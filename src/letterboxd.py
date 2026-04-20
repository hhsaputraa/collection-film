"""
letterboxd.py — Scrape film dari sebuah Letterboxd list (dengan pagination)
"""
import json
import re
import time
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from rich.console import Console

console = Console()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _normalize_url(url: str) -> str:
    """Pastikan URL diakhiri dengan slash agar paginasi bekerja."""
    if not url.endswith("/"):
        url += "/"
    return url


def _parse_year(display_name: str) -> int | None:
    """
    Ambil tahun dari string seperti 'Harakiri (1962)' → 1962.
    Returns None jika tidak ditemukan.
    """
    match = re.search(r"\((\d{4})\)$", display_name.strip())
    return int(match.group(1)) if match else None


def _parse_title(display_name: str) -> str:
    """
    Ambil judul bersih dari 'Harakiri (1962)' → 'Harakiri'.
    """
    return re.sub(r"\s*\(\d{4}\)$", "", display_name.strip()).strip()


def _extract_films_from_soup(soup: BeautifulSoup) -> list[dict]:
    """
    Ambil data film dari satu halaman Letterboxd.

    Struktur HTML aktual (2025+):
      li.posteritem
        └─ div.react-component[data-component-class="LazyPoster"]
             ├─ data-item-full-display-name = "Harakiri (1962)"
             ├─ data-item-slug              = "harakiri"
             ├─ data-film-id               = "43015"
             └─ data-target-link           = "/film/harakiri/"
    """
    films = []

    # Selector utama: LazyPoster react-component di dalam li.posteritem
    lazy_posters = soup.select(
        'li.posteritem div.react-component[data-component-class="LazyPoster"]'
    )

    for lp in lazy_posters:
        full_name   = lp.get("data-item-full-display-name", "").strip()
        item_name   = lp.get("data-item-name", "").strip()
        slug        = lp.get("data-item-slug", "").strip()
        target_link = lp.get("data-target-link", "").strip()
        film_id     = lp.get("data-film-id", "").strip()

        # Pilih sumber terbaik untuk judul + tahun
        source = full_name or item_name
        if source:
            title = _parse_title(source)
            year  = _parse_year(source)
        else:
            # Fallback: img alt (tidak ada tahun)
            img   = lp.find("img")
            title = img.get("alt", "").strip() if img else ""
            year  = None

        if title:
            films.append({
                "slug":        slug,
                "title":       title,
                "year":        year,
                "target_link": target_link,
                "film_id":     film_id,
            })

    return films


def _get_list_name(soup: BeautifulSoup, url: str) -> str:
    """Ambil nama list dari halaman Letterboxd."""
    for selector in ["h1.title-1", "h1.list-title", "h1"]:
        h1 = soup.select_one(selector)
        if h1:
            text = h1.get_text(strip=True)
            if text:
                return text

    # Fallback: <title> tag — format: "Name • A list by User • Letterboxd"
    title_tag = soup.find("title")
    if title_tag:
        parts = [p.strip() for p in title_tag.get_text().split("•") if p.strip()]
        if parts:
            return parts[0]

    # Last fallback: URL slug
    path_parts = urlparse(url).path.strip("/").split("/")
    if "list" in path_parts:
        idx = path_parts.index("list")
        if idx + 1 < len(path_parts):
            return path_parts[idx + 1].replace("-", " ").title()

    return "Letterboxd Collection"


def scrape_list(url: str, delay: float = 1.0, session: requests.Session = None) -> tuple[list[dict], str]:
    """
    Scrape semua film dari sebuah Letterboxd list URL.

    Returns:
        tuple: (list of film dicts, list_name)
            film dict: { slug, title, year, target_link, film_id }
    """
    url = _normalize_url(url)
    all_films: list[dict] = []
    list_name = ""
    page = 1

    if session is None:
        session = requests.Session()
        session.headers.update(HEADERS)

    while True:
        page_url = f"{url}page/{page}/" if page > 1 else url
        console.log(f"  [dim]Fetching halaman {page}: {page_url}[/dim]")

        try:
            response = session.get(page_url, timeout=15)
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if response.status_code == 404:
                console.print(
                    "[red]✗ List tidak ditemukan (404). "
                    "Pastikan URL benar dan list bersifat publik.[/red]"
                )
                raise
            raise RuntimeError(f"HTTP error saat mengakses Letterboxd: {e}") from e
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Koneksi gagal: {e}") from e

        soup = BeautifulSoup(response.text, "lxml")

        if page == 1:
            list_name = _get_list_name(soup, url)

        films_on_page = _extract_films_from_soup(soup)

        if not films_on_page:
            # Tidak ada film → selesai
            break

        all_films.extend(films_on_page)

        # Cek pagination — Letterboxd pakai <a class="next">
        next_btn = soup.select_one("a.next")
        if not next_btn:
            break

        page += 1
        time.sleep(delay)

    return all_films, list_name


def fetch_film_director(target_link: str, session: requests.Session = None) -> str | None:
    """
    Ambil nama sutradara dari halaman spesifik film di Letterboxd.
    Menggunakan JSON-LD yang ada di dalam tag <script type="application/ld+json">.
    """
    url = f"https://letterboxd.com{target_link}"
    try:
        # Gunakan session jika ada, jika tidak pakai requests standar
        if session:
            # Tambahkan Referer untuk mengelabui Cloudflare
            headers = {**session.headers, "Referer": "https://letterboxd.com/"}
            response = session.get(url, headers=headers, timeout=10)
        else:
            headers = {**HEADERS, "Referer": "https://letterboxd.com/"}
            response = requests.get(url, headers=headers, timeout=10)
            
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        
        script = soup.find("script", type="application/ld+json")
        if not script or not script.string:
            return None
        
        raw = script.string.strip()
        if raw.startswith("/* <![CDATA[ */"):
            raw = raw[15:]
        if raw.endswith("/* ]]> */"):
            raw = raw[:-9]
            
        data = json.loads(raw.strip())
        directors = data.get("director", [])
        if isinstance(directors, dict):
            directors = [directors]
            
        for d in directors:
            name = d.get("name")
            if name:
                return name
    except Exception as e:
        console.log(f"  [dim]Gagal mengambil sutradara dari {target_link}: {e}[/dim]")
        
    return None
