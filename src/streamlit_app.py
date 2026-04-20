import streamlit as st
import time
import sys
from pathlib import Path

# Import logic dari src
from src.config import get_config
from src.letterboxd import scrape_list
from src.tmdb import TMDBClient
from src.supabase_client import SupabaseClient

# ─────────────────────────────────────────────────────────
#  Page Config & Styling
# ─────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Letterboxd → TMDB/Supabase Sync",
    page_icon="🎬",
    layout="centered",
)

# Custom CSS for better aesthetics
st.markdown("""
    <style>
    .main {
        background: linear-gradient(to bottom, #121212, #1a1a1a);
    }
    .stButton>button {
        width: 100%;
        border-radius: 10px;
        height: 3em;
        background-color: #00d573;
        color: white;
        font-weight: bold;
        border: none;
    }
    .stButton>button:hover {
        background-color: #00b361;
        border: none;
        color: white;
    }
    .success-text {
        color: #00d573;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────
#  Helper Functions
# ─────────────────────────────────────────────────────────

def load_settings():
    """Load config dari .env (local) atau st.secrets (cloud)."""
    try:
        # Prioritas st.secrets jika didefinisikan (untuk cloud hosting)
        if "TMDB_ACCESS_TOKEN" in st.secrets:
            return {
                "access_token": st.secrets["TMDB_ACCESS_TOKEN"],
                "user_access_token": st.secrets.get("TMDB_USER_ACCESS_TOKEN", ""),
                "language": st.secrets.get("TMDB_LANGUAGE", "en-US"),
                "scrape_delay": float(st.secrets.get("SCRAPE_DELAY", "1.0")),
                "supabase_url": st.secrets.get("SUPABASE_URL", ""),
                "supabase_key": st.secrets.get("SUPABASE_KEY", ""),
                "supabase_user_id": st.secrets.get("SUPABASE_USER_ID", ""),
            }
        # Fallback ke get_config (dotenv)
        return get_config()
    except Exception:
        # Jika gagal (misal .env belum ada), berikan form input di UI
        return None

# ─────────────────────────────────────────────────────────
#  Main UI
# ─────────────────────────────────────────────────────────

st.title("🎬 Letterboxd Sync")
st.markdown("Sync collections dari **Letterboxd** ke **TMDB List** atau **Supabase** dalam hitungan detik.")

# Sidebar untuk Konfigurasi (jika belum ada di secrets/.env)
config = load_settings()
with st.sidebar:
    st.header("⚙️ Configuration")
    if not config:
        st.warning("Konfigurasi API belum ditemukan. Silakan isi .env atau gunakan Streamlit Secrets.")
    else:
        st.success("API Keys Loaded ✅")
        st.info(f"Language: {config['language']}")

# Form Input Utama
with st.container(border=True):
    lb_url = st.text_input("🔗 Letterboxd List URL", placeholder="https://letterboxd.com/username/list/my-list/")
    
    col1, col2 = st.columns(2)
    with col1:
        destination = st.selectbox("🎯 Destination", ["TMDB List", "Supabase Collection"])
    with col2:
        list_name_override = st.text_input("📝 Custom Name (Optional)", placeholder="Use Letterboxd Name")

    start_btn = st.button("🚀 Start Sync")

# ─────────────────────────────────────────────────────────
#  Sync Execution Logic
# ─────────────────────────────────────────────────────────

if start_btn:
    if not lb_url:
        st.error("Silakan masukkan URL Letterboxd terlebih dahulu.")
    elif not config:
        st.error("API Keys tidak ditemukan. Pastikan .env sudah diisi.")
    else:
        # Inisialisasi Clients
        tmdb_client = TMDBClient(
            api_read_token=config["access_token"],
            user_access_token=config["user_access_token"],
            language=config["language"],
        )
        
        # UI Progress & Containers
        status = st.status("⏳ Memulai proses...", expanded=True)
        progress_bar = st.progress(0)
        logs = st.container()

        try:
            # ── Step 1: Scrape ──────────────────────────
            status.update(label="📡 Mengambil data dari Letterboxd...", state="running")
            films, lb_list_name = scrape_list(lb_url, delay=config["scrape_delay"])
            tmdb_list_name = list_name_override or lb_list_name
            status.write(f"✅ Ditemukan **{len(films)}** film di Letterboxd: **{lb_list_name}**")
            
            # ── Step 2: Search ──────────────────────────
            status.update(label="🔍 Mencari film di TMDB...", state="running")
            found_movies = []
            not_found = []
            
            for i, film in enumerate(films):
                title = film.get("title", "Unknown")
                year = film.get("year")
                
                # Update UI
                progress_val = int(((i + 1) / len(films)) * 50) # 50% max for search phase
                progress_bar.progress(progress_val)
                status.write(f"🔎 Mencari: {title} ({year or '?'})")
                
                # Search process
                # Note: Untuk Streamlit, kita ambil metadata lengkap
                movie_data = tmdb_client.search_movie(title, year=year)
                if movie_data:
                    found_movies.append(movie_data)
                else:
                    not_found.append(title)
                
                time.sleep(0.1) # Small delay for smoother UI

            status.write(f"✅ Berhasil menemukan **{len(found_movies)}** film.")
            if not_found:
                status.write(f"⚠️ **{len(not_found)}** film tidak ditemukan.")

            # ── Step 3: Insert ──────────────────────────
            if not found_movies:
                status.update(label="❌ Gagal: Tidak ada film yang ditemukan.", state="error")
            else:
                if destination == "TMDB List":
                    status.update(label="📤 Menambahkan ke TMDB List...", state="running")
                    # Cek write access
                    if not tmdb_client.has_write_access:
                        status.update(label="🔒 Butuh Autentikasi TMDB", state="error")
                        st.info("TMDB membutuhkan User Access Token untuk menulis data. Silakan jalankan program CLI sekali untuk mendapatkan token.")
                    else:
                        list_id = tmdb_client.create_list(tmdb_list_name)
                        
                        def on_item_start(item):
                            ititle = item.get('title') or item.get('name')
                            status.write(f"➕ Menambahkan: {ititle}")
                            # update progress 50% -> 100%
                        
                        result = tmdb_client.add_items_to_list(list_id, found_movies, on_item_start=on_item_start)
                        progress_bar.progress(100)
                        status.update(label="✅ Berhasil ditambahkan ke TMDB!", state="complete")
                        st.balloons()
                        st.success(f"Sync Selesai! [Lihat di TMDB](https://www.themoviedb.org/list/{list_id})")

                else:
                    # Supabase
                    status.update(label="📤 Menambahkan ke Supabase...", state="running")
                    if not config["supabase_url"] or not config["supabase_key"]:
                        status.update(label="❌ Konfigurasi Supabase Error", state="error")
                    else:
                        sb_client = SupabaseClient(
                            url=config["supabase_url"],
                            key=config["supabase_key"],
                            user_id=config["supabase_user_id"]
                        )
                        collection_id = sb_client.create_collection(tmdb_list_name)
                        
                        # Simulasikan progres insertion di UI
                        for j, movie in enumerate(found_movies):
                            mtitle = movie.get('title') or movie.get('name')
                            status.write(f"💾 Menyimpan ke SB: {mtitle}")
                            progress_val = 50 + int(((j + 1) / len(found_movies)) * 50)
                            progress_bar.progress(progress_val)
                        
                        sb_client.add_items_to_collection(collection_id, found_movies)
                        status.update(label="✅ Berhasil disimpan ke Supabase!", state="complete")
                        st.balloons()
                        st.success(f"Sync Selesai! Collection ID: `{collection_id}`")

        except Exception as e:
            status.update(label=f"❌ Error Terjadi", state="error")
            st.error(f"Pesan Error: {str(e)}")

st.divider()
st.caption("Built with ❤️ using Streamlit & TMDB API")
