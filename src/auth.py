"""
auth.py — TMDB v4 OAuth flow untuk mendapatkan User Access Token (write permission)
"""
import webbrowser
from pathlib import Path

import requests
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

console = Console()

TMDB_BASE_V4 = "https://api.themoviedb.org/4"


def _update_env_file(key: str, value: str, env_path: Path) -> None:
    """Tulis atau update sebuah key di file .env."""
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []

    updated = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}=") or line.startswith(f"{key} ="):
            new_lines.append(f"{key}={value}")
            updated = True
        else:
            new_lines.append(line)

    if not updated:
        new_lines.append(f"{key}={value}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def run_auth_flow(api_read_access_token: str, env_path: Path) -> str:
    """
    Jalankan TMDB v4 OAuth flow:
      1. Buat request_token sementara
      2. User approve di browser
      3. Exchange ke user_access_token (permanent)
      4. Simpan ke .env

    Returns:
        user_access_token (str) yang siap dipakai untuk write operations
    """
    headers = {
        "Authorization": f"Bearer {api_read_access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    console.print()
    console.print(Panel(
        "[bold yellow]⚠  Autentikasi TMDB Diperlukan[/bold yellow]\n\n"
        "Untuk membuat list dan menambahkan film, program perlu izin write ke akun TMDB Anda.\n"
        "Proses ini hanya perlu dilakukan [bold]sekali saja[/bold] — hasilnya akan disimpan di file [cyan].env[/cyan].",
        border_style="yellow",
        expand=False,
    ))
    console.print()

    # ── Step 1: Buat Request Token ────────────────────────────
    console.print("[cyan]Step 1:[/cyan] Membuat request token...")
    resp = requests.post(
        f"{TMDB_BASE_V4}/auth/request_token",
        headers=headers,
        timeout=10,
    )

    if resp.status_code == 401:
        raise PermissionError(
            "TMDB_ACCESS_TOKEN tidak valid. "
            "Pastikan token di .env sudah benar.\n"
            "Ambil dari: https://www.themoviedb.org/settings/api"
        )
    resp.raise_for_status()

    request_token = resp.json().get("request_token")
    if not request_token:
        raise RuntimeError(f"Gagal mendapat request token: {resp.text}")

    console.print(f"  [green]✓[/green] Request token berhasil dibuat.")

    # ── Step 2: User Approve di Browser ──────────────────────
    approve_url = f"https://www.themoviedb.org/auth/access?request_token={request_token}"

    console.print()
    console.print("[cyan]Step 2:[/cyan] Buka URL berikut di browser Anda dan klik [bold]Approve[/bold]:")
    console.print(f"\n  [link={approve_url}][bold underline]{approve_url}[/bold underline][/link]\n")

    # Coba buka browser otomatis
    try:
        webbrowser.open(approve_url)
        console.print("  [dim](Browser otomatis dibuka...)[/dim]")
    except Exception:
        console.print("  [dim](Buka URL di atas secara manual di browser Anda)[/dim]")

    console.print()
    input("  Setelah klik Approve di browser, tekan [Enter] untuk melanjutkan...")
    console.print()

    # ── Step 3: Exchange ke User Access Token ─────────────────
    console.print("[cyan]Step 3:[/cyan] Menukarkan request token ke user access token...")
    resp2 = requests.post(
        f"{TMDB_BASE_V4}/auth/access_token",
        headers=headers,
        json={"request_token": request_token},
        timeout=10,
    )

    if resp2.status_code == 401:
        raise PermissionError(
            "Request token tidak di-approve atau sudah expired (15 menit).\n"
            "Jalankan lagi dan pastikan mengklik Approve di browser sebelum menekan Enter."
        )
    resp2.raise_for_status()

    data = resp2.json()
    user_access_token = data.get("access_token")
    account_id = data.get("account_id", "")

    if not user_access_token:
        raise RuntimeError(f"Gagal mendapat user access token: {resp2.text}")

    # ── Step 4: Simpan ke .env ────────────────────────────────
    _update_env_file("TMDB_USER_ACCESS_TOKEN", user_access_token, env_path)
    if account_id:
        _update_env_file("TMDB_ACCOUNT_ID", account_id, env_path)

    console.print(f"  [green]✓[/green] User access token berhasil didapat!")
    console.print(f"  [green]✓[/green] Disimpan ke [cyan].env[/cyan] sebagai [bold]TMDB_USER_ACCESS_TOKEN[/bold]")
    if account_id:
        console.print(f"  [green]✓[/green] Account ID: [bold]{account_id}[/bold]")

    return user_access_token
