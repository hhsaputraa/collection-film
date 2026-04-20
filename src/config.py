"""
config.py — Load dan validasi environment variables
"""
import os
from dotenv import load_dotenv


def get_config() -> dict:
    """
    Ambil semua konfigurasi dari .env.
    - TMDB_ACCESS_TOKEN      : API Read Access Token (wajib, untuk search & auth flow)
    - TMDB_USER_ACCESS_TOKEN : User Access Token (optional, akan diisi setelah auth)
    """
    # Reload setiap kali dipanggil agar .env yang baru ditulis langsung terbaca
    load_dotenv(override=True)

    access_token = os.getenv("TMDB_ACCESS_TOKEN", "").strip()

    if not access_token:
        raise EnvironmentError(
            "TMDB_ACCESS_TOKEN tidak ditemukan di file .env\n"
            "Silakan copy .env.example ke .env dan isi dengan credentials Anda.\n"
            "Dapatkan dari: https://www.themoviedb.org/settings/api\n"
            "  → Bagian 'API Read Access Token (v4 auth)'"
        )

    return {
        "access_token": access_token,
        # Akan terisi setelah auth flow selesai
        "user_access_token": os.getenv("TMDB_USER_ACCESS_TOKEN", "").strip(),
        "account_id": os.getenv("TMDB_ACCOUNT_ID", "").strip(),
        "language": os.getenv("TMDB_LANGUAGE", "en-US"),
        "scrape_delay": float(os.getenv("SCRAPE_DELAY", "1.0")),
        # Supabase config
        "supabase_url": os.getenv("SUPABASE_URL", "").strip(),
        "supabase_key": os.getenv("SUPABASE_KEY", "").strip(),
        "supabase_user_id": os.getenv("SUPABASE_USER_ID", "").strip(),
    }

