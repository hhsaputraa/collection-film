"""
main.py — Entry point CLI: Letterboxd → TMDB Collection Sync
============================================================

Usage:
    python main.py
    python main.py --url "https://letterboxd.com/username/list/my-list/"
    python main.py --url "https://letterboxd.com/username/list/my-list/" --name "My TMDB List"
"""
import argparse
import sys
import time

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from src.config import get_config
from src.letterboxd import scrape_list
from src.tmdb import TMDBClient
from src.auth import run_auth_flow
from src.supabase_client import SupabaseClient

console = Console()


# ─────────────────────────────────────────────────────────
#  Banner
# ─────────────────────────────────────────────────────────

def print_banner():
    banner = Text()
    banner.append("🎬  Letterboxd", style="bold cyan")
    banner.append("  →  ", style="dim white")
    banner.append("TMDB", style="bold magenta")
    banner.append("  Collection Sync", style="bold white")

    console.print()
    console.print(Panel(banner, border_style="cyan", padding=(0, 4)))
    console.print()


# ─────────────────────────────────────────────────────────
#  Step 1: Scrape Letterboxd
# ─────────────────────────────────────────────────────────

def step_scrape(url: str, delay: float) -> tuple[list[dict], str]:
    console.rule("[bold cyan]Step 1 — Scraping Letterboxd[/bold cyan]")
    console.print()

    with console.status("[cyan]Mengambil data dari Letterboxd...[/cyan]", spinner="dots"):
        films, list_name = scrape_list(url, delay=delay)

    if not films:
        console.print("[red]✗ Tidak ada film yang ditemukan di list ini.[/red]")
        console.print("  Pastikan URL benar dan list bersifat [bold]publik[/bold].")
        sys.exit(1)

    console.print(f"[green]✓[/green] List ditemukan: [bold]{list_name}[/bold]")
    console.print(f"[green]✓[/green] Total film ter-scrape: [bold]{len(films)}[/bold]")
    console.print()
    return films, list_name


# ─────────────────────────────────────────────────────────
#  Step 2: Search di TMDB
# ─────────────────────────────────────────────────────────

def step_search(films: list[dict], client: TMDBClient) -> tuple[list[dict], list[str]]:
    from src.letterboxd import fetch_film_director
    console.rule("[bold cyan]Step 2 — Mencari Film di TMDB[/bold cyan]")
    console.print()

    found_movies: list[dict] = []
    not_found: list[str] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Mencari film...[/cyan]", total=len(films))

        for film in films:
            title = film.get("title", "Unknown")
            year  = film.get("year")
            target_link = film.get("target_link")
            
            # 1. Fetch director dari detail page Letterboxd
            progress.update(task, description=f"[cyan]Mengecek info:[/cyan] {title[:30]}")
            director = None
            if target_link:
                director = fetch_film_director(target_link)
            
            # 2. Cari di TMDB
            progress.update(task, description=f"[cyan]Mencari di TMDB:[/cyan] {title[:35]}")
            movie_data = client.search_movie(title, year=year, director=director)

            if movie_data:
                found_movies.append(movie_data)
                movie_id = movie_data.get("id")
                dir_info = f", Dir: {director}" if director else ""
                progress.console.print(f"  [green]✓[/green] {title} ({year or '?'}{dir_info})  [dim]→ ID: {movie_id}[/dim]")
            else:
                not_found.append(title)
                progress.console.print(f"  [yellow]✗[/yellow] {title}  [dim](tidak ditemukan di TMDB)[/dim]")

            progress.advance(task)
            time.sleep(0.25)  # hindari rate limiting TMDB

    console.print()
    console.print(f"[green]✓ Ditemukan:[/green] [bold]{len(found_movies)}[/bold] film")
    if not_found:
        console.print(f"[yellow]✗ Tidak ditemukan:[/yellow] [bold]{len(not_found)}[/bold] film (akan dilewati)")
    console.print()

    return found_movies, not_found


# ─────────────────────────────────────────────────────────
#  Step 3: Buat List dan Insert ke TMDB
# ─────────────────────────────────────────────────────────

def step_create_and_insert(
    client: TMDBClient,
    list_name: str,
    found_movies: list[dict],
    source_url: str,
) -> int:
    console.rule("[bold cyan]Step 3 — Membuat List & Menambahkan Film ke TMDB[/bold cyan]")
    console.print()

    # Buat list
    with console.status(f"[cyan]Membuat list [bold]{list_name}[/bold] di TMDB...[/cyan]", spinner="dots"):
        list_id = client.create_list(
            name=list_name,
            description=f"My collection: {list_name}",
        )

    console.print(f"[green]✓[/green] List dibuat — ID: [bold]{list_id}[/bold]")

    # Insert film dengan progress update per item
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"[cyan]Menambahkan {len(found_movies)} film...[/cyan]", 
            total=len(found_movies)
        )

        def on_item_start(item):
            title = item.get('title') or item.get('name') or "Unknown"
            progress.update(task, description=f"[cyan]Menambahkan:[/cyan] {title[:40]}")
            progress.advance(task)

        result = client.add_items_to_list(list_id, found_movies, on_item_start=on_item_start)

    console.print()
    console.print(
        f"[green]✓[/green] Berhasil ditambahkan: [bold]{result['success']}[/bold] film"
    )
    if result["failed"]:
        console.print(f"[yellow]✗[/yellow] Gagal ditambahkan: [bold]{result['failed']}[/bold] film")

    return list_id


def step_supabase_insert(
    client: SupabaseClient,
    list_name: str,
    found_movies: list[dict],
) -> str:
    console.rule("[bold cyan]Step 3 — Membuat Collection & Insert ke Supabase[/bold cyan]")
    console.print()

    # 1. Buat collection
    with console.status(f"[cyan]Membuat collection [bold]{list_name}[/bold] di Supabase...[/cyan]", spinner="dots"):
        collection_id = client.create_collection(list_name)

    console.print(f"[green]✓[/green] Collection dibuat — ID: [bold]{collection_id}[/bold]")

    # 2. Insert items
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"[cyan]Memasukkan {len(found_movies)} item...[/cyan]", 
            total=len(found_movies)
        )

        # Supabase insertion (batch send, but we show individual progress in UI)
        for movie in found_movies:
            title = movie.get('title') or movie.get('name') or "Unknown"
            progress.update(task, description=f"[cyan]Menyimpan:[/cyan] {title[:40]}")
            progress.advance(task)
            
        client.add_items_to_collection(collection_id, found_movies)

    console.print()
    console.print(f"[green]✓[/green] Berhasil disimpan ke Supabase")
    return collection_id


# ─────────────────────────────────────────────────────────
#  Summary
# ─────────────────────────────────────────────────────────

def print_summary(
    list_name: str,
    list_id: str,
    total_scraped: int,
    total_found: int,
    not_found: list[str],
    destination: str = "tmdb"
):
    console.rule("[bold green]✅  Selesai![/bold green]")
    console.print()

    table = Table(box=box.ROUNDED, show_header=False, border_style="green")
    table.add_column("Label", style="dim", width=22)
    table.add_column("Value", style="bold")

    target_label = "Nama List TMDB" if destination == "tmdb" else "Nama Collection SB"
    table.add_row(target_label, list_name)
    table.add_row("Total di Letterboxd", str(total_scraped))
    table.add_row("Berhasil di-insert", f"[green]{total_found}[/green]")
    table.add_row(
        "Tidak ditemukan",
        f"[yellow]{len(not_found)}[/yellow]" if not_found else "[green]0[/green]",
    )
    
    if destination == "tmdb":
        table.add_row(
            "Link List TMDB",
            f"[link=https://www.themoviedb.org/list/{list_id}]https://www.themoviedb.org/list/{list_id}[/link]",
        )
    else:
        table.add_row("Destinasi", "Supabase Collection")
        table.add_row("Collection ID", list_id)

    console.print(table)

    if not_found:
        console.print()
        console.print("[yellow]Film yang tidak ditemukan di TMDB:[/yellow]")
        for title in not_found:
            console.print(f"  [dim]• {title}[/dim]")

    console.print()


# ─────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Sync Letterboxd list ke TMDB collection otomatis.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh:
  python main.py
  python main.py --url "https://letterboxd.com/myusername/list/myfav/"
  python main.py --url "https://letterboxd.com/myusername/list/myfav/" --name "My Favorites"
        """,
    )
    parser.add_argument(
        "--url",
        type=str,
        default="",
        help="URL Letterboxd list yang ingin disync (harus publik)",
    )
    parser.add_argument(
        "--name",
        type=str,
        default="",
        help="Nama list di TMDB. Jika kosong, akan menggunakan nama dari Letterboxd.",
    )
    return parser.parse_args()


def main():
    print_banner()

    # Load konfigurasi
    try:
        config = get_config()
    except EnvironmentError as e:
        console.print(f"[red]✗ Konfigurasi Error:[/red]\n{e}")
        sys.exit(1)

    # Input URL
    args = parse_args()
    url = args.url.strip()
    if not url:
        url = Prompt.ask(
            "[cyan]Masukkan URL Letterboxd list[/cyan]\n"
            "  [dim](contoh: https://letterboxd.com/username/list/myfav/)[/dim]\n  > "
        ).strip()

    if not url.startswith("https://letterboxd.com"):
        console.print("[red]✗ URL tidak valid. Harus dimulai dengan https://letterboxd.com[/red]")
        sys.exit(1)

    # ── Pilih Destinasi ──────────────────────────────────
    console.print("[cyan]Pilih destinasi insert:[/cyan]")
    console.print("  1. TMDB List [dim](v4)[/dim]")
    console.print("  2. Supabase Collection")
    choice = Prompt.ask("  Pilihan", choices=["1", "2"], default="1")
    destination = "tmdb" if choice == "1" else "supabase"
    console.print()

    # Inisialisasi TMDB Client & validasi token
    tmdb_client = TMDBClient(
        api_read_token=config["access_token"],
        user_access_token=config["user_access_token"],
        language=config["language"],
    )

    with console.status("[cyan]Memvalidasi token TMDB...[/cyan]", spinner="dots"):
        try:
            account = tmdb_client.validate_token()
            username = account.get("username", account.get("name", "Unknown"))
        except PermissionError as e:
            console.print(f"[red]✗ Token TMDB Error:[/red]\n{e}")
            sys.exit(1)

    console.print(f"[green]✓[/green] Token TMDB valid — Login sebagai: [bold]{username}[/bold]")
    
    # Inisialisasi Supabase if needed
    sb_client = None
    if destination == "supabase":
        if not config["supabase_url"] or not config["supabase_key"]:
            console.print("[red]✗ Konfigurasi Supabase (URL/Key) belum diisi di .env[/red]")
            sys.exit(1)
        sb_client = SupabaseClient(
            url=config["supabase_url"],
            key=config["supabase_key"],
            user_id=config["supabase_user_id"]
        )
        console.print(f"[green]✓[/green] Supabase Client siap — User ID: [dim]{config['supabase_user_id']}[/dim]")
    
    console.print()

    # ── Step 1: Scrape ──────────────────────────────────
    try:
        films, list_name = step_scrape(url, delay=config["scrape_delay"])
    except RuntimeError as e:
        console.print(f"[red]✗ Gagal scraping Letterboxd:[/red] {e}")
        sys.exit(1)

    # Input nama list TMDB
    tmdb_list_name = args.name.strip()
    if not tmdb_list_name:
        tmdb_list_name = Prompt.ask(
            f"[cyan]Nama list di TMDB[/cyan] [dim](Enter = gunakan nama Letterboxd)[/dim]",
            default=list_name,
        ).strip() or list_name

    # ── Step 2: Search ──────────────────────────────────
    found_movies, not_found = step_search(films, tmdb_client)

    if not found_movies:
        console.print("[red]✗ Tidak ada film yang berhasil ditemukan di TMDB. Proses dihentikan.[/red]")
        sys.exit(1)

    # ── Step 3: Insert ──────────────────────────────────
    if destination == "tmdb":
        # Cek user_access_token — diperlukan untuk write ke TMDB
        if not tmdb_client.has_write_access:
            console.print()
            console.rule("[bold yellow]Autentikasi Diperlukan[/bold yellow]")
            try:
                from pathlib import Path
                env_path = Path(".") / ".env"
                user_token = run_auth_flow(
                    api_read_access_token=config["access_token"],
                    env_path=env_path,
                )
                tmdb_client.set_user_access_token(user_token)
                console.print()
            except (PermissionError, RuntimeError) as e:
                console.print(f"[red]✗ Auth gagal:[/red] {e}")
                sys.exit(1)

        try:
            list_id = step_create_and_insert(tmdb_client, tmdb_list_name, found_movies, source_url=url)
        except Exception as e:
            console.print(f"[red]✗ Gagal membuat list atau menambahkan film:[/red] {e}")
            sys.exit(1)
    else:
        # Supabase
        try:
            list_id = step_supabase_insert(sb_client, tmdb_list_name, found_movies)
        except Exception as e:
            console.print(f"[red]✗ Gagal sinkron ke Supabase:[/red] {e}")
            sys.exit(1)

    # ── Summary ─────────────────────────────────────────
    print_summary(
        list_name=tmdb_list_name,
        list_id=str(list_id), # cast to string case ID is UUID
        total_scraped=len(films),
        total_found=len(found_movies),
        not_found=not_found,
        destination=destination
    )


if __name__ == "__main__":
    main()
