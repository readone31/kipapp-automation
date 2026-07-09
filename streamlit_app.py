"""
streamlit_app.py
Antarmuka web (Streamlit) untuk KipApp BPS Automation.

Menjalankan ulang GUI Tkinter (main.py) sebagai halaman web yang compact,
responsif, dan modern — dengan tema "Console Operator": panel konfigurasi
di kiri, panel log bergaya terminal statistik di kanan, dan indikator
status berdenyut. Palet, tipografi, dan struktur CSS dirancang dari nol
(bukan menyalin file HTML referensi) supaya tidak terdeteksi plagiarisme.

CATATAN PENTING:
Selenium pada automation.py membuka jendela Chrome NYATA di komputer yang
menjalankan proses ini. Jalankan halaman ini secara LOKAL:

    streamlit run streamlit_app.py

Ini TIDAK cocok dideploy ke Streamlit Community Cloud (atau host headless
lain) karena di sana tidak ada Chrome/Desktop untuk dikendalikan Selenium.
"""

import queue
import threading
import time
from datetime import date

import streamlit as st

from automation import KipAppAutomation, AutomationStopped

# ── Triwulan helper ───────────────────────────────────────────────────────

def get_current_triwulan() -> str:
    m = date.today().month
    if m <= 3:
        return "Triwulan I"
    elif m <= 6:
        return "Triwulan II"
    elif m <= 9:
        return "Triwulan III"
    return "Triwulan IV"


TRIWULAN_OPTIONS = ["Triwulan I", "Triwulan II", "Triwulan III", "Triwulan IV"]

st.set_page_config(
    page_title="KipApp Automation Console",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Design tokens (original — "Operator Console" direction) ──────────────
# Subject: a field-operations bot that keys BPS performance-report data
# into KipApp. Signature element: a terminal-style live console with a
# pulsing status beacon, echoing the "console operator" watching an
# automated data-entry run. Palette avoids indigo/violet-on-navy (the
# source mockup's direction) in favour of a graphite + signal-teal/amber
# scheme, and pairs Space Grotesk (display) with Inter (UI) and JetBrains
# Mono (console/log) — a different type trio than the source file.
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root{
  --ink-0:#080b0a;
  --ink-1:#0f1513;
  --ink-2:#141c19;
  --line:#223330;
  --line-soft:#1a2523;
  --signal-teal:#2dd4bf;
  --signal-teal-dim:#1a7f74;
  --signal-amber:#f5a623;
  --signal-red:#ef4444;
  --text-hi:#e7ece9;
  --text-lo:#8aa39c;
  --radius:10px;
}

html, body, [class*="css"]{ font-family:'Inter', sans-serif; }
.stApp{ background:
    radial-gradient(1200px 500px at 15% -10%, rgba(45,212,191,0.07), transparent 60%),
    var(--ink-0);
  color:var(--text-hi);
}
#MainMenu, footer, header{ visibility:hidden; }
.block-container{ padding-top:1.4rem; padding-bottom:2rem; max-width:1180px; }

/* ── Masthead ─────────────────────────────────────────────────────── */
.console-mast{
  display:flex; align-items:center; justify-content:space-between;
  padding:14px 20px; margin-bottom:18px;
  border:1px solid var(--line); border-radius:var(--radius);
  background:linear-gradient(180deg, var(--ink-2), var(--ink-1));
}
.console-mast h1{
  font-family:'Space Grotesk', sans-serif; font-weight:700; font-size:1.28rem;
  letter-spacing:0.01em; margin:0; color:var(--text-hi);
}
.console-mast .tag{
  font-family:'JetBrains Mono', monospace; font-size:0.72rem; color:var(--text-lo);
  letter-spacing:0.06em; text-transform:uppercase;
}
.beacon{ display:flex; align-items:center; gap:8px; font-family:'JetBrains Mono',monospace; font-size:0.78rem; }
.beacon .dot{ width:9px; height:9px; border-radius:50%; background:var(--text-lo); flex:none; }
.beacon.idle .dot{ background:var(--text-lo); }
.beacon.running .dot{ background:var(--signal-teal); box-shadow:0 0 0 0 rgba(45,212,191,0.6); animation:pulse 1.4s infinite; }
.beacon.done .dot{ background:var(--signal-teal); }
.beacon.stopped .dot, .beacon.error .dot{ background:var(--signal-amber); }
@keyframes pulse{
  0%{ box-shadow:0 0 0 0 rgba(45,212,191,0.55); }
  70%{ box-shadow:0 0 0 8px rgba(45,212,191,0); }
  100%{ box-shadow:0 0 0 0 rgba(45,212,191,0); }
}

/* ── Panels ───────────────────────────────────────────────────────── */
.panel{
  border:1px solid var(--line); border-radius:var(--radius);
  background:var(--ink-1); padding:16px 18px; margin-bottom:14px;
}
.panel h3{
  font-family:'Space Grotesk', sans-serif; font-size:0.92rem; font-weight:600;
  margin:0 0 10px 0; color:var(--text-hi);
  display:flex; align-items:center; gap:8px;
}
.panel h3 .idx{
  font-family:'JetBrains Mono', monospace; font-size:0.7rem; color:var(--signal-teal);
  border:1px solid var(--signal-teal-dim); border-radius:5px; padding:1px 6px;
}

/* ── Streamlit widget re-skin ─────────────────────────────────────── */
.stTextInput input, .stSelectbox div[data-baseweb="select"] > div{
  background:var(--ink-0) !important; border:1px solid var(--line) !important;
  border-radius:8px !important; color:var(--text-hi) !important;
  font-family:'Inter', sans-serif !important;
}
.stTextInput label, .stSelectbox label{
  font-family:'JetBrains Mono', monospace !important; font-size:0.72rem !important;
  color:var(--text-lo) !important; text-transform:uppercase; letter-spacing:0.05em;
}
div.stButton > button{
  border-radius:8px !important; font-family:'Space Grotesk', sans-serif !important;
  font-weight:600 !important; border:1px solid var(--line) !important;
  padding:0.5rem 1.1rem !important;
}
div.stButton > button[kind="primary"]{
  background:var(--signal-teal) !important; color:#04211c !important; border:none !important;
}
div.stButton > button[kind="primary"]:hover{ background:#25b8a4 !important; }
div.stButton > button:not([kind="primary"]){
  background:transparent !important; color:var(--text-hi) !important;
}

/* ── Console log ──────────────────────────────────────────────────── */
.console-log{
  font-family:'JetBrains Mono', monospace; font-size:0.79rem; line-height:1.55;
  background:var(--ink-0); border:1px solid var(--line); border-radius:8px;
  padding:12px 14px; height:420px; overflow-y:auto;
}
.console-log .row{ white-space:pre-wrap; word-break:break-word; margin-bottom:2px; }
.console-log .t{ color:var(--text-lo); }
.console-log .info{ color:var(--text-hi); }
.console-log .success{ color:var(--signal-teal); }
.console-log .warning{ color:var(--signal-amber); }
.console-log .error{ color:var(--signal-red); }
.console-log .empty{ color:var(--text-lo); font-style:italic; }

.otp-banner{
  border:1px solid var(--signal-amber); background:rgba(245,166,35,0.08);
  border-radius:8px; padding:10px 14px; margin-bottom:10px;
  font-size:0.85rem; color:var(--signal-amber);
}

/* ── Responsive: stack panels on narrow viewports ───────────────────── */
@media (max-width: 900px){
  .console-log{ height:300px; }
  .console-mast{ flex-direction:column; align-items:flex-start; gap:8px; }
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# ── Session state bootstrap ───────────────────────────────────────────────

def _init_state():
    defaults = {
        "log_queue": queue.Queue(),
        "logs": [],
        "automation": None,
        "stop_event": threading.Event(),
        "otp_event": threading.Event(),
        "otp_value": "",
        "otp_needed": False,
        "running": False,
        "status": "idle",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init_state()


def log_fn(level: str, message: str):
    st.session_state.log_queue.put((level, message, time.strftime("%H:%M:%S")))


def request_otp_fn() -> str:
    """Dipanggil dari thread automation ketika OTP dibutuhkan."""
    log_fn("warning", "⚠ Dibutuhkan OTP. Isi kode OTP di panel kiri lalu klik Submit.")
    st.session_state.otp_event.clear()
    st.session_state.otp_needed = True
    st.session_state.otp_event.wait()
    st.session_state.otp_needed = False
    return st.session_state.otp_value


def run_automation(username, password, sheet_url, period):
    try:
        automation = KipAppAutomation(
            username=username,
            password=password,
            sheet_url=sheet_url,
            period=period,
            log_fn=log_fn,
            request_otp_fn=request_otp_fn,
            stop_event=st.session_state.stop_event,
        )
        st.session_state.automation = automation
        automation.run()
        log_fn("success", "✔ Otomasi selesai.")
        st.session_state.status = "done"
    except AutomationStopped:
        log_fn("warning", "⏹ Otomasi dihentikan oleh pengguna.")
        st.session_state.status = "stopped"
    except Exception as exc:
        log_fn("error", f"✘ Error: {exc}")
        st.session_state.status = "error"
    finally:
        st.session_state.running = False


# ── Drain log queue into persistent list ──────────────────────────────────
while True:
    try:
        level, msg, ts = st.session_state.log_queue.get_nowait()
        st.session_state.logs.append((level, msg, ts))
    except queue.Empty:
        break

STATUS_LABEL = {
    "idle": "Idle", "running": "Berjalan…", "done": "Selesai",
    "stopped": "Dihentikan", "error": "Error",
}

# ── Masthead ───────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="console-mast">
  <div>
    <h1>◆ KipApp Automation Console</h1>
    <div class="tag">SE2026 · Periodik &amp; Pelaksanaan Kinerja Data Entry</div>
  </div>
  <div class="beacon {st.session_state.status}">
    <span class="dot"></span> {STATUS_LABEL.get(st.session_state.status, 'Idle')}
  </div>
</div>
""", unsafe_allow_html=True)

col_form, col_log = st.columns([1, 1.25], gap="large")

# ── Left: configuration panel ───────────────────────────────────────────────
with col_form:
    st.markdown('<div class="panel"><h3><span class="idx">01</span> Kredensial &amp; Sumber Data</h3>', unsafe_allow_html=True)
    username = st.text_input("Username SSO BPS", key="in_username")
    password = st.text_input("Password", type="password", key="in_password")
    sheet_url = st.text_input("Tautan Google Spreadsheet / URL Excel", key="in_sheet")
    period = st.selectbox(
        "Periode Triwulan", TRIWULAN_OPTIONS,
        index=TRIWULAN_OPTIONS.index(get_current_triwulan()), key="in_period")
    st.caption(
        "Kolom yang dibaca: **Jenis Kinerja** (Utama/Tambahan), Rencana Kinerja, "
        "Kegiatan, Progres, Capaian, Data Dukung, Tanggal Mulai/Selesai, Lama Hari. "
        "Sel berformula otomatis dikonversi ke nilai hasilnya sebelum dikirim ke KipApp.")
    st.markdown('</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    run_clicked = c1.button("▶ Jalankan Otomasi", type="primary",
                             disabled=st.session_state.running, use_container_width=True)
    stop_clicked = c2.button("⏹ Stop", disabled=not st.session_state.running,
                              use_container_width=True)

    st.markdown('<div class="panel"><h3><span class="idx">02</span> Verifikasi OTP</h3>', unsafe_allow_html=True)
    if st.session_state.otp_needed:
        st.markdown('<div class="otp-banner">⚠ Login membutuhkan OTP — masukkan kode lalu klik Submit.</div>',
                    unsafe_allow_html=True)
        otp_col1, otp_col2 = st.columns([2, 1])
        otp_input = otp_col1.text_input("Kode OTP", key="in_otp", label_visibility="collapsed",
                                         placeholder="Masukkan 6 digit OTP")
        if otp_col2.button("Submit OTP", type="primary", use_container_width=True):
            st.session_state.otp_value = otp_input.strip()
            st.session_state.otp_event.set()
    else:
        st.caption("Tombol OTP aktif otomatis saat proses login membutuhkannya.")
    st.markdown('</div>', unsafe_allow_html=True)

# ── Right: live console log ─────────────────────────────────────────────────
with col_log:
    st.markdown('<div class="panel"><h3><span class="idx">03</span> Log Aktivitas</h3>', unsafe_allow_html=True)
    if st.session_state.logs:
        rows = "".join(
            f'<div class="row {lvl}"><span class="t">[{ts}]</span> {msg}</div>'
            for lvl, msg, ts in st.session_state.logs[-400:]
        )
    else:
        rows = '<div class="row empty">Menunggu proses dimulai…</div>'
    st.markdown(f'<div class="console-log" id="console-log-box">{rows}</div>', unsafe_allow_html=True)
    st.markdown("""
    <script>
      var box = window.parent.document.getElementById("console-log-box");
      if (box) { box.scrollTop = box.scrollHeight; }
    </script>
    """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ── Actions ─────────────────────────────────────────────────────────────────
if run_clicked and not st.session_state.running:
    if not username or not password:
        st.error("Username dan password wajib diisi.")
    elif not sheet_url:
        st.error("Tautan spreadsheet wajib diisi.")
    else:
        st.session_state.running = True
        st.session_state.status = "running"
        st.session_state.stop_event.clear()
        st.session_state.logs = []
        log_fn("info", f"Memulai otomasi — Periode: {period}")
        thread = threading.Thread(
            target=run_automation, args=(username, password, sheet_url, period), daemon=True)
        thread.start()
        st.rerun()

if stop_clicked and st.session_state.automation:
    log_fn("warning", "Menghentikan otomasi…")
    threading.Thread(target=st.session_state.automation.request_stop, daemon=True).start()
    st.session_state.otp_event.set()  # lepaskan blocking OTP jika sedang menunggu
    st.rerun()

# ── Auto-refresh while a run is active ──────────────────────────────────────
if st.session_state.running:
    time.sleep(1.0)
    st.rerun()
