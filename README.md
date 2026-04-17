# 🎬 Letterboxd → TMDB Collection Sync

Program Python CLI yang otomatis mengambil koleksi film dari Letterboxd dan memasukkannya ke TMDB list.

---

## 🚀 Cara Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Konfigurasi API Key
```bash
# Copy template .env
copy .env.example .env
```

Edit file `.env` dan isi dengan credentials TMDB Anda:

```
TMDB_ACCESS_TOKEN=your_read_access_token_here
```

> **Cara dapatkan token TMDB:**
> 1. Login ke [themoviedb.org](https://www.themoviedb.org)
> 2. Pergi ke **Settings → API**
> 3. Copy nilai **API Read Access Token (v4 auth)** — bukan API Key biasa
> 4. Paste ke `.env`

---

## ▶️ Cara Pakai

### Mode interaktif (recommended)
```bash
python main.py
```
Program akan menanyakan URL Letterboxd list Anda.

### Mode dengan argumen
```bash
python main.py --url "https://letterboxd.com/username/list/nama-list/"
```

### Dengan nama list custom di TMDB
```bash
python main.py --url "https://letterboxd.com/username/list/myfav/" --name "My Favorite Films"
```

---

## 📋 Contoh Output

```
🎬 Letterboxd → TMDB Collection Sync

✓ Token valid — Login sebagai: myusername

── Step 1 — Scraping Letterboxd ─────────────────
✓ List ditemukan: My Favorites
✓ Total film ter-scrape: 10

── Step 2 — Mencari Film di TMDB ────────────────
  ✓ The Dark Knight          → ID: 155
  ✓ Inception                → ID: 27205
  ✓ Interstellar             → ID: 157336
  ...

── Step 3 — Membuat List & Menambahkan Film ──────
✓ List dibuat — ID: 8312745
✓ Berhasil ditambahkan: 10 film

✅ Selesai!
╭──────────────────────────────────────────╮
│ Nama List TMDB    My Favorites           │
│ Total Letterboxd  10                     │
│ Berhasil          10                     │
│ Tidak ditemukan   0                      │
│ Link List TMDB    tmdb.org/list/8312745  │
╰──────────────────────────────────────────╯
```

---

## ⚠️ Catatan Penting

- **List Letterboxd harus publik** — list privat tidak bisa di-scrape
- **Rate limiting**: Program otomatis menambahkan delay antar request agar tidak diblokir
- **Film tidak ditemukan**: Film dengan judul unik/non-Inggris mungkin tidak ditemukan di TMDB, tapi proses tetap lanjut untuk film lainnya

---

## 📁 Struktur Proyek

```
insert-tmdb/
├── main.py              # Entry point CLI
├── requirements.txt     # Dependencies
├── .env.example         # Template konfigurasi
├── .env                 # Konfigurasi rahasia (jangan di-commit!)
└── src/
    ├── config.py        # Load environment variables
    ├── letterboxd.py    # Scraper Letterboxd (dengan pagination)
    └── tmdb.py          # TMDB API client (search, create, insert)
```
