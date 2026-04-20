"""
supabase_client.py — Interaksi dengan Supabase REST API
"""
import requests
from typing import List, Dict, Any

class SupabaseClient:
    def __init__(self, url: str, key: str, user_id: str):
        self.url = url.rstrip('/')
        self.key = key
        self.user_id = user_id
        
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

    def create_collection(self, name: str) -> str:
        """
        Buat collection baru di tabel 'collections'.
        Returns id dari collection yang baru dibuat.
        """
        # Tambahkan apikey ke URL params sebagai fallback jika header tersaring/stripped
        endpoint = f"{self.url}/rest/v1/collections?apikey={self.key}"
        payload = {
            "name": name,
            "user_id": self.user_id
        }
        
        try:
            resp = requests.post(endpoint, json=payload, headers=self.headers, timeout=15)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            # Berikan detail error dari Supabase (biasanya JSON)
            error_data = resp.text
            raise RuntimeError(f"HTTP {resp.status_code}: {error_data}") from e
        
        data = resp.json()
        if not data:
            raise RuntimeError("Gagal membuat collection: Response kosong")
            
        return data[0]["id"]

    def add_items_to_collection(self, collection_id: str, items: List[Dict[str, Any]]):
        """
        Tambah banyak movie/tv ke tabel 'collection_items'.
        """
        endpoint = f"{self.url}/rest/v1/collection_items?apikey={self.key}"
        
        payload = []
        for item in items:
            # Petakan data dari TMDB ke schema Supabase user
            payload.append({
                "collection_id": collection_id,
                "media_id": str(item.get("id")),
                "media_type": item.get("media_type"),
                "poster_path": item.get("poster_path"),
                "title": item.get("title") or item.get("name"),
                "name": item.get("name") or item.get("title"),
                "overview": item.get("overview"),
                "vote_average": item.get("vote_average"),
                "release_date": item.get("release_date"),
                "first_air_date": item.get("first_air_date")
            })

        if not payload:
            return

        try:
            resp = requests.post(endpoint, json=payload, headers=self.headers, timeout=20)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            error_data = resp.text
            raise RuntimeError(f"HTTP {resp.status_code}: {error_data}") from e
            
        return resp.json()
