"""
tmdb.py — Semua interaksi dengan TMDB API (search, create list, add items)
"""
import time
import difflib
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

    def _is_director_match(self, movie_id: int, target_director: str) -> bool:
        """Fetch credits for a movie and check if the director matches target_director."""
        url = f"{TMDB_BASE_V3}/movie/{movie_id}?append_to_response=credits"
        try:
            resp = self._session.get(url, timeout=10)
            if resp.status_code != 200:
                return False
            data = resp.json()
            crew = data.get("credits", {}).get("crew", [])
            for c in crew:
                if c.get("job") == "Director":
                    tmdb_dir = c.get("name", "")
                    if not tmdb_dir:
                        continue
                    
                    # Normalisasi untuk perbandingan
                    n1 = target_director.lower()
                    n2 = tmdb_dir.lower()
                    
                    if n1 in n2 or n2 in n1:
                        return True
                    if difflib.SequenceMatcher(None, n1, n2).ratio() > 0.8:
                        return True
        except Exception:
            pass
        return False

    def search_movie(
        self, title: str, year: Optional[int] = None, director: Optional[str] = None
    ) -> Optional[dict]:
        """
        Cari film di TMDB.
        Prioritas 1: /search/movie (support primary_release_year)
        Prioritas 2: /search/tv (support first_air_date_year)
        Prioritas 3: /search/multi (tanpa filter tahun)
        """
        results = []
        
        # 1. Coba cari sebagai MOVIE (karena Letterboxd mayoritas film)
        movie_params = {
            "query": title,
            "language": self.language,
            "include_adult": "false",
            "page": 1,
        }
        if year:
            movie_params["primary_release_year"] = year
            
        try:
            resp = self._session.get(f"{TMDB_BASE_V3}/search/movie", params=movie_params, timeout=10)
            resp.raise_for_status()
            movie_results = resp.json().get("results", [])
            for r in movie_results:
                r["media_type"] = "movie"
            results.extend(movie_results)
        except Exception:
            pass

        # 2. Jika tidak ada hasil, coba cari sebagai TV (opsional jika bukan list film murni)
        if not results:
            tv_params = movie_params.copy()
            if year:
                # Ganti key param untuk TV
                tv_params.pop("primary_release_year", None)
                tv_params["first_air_date_year"] = year
            try:
                resp = self._session.get(f"{TMDB_BASE_V3}/search/tv", params=tv_params, timeout=10)
                resp.raise_for_status()
                tv_results = resp.json().get("results", [])
                for r in tv_results:
                    r["media_type"] = "tv"
                results.extend(tv_results)
            except Exception:
                pass

        # 3. Fallback: Multi-search tanpa filter tahun jika masih zonk
        if not results:
            multi_params = {
                "query": title,
                "language": self.language,
                "include_adult": "false",
                "page": 1,
            }
            try:
                resp = self._session.get(f"{TMDB_BASE_V3}/search/multi", params=multi_params, timeout=10)
                resp.raise_for_status()
                results = resp.json().get("results", [])
                results = [r for r in results if r.get("media_type") in ["movie", "tv"]]
            except Exception:
                pass

        if not results:
            return None

        # Pilih kandidat terbaik
        selected_result = results[0]
        
        # Validasi sutradara jika ada (tingkatkan ke 5 hasil teratas)
        if director:
            for res in results[:5]:
                if self._is_director_match(res["id"], director):
                    selected_result = res
                    break

        return selected_result

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
        self, 
        list_id: int, 
        items: list[dict], 
        chunk_size: int = 20,
        on_item_start: Optional[callable] = None
    ) -> dict:
        """
        Tambahkan film ke list TMDB (v4).
        Mendukung bulk insert dalam batch (max 20 per request sesuai limit TMDB).

        - items: list dari dict {"id": movie_id, "title": title}
        - on_item_start: callback function yang dipanggil sebelum item ditambahkan

        Returns dict berisi jumlah success dan failed.
        """
        url = f"{TMDB_BASE_V4}/list/{list_id}/items"
        total_success = 0
        total_failed = 0

        # Bagi menjadi chunks agar tidak melebihi batasan API
        for i in range(0, len(items), chunk_size):
            chunk = items[i : i + chunk_size]
            
            # Panggil callback untuk setiap item dalam chunk (visual progress)
            if on_item_start:
                for item in chunk:
                    on_item_start(item)

            payload = {
                "items": [
                    {"media_type": "movie", "media_id": item["id"]} for item in chunk
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
            if i + chunk_size < len(items):
                time.sleep(0.5)

        return {"success": total_success, "failed": total_failed}
