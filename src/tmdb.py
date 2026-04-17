"""
tmdb.py — Semua interaksi dengan TMDB API (search, create list, add items)
"""
import time
from typing import Optional

import requests
from rich.console import Console

console = Console()

TMDB_BASE_V3 = "https://api.themoviedb.org/3"
TMDB_BASE_V4 = "https://api.themoviedb.org/4"


class TMDBClient:
    """
    Client untuk TMDB API v3/v4.

    - api_read_token      : API Read Access Token (dari settings/api) — untuk search & auth
    - user_access_token   : User Access Token dari OAuth flow — untuk write (create list, add items)
    """

    def __init__(
        self,
        api_read_token: str,
        user_access_token: str = "",
        language: str = "en-US",
    ):
        self.language = language
        self._api_read_token = api_read_token
        self._user_access_token = user_access_token

        # Session utama pakai read token (untuk search & validasi)
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {api_read_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    @property
    def has_write_access(self) -> bool:
        """True jika user_access_token sudah diisi (bisa write ke TMDB)."""
        return bool(self._user_access_token)

    def _write_headers(self) -> dict:
        """Headers untuk operasi write (pakai user_access_token)."""
        return {
            "Authorization": f"Bearer {self._user_access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def set_user_access_token(self, token: str) -> None:
        """Set user access token setelah auth flow selesai."""
        self._user_access_token = token

    # ─────────────────────────────────────────────
    #  Validasi Token
    # ─────────────────────────────────────────────

    def validate_token(self) -> dict:
        """
        Validasi token menggunakan /3/account.
        Returns account info jika valid, raise error jika tidak.
        """
        url = f"{TMDB_BASE_V3}/account"
        resp = self._session.get(url, timeout=10)

        if resp.status_code == 401:
            raise PermissionError(
                "Token TMDB tidak valid atau expired.\n"
                "Pastikan TMDB_ACCESS_TOKEN di .env sudah benar.\n"
                "Dapatkan token di: https://www.themoviedb.org/settings/api"
            )

        resp.raise_for_status()
        return resp.json()

    # ─────────────────────────────────────────────
    #  Search Film
    # ─────────────────────────────────────────────

    def search_movie(self, title: str, year: Optional[int] = None) -> Optional[int]:
        """
        Cari film di TMDB berdasarkan judul (dan tahun opsional).
        Jika ada tahun, coba search dengan tahun dulu untuk akurasi lebih tinggi.
        Fallback: cari tanpa tahun.
        Returns TMDB movie_id jika ditemukan, None jika tidak.
        """
        params: dict = {
            "query": title,
            "language": self.language,
            "include_adult": "false",
            "page": 1,
        }
        if year:
            params["primary_release_year"] = year

        url = f"{TMDB_BASE_V3}/search/movie"
        resp = self._session.get(url, params=params, timeout=10)
        resp.raise_for_status()

        data = resp.json()
        results = data.get("results", [])

        if not results:
            # Fallback: cari tanpa filter tahun
            if year:
                return self.search_movie(title, year=None)
            return None

        # Ambil hasil pertama (TMDB sort by relevance)
        return results[0]["id"]

    # ─────────────────────────────────────────────
    #  Create List
    # ─────────────────────────────────────────────

    def create_list(self, name: str, description: str = "") -> int:
        """
        Buat list baru di TMDB menggunakan v4 (butuh user_access_token).
        Returns list_id dari list yang baru dibuat.

        Payload wajib: name + iso_639_1.
        JANGAN kirim iso_3166_1 / public — TMDB v4 akan 400.
        """
        url = f"{TMDB_BASE_V4}/list"
        payload = {
            "name": name,
            "description": description or f"My collection: {name}",
            "iso_639_1": self.language.split("-")[0],  # "en-US" → "en"
        }

        # Operasi write → pakai user_access_token
        resp = requests.post(
            url,
            json=payload,
            headers=self._write_headers(),
            timeout=10,
        )

        if resp.status_code == 401:
            raise PermissionError(
                "User Access Token tidak valid atau belum diset.\n"
                "Jalankan ulang program — auth flow akan otomatis dipicu."
            )

        if resp.status_code == 400:
            raise RuntimeError(
                f"400 Bad Request saat membuat list.\nResponse: {resp.text}"
            )

        resp.raise_for_status()
        data = resp.json()

        list_id = data.get("id")
        if not list_id:
            raise RuntimeError(f"Gagal membuat list TMDB. Response: {data}")

        return list_id

    # ─────────────────────────────────────────────
    #  Add Items to List
    # ─────────────────────────────────────────────

    def add_items_to_list(
        self, list_id: int, movie_ids: list[int], chunk_size: int = 20
    ) -> dict:
        """
        Tambahkan film ke list TMDB (v4).
        Mendukung bulk insert dalam batch (max 20 per request sesuai limit TMDB).

        Returns dict berisi jumlah success dan failed.
        """
        url = f"{TMDB_BASE_V4}/list/{list_id}/items"
        total_success = 0
        total_failed = 0

        # Bagi menjadi chunks agar tidak melebihi batasan API
        for i in range(0, len(movie_ids), chunk_size):
            chunk = movie_ids[i : i + chunk_size]
            payload = {
                "items": [
                    {"media_type": "movie", "media_id": mid} for mid in chunk
                ]
            }

            # Operasi write → pakai user_access_token
            resp = requests.post(
                url,
                json=payload,
                headers=self._write_headers(),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            # Hitung success/failed dari response
            results = data.get("results", [])
            for result in results:
                if result.get("success"):
                    total_success += 1
                else:
                    total_failed += 1

            # Jika tidak ada results field, asumsikan semua berhasil
            if not results:
                total_success += len(chunk)

            # Jangan spam API
            if i + chunk_size < len(movie_ids):
                time.sleep(0.5)

        return {"success": total_success, "failed": total_failed}
