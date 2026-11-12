---
title: Rikod Live
emoji: 🔴
colorFrom: red
colorTo: pink
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
---

# 🔴 Rikod Live - JKT48 IDN App Live Stream Recorder & Cloud Storage

Aplikasi berbasis web modern untuk memantau (*monitoring*) dan merekam siaran langsung (*live stream*) member **JKT48** secara otomatis dari platform [IDN App (IDN Live)](https://www.idn.app/). Hasil rekaman disimpan secara otomatis ke **penyimpanan lokal (PC/Server)** atau di-upload otomatis ke **Cloud Storage** (Google Drive, Rclone, S3 / Cloudflare R2).

---

## ✨ Fitur Unggulan

1. **Auto-Detection & Monitoring Real-Time**:
   - Terintegrasi langsung dengan GraphQL API IDN Live (`https://api.idn.app/graphql`).
   - Secara otomatis mendeteksi ketika member JKT48 memulai siaran langsung.
   - Filter otomatis berdasarkan database member JKT48 aktif (Generasi 3 s/d Trainee).

2. **Smart Recording Engine (3 Mode Perekam)**:
   - **Native Python HLS Engine**: Perekam HLS bawaan tanpa perlu install software tambahan seperti ffmpeg/yt-dlp. Mengunduh segmen video (`.ts`) secara berkala dan menyusunnya menjadi file rekaman.
   - **yt-dlp**: Menggunakan downloader `yt-dlp` untuk rekaman berkecepatan tinggi dengan output `.mp4`.
   - **FFmpeg**: Menggunakan stream capture copy codec `ffmpeg` jika terpasang di sistem.

3. **Penyimpanan Lokal & Cloud Storage Otomatis**:
   - **Local Storage**: Tersimpan rapi di folder `./recordings/` dengan nama file format `YYYY-MM-DD_HH-mm_[Nama Member]_[Judul].ts/.mp4`.
   - **Google Drive**: Integrasi resmi via Google Drive API (Service Account / OAuth).
   - **Rclone**: Sinkronisasi ke 40+ penyedia cloud (Google Drive, OneDrive, Mega, Dropbox, Nextcloud).
   - **S3 & Cloudflare R2**: Kompatibel dengan Object Storage AWS S3, Cloudflare R2 (10 GB gratis & bebas biaya egress), atau MinIO.
   - **Auto-Delete Setelah Upload**: Opsi menghemat disk lokal dengan menghapus file lokal secara otomatis setelah berhasil ter-upload ke cloud.

4. **Dashboard Web Interaktif & Responsif**:
   - **Live Monitor**: Tampilan kartu siaran live dengan thumbnail, viewer counter, dan tombol tonton preview langsung di browser.
   - **Sesi Aktif**: Pantau durasi berjalan, ukuran file real-time, kecepatan download, dan tombol Stop Rekam.
   - **Galeri Rekaman**: Pemutar video langsung di browser (dengan scrubbing range header), tombol download lokal, upload manual ke cloud, dan hapus arsip.
   - **Watchlist Member**: Switch master "Auto-Record Semua Member" atau atur per-member tertentu saja (misal hanya merekam Freya, Christy, atau Marsha).
   - **Tambah Creator / Member Baru**: Bebas menambahkan username creator IDN baru kapan saja.

5. **Notifikasi Webhook (Discord & Telegram)**:
   - Notifikasi saat member memulai siaran langsung.
   - Notifikasi saat rekaman selesai beserta info ukuran file, durasi siaran, dan link ke cloud storage.

---

## 🚀 Cara Menjalankan

### Persyaratan Sistem
- **Python 3.10** atau lebih baru
- Browser modern (Chrome, Edge, Firefox, Safari)

### Menjalankan di Background Tanpa Membuka Browser (24/7)
Anda tidak perlu membuka website atau browser untuk proses perekaman otomatis:
1. Klik ganda file:
   ```
   run_background.vbs
   ```
   Aplikasi akan langsung berjalan diam-diam (*silent*) di latar belakang Windows tanpa memunculkan jendela hitam terminal.
2. Setiap kali member pilihan Anda memulai live, sistem otomatis merekam dari awal hingga live selesai dan mengunggahnya ke Google Drive.
3. Untuk mengecek status apakah server sedang berjalan: klik ganda **`status.bat`**.
4. Untuk mematikan server: klik ganda **`stop_background.bat`**.

### Di Linux / VPS / macOS:
```bash
# Berikan izin eksekusi script
chmod +x run.sh

# Jalankan launcher
./run.sh
```

Aplikasi dapat diakses melalui browser di:
```
http://localhost:5000
```
*(Atau `http://IP_VPS_ANDA:5000` jika dijalankan di VPS)*

---

## ⚙️ Panduan Konfigurasi Cloud Storage

Buka tab **Pengaturan** di dashboard web untuk memilih penyedia cloud:

### 1. Google Drive (Direct API)
1. Buat project di [Google Cloud Console](https://console.cloud.google.com/).
2. Aktifkan **Google Drive API**.
3. Buat **Service Account**, unduh file kredensial JSON.
4. Buka Google Drive Anda, buat folder khusus (misal `JKT48_Recordings`), lalu bagikan (*Share*) folder tersebut ke email Service Account (akses Editor).
5. Di menu Pengaturan Rikod Live:
   - Pilih Penyedia Cloud: **Google Drive**
   - Masukkan **Google Drive Folder ID** (didapat dari URL folder).
   - Paste isi teks file Service Account JSON.
   - Centang **Auto-Upload** jika ingin file di-upload otomatis setelah rekaman selesai.

### 2. Rclone (Sangat Direkomendasikan untuk VPS/Server)
1. Install [Rclone](https://rclone.org/) di PC/server Anda.
2. Jalankan `rclone config` di terminal dan hubungkan ke Google Drive / OneDrive Anda (misal dinamai `gdrive`).
3. Di menu Pengaturan Rikod Live:
   - Pilih Penyedia Cloud: **Rclone**
   - Masukkan Remote Destination: `gdrive:JKT48_Live`

### 3. S3 / Cloudflare R2
1. Di menu Pengaturan Rikod Live:
   - Masukkan **Endpoint URL** (misal `https://<account_id>.r2.cloudflarestorage.com`)
   - Masukkan **Bucket Name**, **Access Key ID**, dan **Secret Access Key**.

---

## 🔔 Panduan Notifikasi Webhook

- **Discord**: Masuk ke Channel Discord Anda -> *Integrations* -> *Webhooks* -> Salin Webhook URL -> Paste ke kolom Discord Webhook di tab Pengaturan.
- **Telegram**: Buat bot via [@BotFather](https://t.me/BotFather), salin Token bot, dan masukkan Chat ID Anda atau grup Anda.

---

## 📁 Struktur Direktori

```
Rikod Live/
│
├── app.py                 # Server Flask & REST API
├── models.py              # SQLite Database (Rekaman, Watchlist, Pengaturan)
├── core/
│   ├── idn_client.py      # Pengambil data GraphQL API IDN Live
│   ├── hls_engine.py      # Engine perekam HLS Native Python m3u8
│   ├── recorder.py        # Pengelola sesi perekaman (HLS / yt-dlp / FFmpeg)
│   ├── monitor.py         # Background scheduler pemantau siaran langsung
│   ├── cloud_uploader.py  # Handler upload Google Drive, Rclone, dan S3
│   └── notifications.py   # Pengirim notifikasi Discord & Telegram
│
├── static/
│   ├── css/style.css      # Styling & animasi tema idol dark
│   └── js/app.js          # SPA logic & live video preview
│
├── templates/
│   └── index.html         # Tampilan web dashboard
│
├── data/
│   ├── members.json       # Database awal nama & username member JKT48
│   └── app.db             # Database SQLite
│
├── recordings/            # Folder penyimpanan file video rekaman
├── requirements.txt       # Daftar pustaka Python
├── run.bat                # Launcher otomatis Windows
├── run.sh                 # Launcher otomatis Linux/VPS
└── README.md              # Dokumentasi lengkap
```

---

## 💡 Tips & Trik

1. **Jalankan 24/7 di VPS Murah**:
   Anda bisa menyewa VPS murah (RAM 1GB - 2GB) di Linode, DigitalOcean, atau Hetzner, lalu pasang Rikod Live dengan mengaktifkan opsi **Auto-Delete setelah Upload ke Cloud**. Dengan cara ini, disk VPS tidak akan pernah penuh karena video langsung dipindahkan ke Google Drive / Cloudflare R2!
2. **Kualitas Siaran**:
   Native Engine dan yt-dlp secara otomatis mendeteksi resolusi tertinggi (Highest Bandwidth) yang disediakan oleh siaran IDN Live (biasanya 720p/1080p).
