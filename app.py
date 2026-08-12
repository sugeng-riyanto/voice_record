import os
import json
import time
import uuid
import shutil
import threading
import traceback
import asyncio
import subprocess
from pathlib import Path

import static_ffmpeg
static_ffmpeg.add_paths()

import torchaudio
try:
    torchaudio.set_audio_backend("soundfile")
except Exception:
    pass

from flask import Flask, request, jsonify, send_from_directory, render_template

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "output"
SAMPLES = BASE / "samples"
INDEX_FILE = SAMPLES / "samples.json"
OUTPUT.mkdir(exist_ok=True)
SAMPLES.mkdir(exist_ok=True)

app = Flask(__name__, template_folder="templates", static_folder="static")

MODEL_DIR = BASE / "models" / "indo_v2"
MODEL_PATH = MODEL_DIR / "f5_tts_indo_v2.pt"
VOCAB_PATH = MODEL_DIR / "vocab.txt"

_engine = None
_engine_lock = threading.Lock()
_index_lock = threading.Lock()


def _load_index():
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {"samples": []}
    return {"samples": []}


def _save_index(data):
    with _index_lock:
        INDEX_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _norm_audio(src, dst):
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-ac", "1", "-ar", "24000", str(dst)],
        check=True,
        capture_output=True,
    )
    return dst


def _probe_duration(path):
    try:
        from pydub import AudioSegment
        return len(AudioSegment.from_file(str(path))) / 1000.0
    except Exception:
        return 0.0


def get_engine():
    global _engine
    with _engine_lock:
        if _engine is None:
            from f5_tts.api import F5TTS
            _engine = F5TTS(
                model="F5TTS_v1_Base",
                ckpt_file=str(MODEL_PATH),
                vocab_file=str(VOCAB_PATH),
                device="cpu",
            )
    return _engine


@app.route("/")
def index():
    return render_template("index.html")


# ---------------- Voice samples CRUD ----------------


@app.route("/api/samples", methods=["GET"])
def list_samples():
    idx = _load_index()
    for s in idx["samples"]:
        p = SAMPLES / s["id"] / "audio.wav"
        s["exists"] = p.exists()
    return jsonify(idx["samples"])


@app.route("/api/samples", methods=["POST"])
def create_sample():
    name = (request.form.get("name") or "").strip() or "Suara baru"
    sid = uuid.uuid4().hex[:12]
    d = SAMPLES / sid
    d.mkdir(exist_ok=True)
    raw = d / "input_raw"
    f = request.files.get("audio")
    if f and f.filename:
        f.save(str(raw))
    else:
        return jsonify({"error": "No audio uploaded"}), 400
    try:
        wav = _norm_audio(raw, d / "audio.wav")
    except Exception as e:
        shutil.rmtree(d, ignore_errors=True)
        return jsonify({"error": f"Audio convert failed: {e}"}), 400
    dur = _probe_duration(wav)
    sample = {"id": sid, "name": name, "created": time.time(), "duration_s": round(dur, 2)}
    idx = _load_index()
    idx["samples"].insert(0, sample)
    _save_index(idx)
    return jsonify({"ok": True, "sample": sample})


@app.route("/api/samples/<sid>", methods=["PUT"])
def update_sample(sid):
    idx = _load_index()
    s = next((x for x in idx["samples"] if x["id"] == sid), None)
    if not s:
        return jsonify({"error": "Sample not found"}), 404
    if request.form.get("name") is not None:
        s["name"] = (request.form.get("name") or "").strip() or s["name"]
    f = request.files.get("audio")
    if f and f.filename:
        d = SAMPLES / sid
        d.mkdir(exist_ok=True)
        raw = d / "input_raw_repl"
        f.save(str(raw))
        try:
            wav = _norm_audio(raw, d / "audio.wav")
        except Exception as e:
            return jsonify({"error": f"Audio convert failed: {e}"}), 400
        s["duration_s"] = round(_probe_duration(wav), 2)
    _save_index(idx)
    return jsonify({"ok": True, "sample": s})


@app.route("/api/samples/<sid>", methods=["DELETE"])
def delete_sample(sid):
    idx = _load_index()
    s = next((x for x in idx["samples"] if x["id"] == sid), None)
    if not s:
        return jsonify({"error": "Sample not found"}), 404
    idx["samples"] = [x for x in idx["samples"] if x["id"] != sid]
    _save_index(idx)
    shutil.rmtree(SAMPLES / sid, ignore_errors=True)
    return jsonify({"ok": True})


@app.route("/samples/<sid>/audio")
def serve_sample_audio(sid):
    return send_from_directory(str(SAMPLES / sid), "audio.wav")


# ---------------- TTS generation ----------------


@app.route("/api/voices")
def voices():
    import edge_tts
    try:
        out = asyncio.run(edge_tts.list_voices())
        indo = [v for v in out if v["Locale"].startswith("id") or "Indonesian" in v["Locale"]]
        return jsonify({"total": len(out), "indonesian": indo})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/generate", methods=["POST"])
def generate():
    text = (request.form.get("text") or "").strip()
    mode = (request.form.get("mode") or "").strip()
    voice = request.form.get("voice") or "id-ID-ArdiNeural"
    speed = float(request.form.get("speed") or "1.0")
    sample_id = (request.form.get("sample_id") or "").strip()

    if not text:
        return jsonify({"error": "Text is required"}), 400

    # Resolve sample path from library
    sample_path = None
    if sample_id:
        p = SAMPLES / sample_id / "audio.wav"
        if not p.exists():
            return jsonify({"error": "Selected voice sample is missing"}), 400
        sample_path = p

    # Auto-decide mode when not forced
    if not mode:
        mode = "offline" if sample_path else "online"

    try:
        if mode == "online":
            wav_path, dur = _online_tts(text, voice, speed)
        else:
            if sample_path is None:
                return jsonify({"error": "Offline mode needs a voice sample. Pick one from the library or record/upload it."}), 400
            wav_path, dur = _offline_clone(text, sample_path, speed)

        rel = str(Path(wav_path).relative_to(BASE)).replace("\\", "/")
        return jsonify({"ok": True, "audio": rel, "duration_s": round(dur, 2), "mode": mode})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def _online_tts(text, voice, speed):
    import edge_tts
    out_path = OUTPUT / f"online_{int(time.time()*1000)}.mp3"
    communicate = edge_tts.Communicate(text, voice, rate=f"{int((speed-1)*100):+d}%")
    asyncio.run(communicate.save(str(out_path)))
    duration = _probe_duration(out_path)
    return out_path, duration


def _offline_clone(text, sample_path, speed):
    engine = get_engine()
    out_path = OUTPUT / f"offline_{int(time.time()*1000)}.wav"
    wav, sr, _ = engine.infer(
        ref_file=str(sample_path),
        ref_text="",
        gen_text=text,
        speed=speed,
    )
    import soundfile as sf
    import numpy as np
    arr = np.asarray(wav)
    if arr.ndim == 1:
        arr = arr[:, None]
    sf.write(str(out_path), arr, int(sr))
    duration = _probe_duration(out_path)
    return out_path, duration


@app.route("/output/<path:name>")
def serve_audio(name):
    return send_from_directory(str(OUTPUT), name)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Voice Clone TTS running at http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, threaded=True)