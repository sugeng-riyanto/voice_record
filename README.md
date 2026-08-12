# voice_record — Voice Clone Studio

Web app (Flask) untuk **voice cloning & text-to-speech** dalam Bahasa Indonesia.

- **Online**: cepat, suara neural Microsoft Edge (`edge-tts`, e.g. `id-ID-ArdiNeural`) — tanpa butuh sampel.
- **Offline**: clone suara dari sampel suara yang kamu rekam/upload, dijalankan di CPU lokal memakai model **F5-TTS** (`f5_tts_indo_v2`).

## Ide proyek

Rekam atau upload suara (10–30 detik) → simpan ke voice library → pilih sampel → ketik teks → generate.
Output audio bisa diputar dan di-download langsung dari browser. Semua berjalan lokal, hanya proses online TTS yang butuh internet.

## Fitur

- Rekam suara via mikrofon (browser) atau upload file audio
- Voice library dengan CRUD (create / rename / delete)
- Mode offline (clone suara, CPU, ±1–3 menit) atau online (instan)
- Simpan hasil generate ke folder `output/` dan bisa di-download

## Struktur

```
voice_record/
├── app.py               # Flask backend + API
├── requirements.txt     # (lihat Dependencies)
├── templates/index.html # Halaman web UI
├── models/indo_v2/      # Model F5-TTS (TIDAK di-repo GitHub, lihat di bawah)
├── output/              # Hasil generate
└── samples/             # Koleksi suara + samples.json
```

Catatan: `venv/`, `models/`, `output/`, `samples/` tidak ikut di-commit (ada di `.gitignore`).

## Clone

```bash
git clone https://github.com/sugeng-riyanto/voice_record.git
cd voice_record
```

## Setup

1. **Python 3.11+** dan buat virtual environment:

   ```bash
   python -m venv venv
   venv\Scripts\activate        # Windows
   # source venv/bin/activate   # Linux/Mac
   ```

2. **Install dependencies:**

   ```bash
   pip install flask torch torchaudio soundfile numpy pydub ffmpeg-static-static static_ffmpeg edge-tts f5-tts
   ```

   (FFmpeg juga dibutuhkan untuk konversi audio — `static_ffmpeg` sudah menyertakan binary-nya.)

3. **Download model offline (untuk fitur clone suara) — ±1.3GB:**

   File model **tidak** ikut di GitHub (terlalu besar). Download manual lalu taruh di folder yang benar. Tanpa model ini, fitur online tetap jalan.

   **Model Indonesia (default, dipakai `app.py`):**

   - `f5_tts_indo_v2.pt` → <https://huggingface.co/Eempostor/F5-TTS-INDO-FINETUNE-V2/resolve/main/f5_tts_indo_v2.pt?download=true>
   - `vocab.txt` → <https://huggingface.co/Eempostor/F5-TTS-INDO-FINETUNE-V2/resolve/main/vocab.txt?download=true>
   - Simpan ke: `models/indo_v2/f5_tts_indo_v2.pt` dan `models/indo_v2/vocab.txt`

   **Model English (switching: ubah `MODEL_DIR`/`MODEL_PATH` di `app.py`):**

   - F5TTS v1 Base (English, kalimat pendek, ±1.3GB) → <https://huggingface.co/SWivid/F5-TTS/tree/main/F5TTS_v1_Base>
   - F5TTS Base (multilingual EN/ZH) → <https://huggingface.co/SWivid/F5-TTS/tree/main/F5TTS_Base>
   - F5TTS Base pakai format `.safetensors`. Taruh di `models/` lalu perbarui variabel `MODEL_PATH` di `app.py` ke file tersebut (contoh: `F5TTS_v1_Base/model_1250000.safetensors`).

   > Semua model ini tidak boleh dipakai untuk tujuan komersial / impersonasi (lisensi CC-BY-NC 4.0). Suara klon dibuat dari sampel yang di-upload user.

4. **Jalankan:**

   ```bash
   python app.py
   ```

   Buka <http://127.0.0.1:5000>

## Cara pakai

1. **Rekam** suara (tombol ● Record, berhenti otomatis di 12 detik) atau **upload** file audio (10–30 detik paling baik).
2. **Simpan** ke library (isi nama lalu "Save last capture").
3. **Pilih** sampel dengan tombol *Use* → mode otomatis beralih ke **OFFLINE** (clone suara).
   Tanpa memilih sampel → default **ONLINE** (suara neural, instan).
4. **Ketik teks** dan klik *Generate Voice* (atau *Force Online*).
5. Putar / download hasilnya.

## API ringkas

| Method | Endpoint               | Keterangan                  |
|--------|------------------------|-----------------------------|
| GET    | `/`                    | UI                          |
| GET    | `/api/samples`         | List suara                  |
| POST   | `/api/samples`         | Tambah suara (`audio`,`name`) |
| PUT    | `/api/samples/<id>`    | Rename / ganti audio        |
| DELETE | `/api/samples/<id>`    | Hapus suara                 |
| GET    | `/api/voices`          | List suara edge-tts         |
| POST   | `/api/generate`        | Generate TTS (`text`,`mode`,`sample_id`,`speed`) |