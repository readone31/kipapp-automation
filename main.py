"""
KipApp BPS Automation
GUI + Selenium automation for kipapp.bps.go.id
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import queue
import re
from datetime import date
from automation import KipAppAutomation, AutomationStopped

# ── Triwulan helper ──────────────────────────────────────────────────────────

def get_current_triwulan() -> str:
    m = date.today().month
    if m <= 3:
        return "Triwulan I"
    elif m <= 6:
        return "Triwulan II"
    elif m <= 9:
        return "Triwulan III"
    else:
        return "Triwulan IV"

TRIWULAN_OPTIONS = ["Triwulan I", "Triwulan II", "Triwulan III", "Triwulan IV"]

# ── Colour palette ───────────────────────────────────────────────────────────

BG         = "#0F1C2E"
PANEL      = "#162032"
CARD       = "#1E2D42"
ACCENT     = "#2E7BFF"
ACCENT_HOV = "#1A63E8"
SUCCESS    = "#22C55E"
WARNING    = "#F59E0B"
ERROR      = "#EF4444"
FG         = "#E8EDF4"
FG_DIM     = "#7A8BA0"
BORDER     = "#2A3A52"
INPUT_BG   = "#0D1520"

# ── App ──────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("KipApp BPS Automation")
        self.geometry("820x680")
        self.minsize(760, 600)
        self.configure(bg=BG)
        self.resizable(True, True)

        self.log_queue: queue.Queue = queue.Queue()
        self.automation: KipAppAutomation | None = None
        self._otp_event = threading.Event()
        self._otp_value = tk.StringVar()
        self._stop_event = threading.Event()

        self._build_styles()
        self._build_ui()
        self._poll_log()

    # ── ttk styles ────────────────────────────────────────────────────────

    def _build_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")

        s.configure("TNotebook",          background=BG,    borderwidth=0, tabmargins=0)
        s.configure("TNotebook.Tab",      background=PANEL, foreground=FG_DIM,
                    padding=[20, 10], font=("Segoe UI", 10, "bold"), borderwidth=0)
        s.map("TNotebook.Tab",
              background=[("selected", CARD), ("active", CARD)],
              foreground=[("selected", FG),   ("active", FG)])

        s.configure("TFrame",  background=CARD)
        s.configure("TLabel",  background=CARD, foreground=FG, font=("Segoe UI", 10))
        s.configure("TEntry",  fieldbackground=INPUT_BG, foreground=FG,
                    insertcolor=FG, borderwidth=1, relief="flat")
        s.configure("TCombobox", fieldbackground=INPUT_BG, foreground=FG,
                    background=INPUT_BG, arrowcolor=FG_DIM)
        s.map("TCombobox", fieldbackground=[("readonly", INPUT_BG)],
                           selectbackground=[("readonly", INPUT_BG)],
                           selectforeground=[("readonly", FG)])

    # ── UI skeleton ───────────────────────────────────────────────────────

    def _build_ui(self):
        # ── header
        hdr = tk.Frame(self, bg=PANEL, height=56)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="⚡ KipApp BPS Automation",
                 bg=PANEL, fg=FG, font=("Segoe UI", 14, "bold")).pack(side="left", padx=20)
        self._status_lbl = tk.Label(hdr, text="● Idle",
                                    bg=PANEL, fg=FG_DIM, font=("Segoe UI", 10))
        self._status_lbl.pack(side="right", padx=20)

        # ── notebook
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=0, pady=0)

        tab_main = ttk.Frame(nb, style="TFrame")
        tab_otp  = ttk.Frame(nb, style="TFrame")
        nb.add(tab_main, text="  Utama  ")
        nb.add(tab_otp,  text="  OTP  ")

        self._build_main_tab(tab_main)
        self._build_otp_tab(tab_otp)

        # ── log panel
        log_frame = tk.Frame(self, bg=PANEL, height=180)
        log_frame.pack(fill="x", side="bottom")
        log_frame.pack_propagate(False)

        tk.Label(log_frame, text="Log Aktivitas", bg=PANEL, fg=FG_DIM,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=12, pady=(6, 0))

        self.log_box = scrolledtext.ScrolledText(
            log_frame, height=8, bg=INPUT_BG, fg=FG_DIM,
            font=("Consolas", 9), relief="flat", bd=0,
            insertbackground=FG, state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=10, pady=(2, 8))
        self.log_box.tag_config("info",    foreground=FG_DIM)
        self.log_box.tag_config("success", foreground=SUCCESS)
        self.log_box.tag_config("warning", foreground=WARNING)
        self.log_box.tag_config("error",   foreground=ERROR)

    # ── Main tab ──────────────────────────────────────────────────────────

    def _build_main_tab(self, parent):
        canvas = tk.Canvas(parent, bg=CARD, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=CARD)

        scroll_frame.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        pad = {"padx": 28, "pady": 6}

        # ── section: Credentials
        self._section_header(scroll_frame, "🔐 Kredensial")

        self._field_var_user = tk.StringVar()
        self._field_var_pass = tk.StringVar()

        self._make_field(scroll_frame, "Username", self._field_var_user, **pad)
        self._make_field(scroll_frame, "Password",  self._field_var_pass,
                         show="•", **pad)

        # ── section: Spreadsheet
        self._section_header(scroll_frame, "📊 Spreadsheet")

        self._field_var_sheet = tk.StringVar()
        self._make_field(scroll_frame, "Tautan Google Spreadsheet / URL Excel",
                         self._field_var_sheet, width=64, **pad)

        # ── section: Periode
        self._section_header(scroll_frame, "📅 Periode")

        prow = tk.Frame(scroll_frame, bg=CARD)
        prow.pack(fill="x", **pad)
        tk.Label(prow, text="Periodik", bg=CARD, fg=FG_DIM,
                 font=("Segoe UI", 9)).pack(anchor="w")

        self._cbo_period = ttk.Combobox(prow, values=TRIWULAN_OPTIONS,
                                         state="readonly", width=24,
                                         font=("Segoe UI", 10))
        self._cbo_period.set(get_current_triwulan())
        self._cbo_period.pack(anchor="w", pady=(2, 0))

        # ── Run / Stop buttons
        tk.Frame(scroll_frame, bg=CARD, height=16).pack()
        btn_row = tk.Frame(scroll_frame, bg=CARD)
        btn_row.pack(padx=28, pady=(0, 24), fill="x")

        self._btn_run = self._make_button(
            btn_row, "▶  Jalankan Otomasi", self._on_run,
            bg=ACCENT, hover=ACCENT_HOV)
        self._btn_run.pack(side="left")

        self._btn_stop = self._make_button(
            btn_row, "⏹  Stop", self._on_stop,
            bg=ERROR, hover="#B91C1C")
        self._btn_stop.pack(side="left", padx=(10, 0))
        self._btn_stop.config(state="disabled")

    # ── OTP tab ───────────────────────────────────────────────────────────

    def _build_otp_tab(self, parent):
        wrapper = tk.Frame(parent, bg=CARD)
        wrapper.pack(fill="both", expand=True)

        center = tk.Frame(wrapper, bg=CARD)
        center.place(relx=0.5, rely=0.38, anchor="center")

        tk.Label(center, text="🔑 Masukkan OTP", bg=CARD, fg=FG,
                 font=("Segoe UI", 14, "bold")).pack(pady=(0, 4))
        tk.Label(center, text="OTP akan diperlukan jika login membutuhkan verifikasi.",
                 bg=CARD, fg=FG_DIM, font=("Segoe UI", 9)).pack(pady=(0, 16))

        entry_frame = tk.Frame(center, bg=BORDER, bd=0)
        entry_frame.pack()
        self._entry_otp = tk.Entry(entry_frame, textvariable=self._otp_value,
                                   font=("Consolas", 22, "bold"), width=10,
                                   bg=INPUT_BG, fg=FG, insertbackground=FG,
                                   justify="center", relief="flat", bd=10)
        self._entry_otp.pack()

        self._btn_otp = self._make_button(
            center, "✔  Submit OTP", self._on_otp_submit,
            bg="#16A34A", hover="#15803D")
        self._btn_otp.pack(pady=(16, 0))
        self._btn_otp.config(state="disabled")

        self._otp_hint = tk.Label(center, text="Tombol aktif saat program membutuhkan OTP.",
                                  bg=CARD, fg=FG_DIM, font=("Segoe UI", 9, "italic"))
        self._otp_hint.pack(pady=(8, 0))

    # ── Widget helpers ────────────────────────────────────────────────────

    def _section_header(self, parent, text: str):
        f = tk.Frame(parent, bg=CARD)
        f.pack(fill="x", padx=20, pady=(18, 2))
        tk.Label(f, text=text, bg=CARD, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Frame(f, bg=BORDER, height=1).pack(side="left", fill="x",
                                               expand=True, padx=(10, 0))

    def _make_field(self, parent, label: str, var: tk.StringVar,
                    show: str = "", width: int = 40, **kw):
        f = tk.Frame(parent, bg=CARD)
        f.pack(fill="x", **kw)
        tk.Label(f, text=label, bg=CARD, fg=FG_DIM,
                 font=("Segoe UI", 9)).pack(anchor="w")
        e = tk.Entry(f, textvariable=var, show=show, width=width,
                     bg=INPUT_BG, fg=FG, insertbackground=FG,
                     relief="flat", bd=6, font=("Segoe UI", 10))
        e.pack(anchor="w", pady=(2, 0))
        return e

    def _make_button(self, parent, text: str, cmd, bg: str, hover: str) -> tk.Button:
        btn = tk.Button(parent, text=text, command=cmd,
                        bg=bg, fg="white", activebackground=hover,
                        activeforeground="white", relief="flat", bd=0,
                        font=("Segoe UI", 11, "bold"), cursor="hand2",
                        padx=28, pady=10)
        btn.bind("<Enter>", lambda _: btn.config(bg=hover))
        btn.bind("<Leave>", lambda _: btn.config(bg=bg))
        return btn

    # ── Actions ───────────────────────────────────────────────────────────

    def _on_run(self):
        username = self._field_var_user.get().strip()
        password = self._field_var_pass.get().strip()
        sheet_url = self._field_var_sheet.get().strip()
        period    = self._cbo_period.get()

        if not username or not password:
            messagebox.showwarning("Peringatan", "Username dan password wajib diisi.")
            return
        if not sheet_url:
            messagebox.showwarning("Peringatan", "Tautan spreadsheet wajib diisi.")
            return

        self._btn_run.config(state="disabled", text="⏳  Menjalankan...")
        self._btn_stop.config(state="normal")
        self._stop_event.clear()
        self._set_status("● Berjalan...", WARNING)
        self.log("info", f"Memulai otomasi — Periode: {period}")

        thread = threading.Thread(
            target=self._run_automation,
            args=(username, password, sheet_url, period),
            daemon=True)
        thread.start()

    def _run_automation(self, username, password, sheet_url, period):
        try:
            self.automation = KipAppAutomation(
                username=username,
                password=password,
                sheet_url=sheet_url,
                period=period,
                log_fn=self.log,
                request_otp_fn=self._request_otp,
                stop_event=self._stop_event,
            )
            self.automation.run()
            self.log("success", "✔ Otomasi selesai.")
            self._set_status("● Selesai", SUCCESS)
        except AutomationStopped:
            self.log("warning", "⏹ Otomasi dihentikan oleh pengguna.")
            self._set_status("● Dihentikan", WARNING)
        except Exception as exc:
            self.log("error", f"✘ Error: {exc}")
            self._set_status("● Error", ERROR)
        finally:
            self.after(0, lambda: self._btn_run.config(
                state="normal", text="▶  Jalankan Otomasi"))
            self.after(0, lambda: self._btn_stop.config(state="disabled", text="⏹  Stop"))
            self.after(0, lambda: self._btn_otp.config(state="disabled"))

    def _on_stop(self):
        if not self.automation:
            return
        if not messagebox.askyesno(
                "Konfirmasi Stop",
                "Hentikan proses otomasi yang sedang berjalan sekarang?"):
            return
        self._btn_stop.config(state="disabled", text="⏳  Menghentikan...")
        self.log("warning", "Menghentikan otomasi…")
        # request_stop() menutup driver dari thread ini; dijalankan di thread
        # terpisah supaya GUI tidak freeze jika driver.quit() sempat lambat.
        threading.Thread(target=self.automation.request_stop, daemon=True).start()
        # Kalau automation sedang menunggu OTP, lepaskan blocking-nya juga.
        self._otp_event.set()

    def _request_otp(self) -> str:
        """Called from automation thread — enables OTP button, waits for submission."""
        self.log("warning", "⚠ Dibutuhkan OTP. Silakan isi di tab OTP lalu klik Submit.")
        self._otp_event.clear()
        self.after(0, lambda: self._btn_otp.config(state="normal"))
        self.after(0, lambda: self._otp_hint.config(
            text="Masukkan OTP dan klik Submit.", fg=WARNING))
        self._otp_event.wait()   # blocks automation thread
        otp = self._otp_value.get().strip()
        self.after(0, lambda: self._btn_otp.config(state="disabled"))
        return otp

    def _on_otp_submit(self):
        otp = self._otp_value.get().strip()
        if not otp:
            messagebox.showwarning("Peringatan", "Masukkan kode OTP terlebih dahulu.")
            return
        self.log("info", f"OTP dikirim: {'*' * len(otp)}")
        self._otp_event.set()

    # ── Status / log ──────────────────────────────────────────────────────

    def _set_status(self, text: str, colour: str):
        self.after(0, lambda: self._status_lbl.config(text=text, fg=colour))

    def log(self, level: str, message: str):
        self.log_queue.put((level, message))

    def _poll_log(self):
        try:
            while True:
                level, msg = self.log_queue.get_nowait()
                self.log_box.config(state="normal")
                ts = date.today().strftime("%H:%M:%S")  # approximate
                self.log_box.insert("end", f"[{ts}] {msg}\n", level)
                self.log_box.see("end")
                self.log_box.config(state="disabled")
        except queue.Empty:
            pass
        self.after(200, self._poll_log)


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()
