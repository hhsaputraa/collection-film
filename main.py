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

def step_search(films: list[dict], client: TMDBClient) -> tuple[list[int], list[str]]:
    from src.letterboxd import fetch_film_director
    console.rule("[bold cyan]Step 2 — Mencari Film di TMDB[/bold cyan]")
    console.print()

    found_ids: list[int] = []
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
            movie_id = client.search_movie(title, year=year, director=director)

            if movie_id:
                found_ids.append(movie_id)
                dir_info = f", Dir: {director}" if director else ""
                progress.console.print(f"  [green]✓[/green] {title} ({year or '?'}{dir_info})  [dim]→ ID: {movie_id}[/dim]")
            else:
                not_found.append(title)
                progress.console.print(f"  [yellow]✗[/yellow] {title}  [dim](tidak ditemukan di TMDB)[/dim]")

            progress.advance(task)
            time.sleep(0.25)  # hindari rate limiting TMDB

    console.print()
    console.print(f"[green]✓ Ditemukan:[/green] [bold]{len(found_ids)}[/bold] film")
    if not_found:
        console.print(f"[yellow]✗ Tidak ditemukan:[/yellow] [bold]{len(not_found)}[/bold] film (akan dilewati)")
    console.print()

    return found_ids, not_found


# ─────────────────────────────────────────────────────────
#  Step 3: Buat List dan Insert ke TMDB
# ─────────────────────────────────────────────────────────

def step_create_and_insert(
    client: TMDBClient,
    list_name: str,
    found_ids: list[int],
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

    # Insert film
    with console.status(f"[cyan]Menambahkan [bold]{len(found_ids)}[/bold] film ke list...[/cyan]", spinner="dots"):
        result = client.add_items_to_list(list_id, found_ids)

    console.print(
        f"[green]✓[/green] Berhasil ditambahkan: [bold]{result['success']}[/bold] film"
    )
    if result["failed"]:
        console.print(f"[yellow]✗[/yellow] Gagal ditambahkan: [bold]{result['failed']}[/bold] film")

    return list_id


# ─────────────────────────────────────────────────────────
#  Summary
# ─────────────────────────────────────────────────────────

def print_summary(
    list_name: str,
    list_id: int,
    total_scraped: int,
    total_found: int,
    not_found: list[str],
):
    console.rule("[bold green]✅  Selesai![/bold green]")
    console.print()

    table = Table(box=box.ROUNDED, show_header=False, border_style="green")
    table.add_column("Label", style="dim", width=22)
    table.add_column("Value", style="bold")

    table.add_row("Nama List TMDB", list_name)
    table.add_row("Total di Letterboxd", str(total_scraped))
    table.add_row("Berhasil di-insert", f"[green]{total_found}[/green]")
    table.add_row(
        "Tidak ditemukan",
        f"[yellow]{len(not_found)}[/yellow]" if not_found else "[green]0[/green]",
    )
    table.add_row(
        "Link List TMDB",
        f"[link=https://www.themoviedb.org/list/{list_id}]https://www.themoviedb.org/list/{list_id}[/link]",
    )

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

    # Inisialisasi TMDB Client & validasi token
    client = TMDBClient(
        api_read_token=config["access_token"],
        user_access_token=config["user_access_token"],
        language=config["language"],
    )

    with console.status("[cyan]Memvalidasi token TMDB...[/cyan]", spinner="dots"):
        try:
            account = client.validate_token()
            username = account.get("username", account.get("name", "Unknown"))
        except PermissionError as e:
            console.print(f"[red]✗ Token Error:[/red]\n{e}")
            sys.exit(1)

    console.print(f"[green]✓[/green] Token valid — Login sebagai: [bold]{username}[/bold]")
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
    found_ids, not_found = step_search(films, client)

    if not found_ids:
        console.print("[red]✗ Tidak ada film yang berhasil ditemukan di TMDB. Proses dihentikan.[/red]")
        sys.exit(1)

    # ── Step 3: Create list & insert ────────────────────
    # Cek user_access_token — diperlukan untuk write ke TMDB
    if not client.has_write_access:
        console.print()
        console.rule("[bold yellow]Autentikasi Diperlukan[/bold yellow]")
        try:
            from pathlib import Path
            env_path = Path(".") / ".env"
            user_token = run_auth_flow(
                api_read_access_token=config["access_token"],
                env_path=env_path,
            )
            client.set_user_access_token(user_token)
            console.print()
        except (PermissionError, RuntimeError) as e:
            console.print(f"[red]✗ Auth gagal:[/red] {e}")
            sys.exit(1)

    try:
        list_id = step_create_and_insert(client, tmdb_list_name, found_ids, source_url=url)
    except Exception as e:
        console.print(f"[red]✗ Gagal membuat list atau menambahkan film:[/red] {e}")
        sys.exit(1)

    # ── Summary ─────────────────────────────────────────
    print_summary(
        list_name=tmdb_list_name,
        list_id=list_id,
        total_scraped=len(films),
        total_found=len(found_ids),
        not_found=not_found,
    )


if __name__ == "__main__":
    main()
