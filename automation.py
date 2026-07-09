"""
automation.py
Core Selenium automation for kipapp.bps.go.id
Semua XPath disesuaikan dengan struktur DOM aktual situs.
"""

import time
import re
import random
import threading
from collections import defaultdict
from datetime import date
from typing import Callable

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (
    TimeoutException, ElementClickInterceptedException, NoSuchElementException,
    StaleElementReferenceException,
)
try:
    from webdriver_manager.chrome import ChromeDriverManager
    HAS_WDM = True
except ImportError:
    HAS_WDM = False

from spreadsheet_reader import load_spreadsheet

# ── Constants ────────────────────────────────────────────────────────────────

BASE_URL  = "https://kipapp.bps.go.id"
HOME_HASH = "#/home"
TIMEOUT   = 20
LONG_WAIT = 40

# Mapping triwulan → teks opsi dropdown Periode SKP di situs
PERIODE_SKP_LABEL = {
    "Triwulan I":   "1 Januari - 31 Maret",
    "Triwulan II":  "1 April - 30 Juni",
    "Triwulan III": "1 Juli - 30 September",
    "Triwulan IV":  "1 Oktober - 31 Desember",
}

def _triwulan_index() -> int:
    m = date.today().month
    return (m - 1) // 3 + 1


class AutomationStopped(Exception):
    """Dilempar ketika pengguna menekan tombol Stop (paksa)."""
    pass


# ── Automation class ──────────────────────────────────────────────────────────

class KipAppAutomation:
    def __init__(
        self,
        username: str,
        password: str,
        sheet_url: str,
        period: str,
        log_fn: Callable[[str, str], None],
        request_otp_fn: Callable[[], str],
        stop_event: threading.Event | None = None,
    ):
        self.username    = username
        self.password    = password
        self.sheet_url   = sheet_url
        self.period      = period          # e.g. "Triwulan II"
        self.log         = log_fn
        self.request_otp = request_otp_fn
        self.driver: webdriver.Chrome | None = None
        self.rows:   list[dict]              = []
        # Event yang di-set dari luar (GUI) saat tombol Stop ditekan.
        self.stop_event: threading.Event = stop_event or threading.Event()

    # ── Stop paksa ────────────────────────────────────────────────────────

    def _check_stop(self):
        """Panggil di titik-titik aman (antar step/iterasi) untuk keluar
        lebih awal jika pengguna menekan Stop."""
        if self.stop_event.is_set():
            raise AutomationStopped("Otomasi dihentikan paksa oleh pengguna.")

    def request_stop(self):
        """Dipanggil dari thread GUI. Set flag berhenti DAN langsung tutup
        browser, sehingga operasi Selenium yang sedang blocking (klik,
        menunggu elemen, dll) langsung gagal dan proses berhenti seketika —
        tidak menunggu iterasi/step saat ini selesai."""
        self.stop_event.set()
        self.log("warning", "⏹ Perintah Stop diterima — menghentikan paksa…")
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass

    # ── Entry point ───────────────────────────────────────────────────────

    def run(self):
        try:
            self._load_spreadsheet()
            self._check_stop()
            self._start_driver()
            self._check_stop()
            self._step1_login()
            self._check_stop()
            self._step4_close_popups()
            self._check_stop()
            self._step5_to_periodik()
            self._check_stop()
            self._step6_check_and_add_periodik()
            self._check_stop()
            self._step8b_add_rencana_kinerja_tambahan()
            self._check_stop()
            self._step9_to_pelaksanaan()
            self._check_stop()
            self._step10_to_14_fill_pelaksanaan()
        except AutomationStopped as e:
            self.log("warning", f"⏹ {e}")
            raise
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass

    # ── Setup ─────────────────────────────────────────────────────────────

    def _load_spreadsheet(self):
        self.log("info", "Memuat data spreadsheet…")
        self.rows = load_spreadsheet(self.sheet_url, log_fn=self.log)
        if not self.rows:
            raise RuntimeError("Spreadsheet kosong atau tidak dapat dibaca.")

        # ── Diagnostik nilai per baris ────────────────────────────────────
        self.log("info", f"Total baris terbaca: {len(self.rows)}")
        for i, row in enumerate(self.rows, start=1):
            jk  = row.get("jenis_kinerja", "").strip()
            rk  = row.get("rencana_kinerja", "").strip()
            keg = row.get("kegiatan", "").strip()
            prg = row.get("progres", "").strip()
            lh  = row.get("lama_hari", "").strip()
            tgl = row.get("tanggal_mulai", "").strip()
            if not rk:
                self.log("warning",
                    f"  Baris {i}: kolom 'rencana_kinerja' KOSONG — "
                    f"periksa nama kolom di spreadsheet. "
                    f"Key tersedia: {list(row.keys())}")
            else:
                self.log("info",
                    f"  Baris {i}: Jenis='{jk or 'Utama'}' | RK='{rk}' | Kegiatan='{keg[:30]}' | "
                    f"Progres='{prg}' | LH='{lh}' | Tgl='{tgl}'"
                )

def _start_driver(self):
    import os
    self.log("info", "Memulai browser Chrome…")

    opts = Options()
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--disable-popup-blocking")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-infobars")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
    opts.add_experimental_option(
        "excludeSwitches", ["enable-logging", "enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    # Deteksi environment: Linux server vs Windows lokal
    if os.path.exists("/usr/bin/chromium"):
        # Streamlit Cloud / Linux — gunakan Chromium sistem
        self.log("info", "Mode server Linux (Chromium)…")
        opts.add_argument("--headless=new")
        opts.binary_location = "/usr/bin/chromium"
        from selenium.webdriver.chrome.service import Service
        service = Service("/usr/bin/chromedriver")
        self.driver = webdriver.Chrome(service=service, options=opts)
    elif os.path.exists("/usr/bin/google-chrome"):
        # Render / Railway
        self.log("info", "Mode server Linux (Chrome)…")
        opts.add_argument("--headless=new")
        from selenium.webdriver.chrome.service import Service
        service = Service("/usr/bin/chromedriver")
        self.driver = webdriver.Chrome(service=service, options=opts)
    else:
        # Lokal Windows/Mac — webdriver-manager otomatis
        self.log("info", "Mode lokal — webdriver-manager…")
        if HAS_WDM:
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.chrome.service import Service
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=opts)
        else:
            self.driver = webdriver.Chrome(options=opts)

    self.driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
            Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
            Object.defineProperty(navigator,'languages',
                {get:()=>['id-ID','id','en-US','en']});
            window.chrome = { runtime: {} };
        """
    })
    self.driver.set_page_load_timeout(60)
    self.driver.set_script_timeout(30)
    self.log("success", "Browser berhasil dibuka.")

    # ── Low-level helpers ─────────────────────────────────────────────────

    def _find(self, xpath: str, timeout: float = TIMEOUT):
        return WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, xpath)))

    def _clickable(self, xpath: str, timeout: float = TIMEOUT):
        return WebDriverWait(self.driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, xpath)))

    def _scroll_into_view(self, el):
        """Scroll elemen ke dalam viewport agar bisa diinteraksi."""
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block:'center', inline:'center'});", el)
        time.sleep(random.uniform(0.15, 0.35))

    def _safe_click(self, el):
        """Klik dengan 3 lapis fallback: scroll → klik biasa → JS click → Actions click."""
        self._scroll_into_view(el)
        try:
            el.click()
            return
        except ElementClickInterceptedException:
            pass
        except Exception:
            pass
        # Fallback 1: JS click (menembus elemen yang menghalangi)
        try:
            self.driver.execute_script("arguments[0].click();", el)
            return
        except Exception:
            pass
        # Fallback 2: ActionChains move + click (untuk elemen di luar area biasa)
        try:
            from selenium.webdriver.common.action_chains import ActionChains
            ActionChains(self.driver).move_to_element(el).click().perform()
        except Exception as e:
            self.log("warning", f"_safe_click semua fallback gagal: {e}")

    def _click_xpath(self, xpath: str, timeout: float = TIMEOUT):
        el = self._clickable(xpath, timeout)
        self._safe_click(el)
        return el

    def _try_click(self, xpath: str, label: str, timeout: float = 5) -> bool:
        """Klik elemen jika ada dan visible. Return True jika berhasil, False jika tidak ada."""
        try:
            el = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, xpath)))
            if el.is_displayed():
                self._safe_click(el)
                self.log("info", f"{label} diklik.")
                self._sleep(0.6)
                return True
        except Exception:
            pass
        return False

    def _wait_interactable(self, el, timeout: float = 10):
        """Tunggu hingga elemen enabled, visible, DAN tidak tertutup elemen lain."""
        import time as _time
        deadline = _time.time() + timeout
        while _time.time() < deadline:
            try:
                if el.is_displayed() and el.is_enabled():
                    # Scroll ke elemen dan pastikan posisinya sudah di viewport
                    self._scroll_into_view(el)
                    return True
            except Exception:
                pass
            _time.sleep(0.2)
        return False

    def _type(self, el, text: str, clear: bool = True):
        """Ketik teks karakter per karakter dengan jeda acak.
        Pastikan elemen interactable sebelum disentuh."""
        self._wait_interactable(el)
        try:
            if clear:
                # Gunakan JS clear lebih aman daripada el.clear() pada elemen read-only sementara
                self.driver.execute_script("arguments[0].value = '';", el)
                el.click()
                time.sleep(random.uniform(0.1, 0.3))
        except Exception:
            pass
        for ch in text:
            el.send_keys(ch)
            time.sleep(random.uniform(0.04, 0.14))

    def _sleep(self, sec: float = 1.0):
        """Tidur dengan jitter acak kecil agar pola tidak terlalu mekanis."""
        jitter = random.uniform(-0.15, 0.25)
        time.sleep(max(0.05, sec + jitter))

    def _human_sleep(self, lo: float = 0.8, hi: float = 2.2):
        """Delay acak menyerupai kecepatan manusia."""
        time.sleep(random.uniform(lo, hi))

    def _wait_url_contains(self, fragment: str, timeout: float = LONG_WAIT):
        WebDriverWait(self.driver, timeout).until(EC.url_contains(fragment))

    def _debug_dump(self, tag: str, scope_xpath: str | None = None, scope_element=None):
        """Simpan screenshot + HTML mentah untuk diagnostik saat sebuah step
        gagal menemukan elemen.

        - Jika `scope_element` diberikan (WebElement yang SUDAH diketahui
          benar, misal hasil dari `_wait_visible_modal`), HTML dibatasi ke
          elemen itu saja — cara paling dianjurkan karena tidak bergantung
          pada tebakan XPath lagi.
        - Jika hanya `scope_xpath` yang diberikan, dicoba `find_element`
          dengan xpath tsb (bisa salah tangkap kalau ada elemen lain yang
          cocok tapi tersembunyi).
        - Jika keduanya gagal/tidak ada, fallback ke modal/drawer AntD yang
          BENAR-BENAR tampil (dicek via is_displayed(), bukan sekadar class
          'ant-modal-hidden' — situs ini menyembunyikan modal lain, mis.
          modal tutorial "KipApp Work Flow", lewat inline style
          'display:none' saja tanpa class tsb, jadi filter class-only
          pernah salah menangkap modal yang salah).
        - Kalau semua di atas gagal, baru fallback ke seluruh page_source.

        Pemakaian: panggil ini di blok except/warning setiap kali sebuah
        selector "tebakan" gagal, supaya pengguna bisa mengirim bukti nyata
        dan XPath berikutnya bisa dipastikan dari DOM sebenarnya, bukan
        tebakan lagi."""
        try:
            import os
            debug_dir = os.path.join(os.getcwd(), "debug_steps")
            os.makedirs(debug_dir, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            safe_tag = re.sub(r"[^a-zA-Z0-9]+", "_", tag)[:40]

            shot_path = os.path.join(debug_dir, f"{ts}_{safe_tag}.png")
            self.driver.save_screenshot(shot_path)

            html = None

            if scope_element is not None:
                try:
                    if scope_element.is_displayed():
                        html = scope_element.get_attribute("outerHTML")
                except Exception:
                    html = None

            if html is None and scope_xpath:
                try:
                    el = self.driver.find_element(By.XPATH, scope_xpath)
                    if el.is_displayed():
                        html = el.get_attribute("outerHTML")
                except Exception:
                    html = None

            if html is None:
                # Coba batasi ke modal/drawer AntD yang BENAR-BENAR tampil
                # di layar (is_displayed() == True), bukan hanya berdasarkan
                # class, supaya tidak salah menangkap modal lain yang ada
                # di DOM tapi disembunyikan via inline style.
                try:
                    wraps = self.driver.find_elements(
                        By.XPATH,
                        "//div[contains(@class,'ant-modal-wrap')] | "
                        "//div[contains(@class,'ant-drawer-open')]")
                    for el in wraps:
                        try:
                            if el.is_displayed():
                                html = el.get_attribute("outerHTML")
                                break
                        except Exception:
                            continue
                except Exception:
                    pass

            if html is None:
                html = self.driver.page_source

            html_path = os.path.join(debug_dir, f"{ts}_{safe_tag}.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)

            self.log("warning",
                f"  Bukti debug disimpan: {shot_path} dan {html_path} "
                f"— kirimkan kedua file ini untuk analisis lebih lanjut.")
        except Exception as e2:
            self.log("warning", f"  Gagal menyimpan bukti debug: {e2}")

    def _wait_visible_modal(self, timeout: float = 8,
                             tag_on_fail: str | None = None):
        """Tunggu & kembalikan WebElement 'ant-modal-wrap' yang BENAR-BENAR
        tampil di layar (is_displayed() == True).

        PENTING (ditemukan dari bukti debug pengguna): situs ini SELALU
        menaruh modal lain di DOM secara bersamaan — misalnya modal
        tutorial "KipApp Work Flow" — lengkap dengan class 'ant-modal',
        tapi disembunyikan lewat inline style 'display:none' pada
        'ant-modal-mask'/'ant-modal-wrap'/'ant-modal', BUKAN lewat class
        'ant-modal-hidden'. Karena itu XPath lama yang hanya memfilter
        `not(contains(@class,'ant-modal-hidden'))` justru menangkap modal
        tutorial yang tersembunyi itu alih-alih modal "Edit Status Rencana
        Kinerja" (atau modal Add) yang sebenarnya sedang tampil — sehingga
        semua pencarian tombol Checklist/Save di dalamnya gagal terus
        ("checklist_button_not_found").

        Solusi: iterasi SEMUA '.ant-modal-wrap' yang ada di DOM dan pilih
        yang benar-benar `is_displayed()`.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                wraps = self.driver.find_elements(
                    By.XPATH, "//div[contains(@class,'ant-modal-wrap')]")
                for wrap in wraps:
                    try:
                        if wrap.is_displayed():
                            return wrap
                    except StaleElementReferenceException:
                        continue
            except Exception:
                pass
            time.sleep(0.2)

        self.log("warning", "  Tidak ada modal yang benar-benar tampil ditemukan.")
        if tag_on_fail:
            self._debug_dump(tag_on_fail)
        return None

    def _dismiss_stray_pickers(self):
        """Blur elemen yang sedang fokus (kalau ada) untuk menutup popup
        kalender AntD yang mungkin masih terbuka dari iterasi sebelumnya —
        misalnya kalau proses sebelumnya berhenti di tengah jalan sebelum
        sempat memanggil blur() sendiri. Dipanggil secara defensif SEBELUM
        setiap klik tombol "+ Add" supaya popup yang tersisa tidak
        menghalangi klik tombol tersebut.

        SENGAJA tidak memakai Keys.ESCAPE (lihat catatan panjang di
        `_set_datepicker_single`) karena itu akan menutup ant-modal, bukan
        cuma popup kalendernya."""
        try:
            self.driver.execute_script(
                "if (document.activeElement && document.activeElement !== "
                "document.body) { document.activeElement.blur(); }")
            self._sleep(0.2)
        except Exception:
            pass

    def _force_close_modal(self, modal):
        """Coba tutup sebuah modal secara paksa (klik tombol X / Cancel)
        supaya state-nya tidak membocori atau memblokir iterasi
        berikutnya — misalnya ketika Save gagal karena validasi dan modal
        tetap terbuka. SENGAJA tidak memakai Keys.ESCAPE (lihat catatan di
        `_set_datepicker_single`)."""
        try:
            close_btn = modal.find_element(
                By.XPATH,
                ".//button[contains(@class,'ant-modal-close')] | "
                ".//button[contains(., 'Cancel') or contains(., 'Batal')]")
            self._safe_click(close_btn)
            self._sleep(0.8)
        except Exception:
            pass

    def _set_input_value(self, el, value: str):
        """Set nilai input/datepicker via JS lalu trigger event React/Vue."""
        self.driver.execute_script(
            "var nativeInputValueSetter = Object.getOwnPropertyDescriptor("
            "window.HTMLInputElement.prototype, 'value').set;"
            "nativeInputValueSetter.call(arguments[0], arguments[1]);"
            "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));"
            "arguments[0].dispatchEvent(new Event('change', { bubbles: true }));",
            el, value)
        self._sleep(0.3)

    def _normalise_date(self, raw: str) -> str | None:
        """Kembalikan format YYYY-MM-DD dari berbagai format tanggal input."""
        raw = raw.strip()
        if re.match(r"\d{4}-\d{2}-\d{2}", raw):
            return raw
        m = re.match(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", raw)
        if m:
            return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
        return None

    # ── Step 1: Login SSO ─────────────────────────────────────────────────

    def _step1_login(self):
        self.log("info", "Membuka kipapp.bps.go.id…")
        self.driver.get(BASE_URL)
        self._sleep(2)

        # 1. Klik tombol Login SSO
        self.log("info", "Klik tombol Login SSO…")
        self._click_xpath("/html/body/div/div/div/div/div/div/div[2]/div/button")
        self._sleep(2)

        # 2. Isi Username
        self.log("info", "Mengisi username…")
        self._type(self._find('//*[@id="username"]'), self.username)

        # 3. Isi Password
        self.log("info", "Mengisi password…")
        self._type(self._find('//*[@id="password"]'), self.password)

        # 4. Klik tombol Login
        self.log("info", "Klik tombol Login…")
        self._click_xpath('//*[@id="kc-login"]')
        self._sleep(3)

        # Cek apakah OTP diperlukan
        current_url = self.driver.current_url
        self.log("info", f"URL setelah login: {current_url}")
        if HOME_HASH not in current_url:
            self.log("warning", "Belum di halaman home — memeriksa kebutuhan OTP…")
            self._handle_otp()

    def _handle_otp(self):
        """Minta OTP dari user, input ke field, lalu submit."""
        otp = self.request_otp()
        if not otp:
            raise RuntimeError("OTP tidak diberikan oleh user.")

        self.log("info", "Memasukkan OTP…")

        # 5. Isi OTP
        otp_el = self._find('//*[@id="otp"]', timeout=15)
        self._type(otp_el, otp)
        self._sleep(0.5)

        # 6. Klik tombol Login setelah OTP
        self.log("info", "Klik tombol Login setelah OTP…")
        self._click_xpath('//*[@id="kc-login"]')
        self._sleep(3)

        try:
            self._wait_url_contains(HOME_HASH, timeout=20)
            self.log("success", "OTP berhasil — masuk ke halaman home.")
        except TimeoutException:
            self.log("warning", "Masih belum di home setelah OTP — melanjutkan…")

    # ── Step 4: Tutup semua popup ─────────────────────────────────────────

    def _step4_close_popups(self):
        self.log("info", "Menunggu halaman home…")
        try:
            self._wait_url_contains(HOME_HASH, timeout=LONG_WAIT)
        except TimeoutException:
            self.log("warning", "Timeout menunggu home, melanjutkan…")
        self._sleep(2)

        # 1. Modal pertama div[3] → klik close button
        self.log("info", "Menutup popup 1…")
        self._close_popup_1()
        self._sleep(0.8)

        # 2. Tour overlay #v-step-13183d79 → klik Skip/Lewati Tour button[1]
        self.log("info", "Menutup popup 2 (tour)…")
        self._close_popup_2()
        self._sleep(0.8)

        # 3. Modal div[3] versi kedua → klik close button
        self.log("info", "Menutup popup 3…")
        self._close_popup_3()
        self._sleep(0.8)

        self.log("success", "Semua popup ditangani.")

    def _close_popup_1(self):
        """Modal /html/body/div[3]/div/div[2]/div/div[2] → cek ukuran,
        klik 5x acak di luar modal, lalu klik close button."""
        MODAL = "/html/body/div[3]/div/div[2]/div/div[2]"
        CLOSE = "/html/body/div[3]/div/div[2]/div/div[1]/button"
        try:
            modal = self.driver.find_element(By.XPATH, MODAL)
            if not modal.is_displayed():
                return

            # Catat ukuran dan posisi modal
            rect = modal.rect   # {x, y, width, height}
            vw = self.driver.execute_script("return window.innerWidth;")
            vh = self.driver.execute_script("return window.innerHeight;")
            self.log("info",
                f"Popup-1 terdeteksi — posisi ({rect['x']:.0f},{rect['y']:.0f}) "
                f"ukuran {rect['width']:.0f}×{rect['height']:.0f}px "
                f"| viewport {vw}×{vh}px")

            # Hitung koordinat di luar modal untuk klik acak
            modal_x1 = int(rect["x"])
            modal_y1 = int(rect["y"])
            modal_x2 = int(rect["x"] + rect["width"])
            modal_y2 = int(rect["y"] + rect["height"])

            outside_zones = []
            margin = 20
            # Zona kiri
            if modal_x1 > margin:
                outside_zones.append((margin, modal_x1 - margin, margin, vh - margin))
            # Zona kanan
            if modal_x2 < vw - margin:
                outside_zones.append((modal_x2 + margin, vw - margin, margin, vh - margin))
            # Zona atas
            if modal_y1 > margin:
                outside_zones.append((margin, vw - margin, margin, modal_y1 - margin))
            # Zona bawah
            if modal_y2 < vh - margin:
                outside_zones.append((margin, vw - margin, modal_y2 + margin, vh - margin))

            from selenium.webdriver.common.action_chains import ActionChains
            actions = ActionChains(self.driver)

            self.log("info", "Klik 5x acak di luar modal…")
            for i in range(5):
                if outside_zones:
                    zone = random.choice(outside_zones)
                    cx = random.randint(zone[0], zone[1])
                    cy = random.randint(zone[2], zone[3])
                else:
                    # Fallback jika tidak ada zona — klik di pojok kiri atas
                    cx, cy = random.randint(5, 30), random.randint(5, 30)
                actions.move_by_offset(0, 0)   # reset
                self.driver.execute_script(
                    "document.elementFromPoint(arguments[0], arguments[1])"
                    ".dispatchEvent(new MouseEvent('click', "
                    "{bubbles:true, cancelable:true, clientX:arguments[0], clientY:arguments[1]}));",
                    cx, cy)
                self.log("info", f"  Klik luar #{i+1} → ({cx},{cy})")
                time.sleep(random.uniform(0.2, 0.6))

            self._sleep(0.5)

            # Klik close button
            if self._try_click(CLOSE, "Popup-1 close button"):
                return
            # Fallback: button pertama di parent div
            parent = self.driver.find_element(By.XPATH, "/html/body/div[3]/div/div[2]/div")
            for btn in parent.find_elements(By.XPATH, ".//button"):
                if btn.is_displayed():
                    self._safe_click(btn)
                    self.log("info", "Popup-1 close button (fallback) diklik.")
                    self._sleep(0.6)
                    return
        except Exception as e:
            self.log("warning", f"Popup-1 error: {e}")

    def _close_popup_2(self):
        """Tour #v-step-13183d79 → klik button[1] (Skip/Lewati Tour)."""
        self._try_click(
            '//*[@id="v-step-13183d79"]/div[3]/button[1]',
            "Popup-2 Lewati Tour")

    def _close_popup_3(self):
        """Modal /html/body/div[3]/div/div[2]/div/div[2] → klik close button."""
        MODAL = "/html/body/div[3]/div/div[2]/div/div[2]"
        CLOSE = "/html/body/div[3]/div/div[2]/div/div[1]/button"
        try:
            modal = self.driver.find_element(By.XPATH, MODAL)
            if not modal.is_displayed():
                return
            if self._try_click(CLOSE, "Popup-3 close button"):
                return
            # Fallback: button pertama di parent div
            parent = self.driver.find_element(By.XPATH, "/html/body/div[3]/div/div[2]/div")
            for btn in parent.find_elements(By.XPATH, ".//button"):
                if btn.is_displayed():
                    self._safe_click(btn)
                    self.log("info", "Popup-3 close button (fallback) diklik.")
                    self._sleep(0.6)
                    return
        except Exception:
            pass

    # ── Step 5: Navigasi ke Periodik ──────────────────────────────────────

    def _step5_to_periodik(self):
        self.log("info", "Klik menu Perencanaan Kinerja…")
        self._click_xpath('//*[@id="sider"]/div/div/ul[2]/li[5]')
        self._sleep(1)

        self.log("info", "Klik sub-menu Periodik…")
        self._click_xpath('//*[@id="sider"]/div/div/ul[2]/li[5]/ul/li[2]')
        self._sleep(2)
        self.log("success", "Halaman Periodik dibuka.")

    # ── Step 6: Cek tabel & Add Periodik ─────────────────────────────────

    def _step6_check_and_add_periodik(self):
        self.log("info", "Memeriksa tabel periodik…")
        self._sleep(1.5)

        triwulan_index = _triwulan_index()
        self.log("info", f"Triwulan berjalan: {self.period} (index {triwulan_index})")

        rows_count = self._count_table_rows()
        self.log("info", f"Jumlah baris tabel: {rows_count}")

        if rows_count < triwulan_index:
            self.log("info", "Jumlah baris kurang — klik Add…")
            # Tombol Add pada tabel periodik kinerja
            self._click_xpath(
                '//*[@id="components-layout-demo-responsive"]/section/main'
                '/div/div[2]/div/div[1]/div/div[6]/div/button')
            self._sleep(1.5)

            self.log("info", "Memilih periode penilaian di popup…")
            self._step7_select_period_in_popup()

            self.log("info", "Mengisi Rencana Kinerja dari spreadsheet…")
            self._step8_fill_rencana_kinerja()
        else:
            self.log("info", "Tabel sudah memiliki entri cukup, skip Add.")

    def _count_table_rows(self) -> int:
        """Hitung baris data pada tabel periodik (tidak termasuk header)."""
        TABEL_XPATH = (
            '//*[@id="components-layout-demo-responsive"]/section/main'
            '/div/div[2]/div/div[1]/div/div[8]/div/div[2]/div/div/div/div'
        )
        try:
            container = self.driver.find_element(By.XPATH, TABEL_XPATH)
            # Hitung child div langsung sebagai baris
            rows = container.find_elements(By.XPATH, "./div")
            real = [r for r in rows if r.text.strip()]
            return len(real)
        except Exception:
            # Fallback: hitung baris <tr> di tabel manapun
            try:
                trs = self.driver.find_elements(
                    By.XPATH, "//table/tbody/tr[td]")
                return len([r for r in trs if r.text.strip()])
            except Exception:
                return 0

    # ── Step 7: Pilih periode di popup ───────────────────────────────────

    def _select_antd_dropdown_option(self, dropdown_xpath: str,
                                       li_index: int, label: str):
        """Helper universal untuk memilih opsi ke-N dari dropdown Ant Design.

        Ant Design me-render popup ke document.body dengan ID dinamis.
        Strategi:
        1. Klik trigger dropdown
        2. Tunggu popup benar-benar visible (bukan hanya present di DOM)
        3. Kumpulkan semua opsi visible, pilih ke-N (1-based)
        """
        try:
            self._click_xpath(dropdown_xpath, timeout=10)
        except TimeoutException:
            self.log("warning", f"  Dropdown '{label}' tidak ditemukan.")
            return False

        # Tunggu popup visible — Ant Design async render
        POPUP_CONTAINERS = [
            "//div[contains(@class,'ant-select-dropdown') "
            "and not(contains(@class,'ant-select-dropdown-hidden')) "
            "and not(contains(@style,'display: none'))]",
            "//div[contains(@class,'rc-virtual-list')]",
            "//div[contains(@class,'ant-select-dropdown')]",
        ]
        for px in POPUP_CONTAINERS:
            try:
                WebDriverWait(self.driver, 6).until(
                    EC.visibility_of_element_located((By.XPATH, px)))
                self.log("info", f"  Popup '{label}' terdeteksi visible.")
                break
            except Exception:
                continue

        self._sleep(0.5)   # render selesai sepenuhnya
        self.log("info", f"  Memilih opsi ke-{li_index} untuk '{label}'…")

        # Kandidat XPath untuk mengumpulkan opsi visible
        CANDIDATE_XPATHS = [
            "//div[contains(@class,'ant-select-dropdown') "
            "and not(contains(@class,'hidden')) "
            "and not(contains(@style,'display: none'))]"
            "//li[contains(@class,'ant-select-item-option')]",

            "//div[contains(@class,'rc-virtual-list')]"
            "//div[contains(@class,'ant-select-item-option')]",

            "//body//li[@role='option']",

            "//body/div[not(@id='root')]//ul/li"
            "[not(ancestor::*[@id='sider']) and not(ancestor::nav)]",
        ]

        for cxpath in CANDIDATE_XPATHS:
            try:
                all_opts  = self.driver.find_elements(By.XPATH, cxpath)
                vis_opts  = [o for o in all_opts if o.is_displayed()]
                self.log("info",
                    f"  Kandidat '{cxpath[:55]}…': "
                    f"{len(all_opts)} total, {len(vis_opts)} visible")

                if len(vis_opts) >= li_index:
                    target = vis_opts[li_index - 1]   # 0-based
                    self._scroll_into_view(target)
                    self.log("info", f"  Opsi ke-{li_index}: '{target.text.strip()}'")
                    self._safe_click(target)
                    self.log("success", f"  '{label}' opsi ke-{li_index} dipilih.")
                    self._sleep(0.5)
                    return True
            except Exception as e:
                self.log("info", f"  Kandidat gagal: {e}")
                continue

        self.log("warning",
            f"  Semua strategi gagal untuk '{label}' li[{li_index}].")
        return False

    def _step7_select_period_in_popup(self):
        """Pilih triwulan berjalan di dropdown periode penilaian."""
        TRIWULAN_INDEX = {
            "Triwulan I":   1,
            "Triwulan II":  2,
            "Triwulan III": 3,
            "Triwulan IV":  4,
        }
        li_index = TRIWULAN_INDEX.get(self.period)
        if li_index is None:
            self.log("warning", f"  Periode tidak dikenali: {self.period}")
            return

        self.log("info", "  Membuka dropdown periode penilaian…")
        self._select_antd_dropdown_option(
            dropdown_xpath='//*[@id="form-add_periodePenilaian"]/div/div/div[1]',
            li_index=li_index,
            label=f"Periode Penilaian ({self.period})",
        )

    # ── Step 8: Isi Rencana Kinerja ───────────────────────────────────────

    def _get_rk_search_input(self, timeout: float = 10):
        """Cari elemen <input> aktual di dalam komponen Select Rencana Kinerja.
        XPath lama menunjuk ke <span> pembungkus (bukan <input>), yang
        menyebabkan ElementNotInteractableException saat send_keys()."""
        candidates = [
            '//*[@id="form-add_rencanaKinerja"]/div/div[1]/span/input',
            '//*[@id="form-add_rencanaKinerja"]//span[contains(@class,"selection-search")]/input',
            '//*[@id="form-add_rencanaKinerja"]//input',
        ]
        last_err = None
        for xp in candidates:
            try:
                return WebDriverWait(self.driver, timeout).until(
                    EC.element_to_be_clickable((By.XPATH, xp)))
            except TimeoutException as e:
                last_err = e
                continue
        raise last_err or TimeoutException("Input pencarian RK tidak ditemukan")

    def _step8_fill_rencana_kinerja(self):
        """Cari setiap RK satu per satu, centang checkbox, hapus isian,
        beri jeda 3 detik antar iterasi, lalu simpan.

        CATATAN (Jenis Kinerja): hanya RK dengan Jenis Kinerja = 'Utama'
        (atau kolom Jenis Kinerja kosong, demi kompatibilitas mundur dengan
        spreadsheet lama yang belum punya kolom ini) yang diproses di sini.
        RK dengan Jenis Kinerja = 'Tambahan' ditambahkan lewat alur terpisah
        di `_step8b_add_rencana_kinerja_tambahan()` (menu Rencana Kinerja >
        Periode SKP > Add > Jenis Kinerja = Tambahan), sesuai flowchart."""

        # Ambil daftar RK unik sesuai urutan di spreadsheet — HANYA yang
        # berjenis 'Utama' (jenis_kinerja kosong dianggap Utama juga).
        rencana_list = list(dict.fromkeys(
            r.get("rencana_kinerja", "").strip()
            for r in self.rows
            if r.get("rencana_kinerja", "").strip()
            and r.get("jenis_kinerja", "").strip().lower() != "tambahan"
        ))
        self.log("info", f"Daftar Rencana Kinerja Utama ({len(rencana_list)} item): {rencana_list}")

        SAVE_XPATH = '/html/body/div[4]/div/div[2]/div/div[2]/div[3]/div/button[2]'

        for idx, rk in enumerate(rencana_list, start=1):
            self._check_stop()
            self.log("info", f"  [{idx}/{len(rencana_list)}] Mencari RK: {rk}")

            # ── 1. Klik & isi kolom pencarian ────────────────────────────
            try:
                search_el = self._get_rk_search_input(timeout=10)
                self._scroll_into_view(search_el)
                self._wait_interactable(search_el)
                search_el.click()
                self._sleep(0.3)

                # Hapus isian sebelumnya secara menyeluruh
                self.driver.execute_script("arguments[0].value = '';", search_el)
                search_el.send_keys(Keys.CONTROL + "a")
                search_el.send_keys(Keys.DELETE)
                self._sleep(0.2)

                # Ketik nama RK karakter per karakter
                for ch in rk:
                    self._check_stop()
                    search_el.send_keys(ch)
                    time.sleep(random.uniform(0.04, 0.12))

                self._sleep(1.5)   # tunggu hasil pencarian muncul
            except TimeoutException:
                self.log("warning", f"  Input pencarian tidak ditemukan, skip RK: {rk}")
                continue
            except Exception as e:
                self.log("warning", f"  Error isi pencarian '{rk}': {e}")
                continue

            # ── 2. Centang checkbox baris pertama hasil pencarian ─────────
            self._tick_rk_checkbox(rk)

            # ── 3. Hapus isian pencarian sebelum iterasi berikutnya ───────
            try:
                search_el = self._get_rk_search_input(timeout=6)
                self._scroll_into_view(search_el)
                search_el.click()
                self._sleep(0.2)
                self.driver.execute_script("arguments[0].value = '';", search_el)
                search_el.send_keys(Keys.CONTROL + "a")
                search_el.send_keys(Keys.DELETE)
                self._sleep(0.3)
            except Exception as e:
                self.log("warning", f"  Gagal menghapus isian pencarian: {e}")

            # ── 4. Jeda 3 detik antar iterasi (dicek tiap 100ms agar Stop responsif) ──
            if idx < len(rencana_list):
                self.log("info", f"  Jeda 3 detik sebelum RK berikutnya…")
                for _ in range(30):
                    self._check_stop()
                    time.sleep(0.1)

        # ── Simpan ────────────────────────────────────────────────────────
        self._sleep(0.8)
        self.log("info", "Klik tombol Save periodik…")
        try:
            self._click_xpath(SAVE_XPATH, timeout=8)
            self._sleep(1.5)
            self.log("success", "Periodik disimpan.")
        except TimeoutException:
            self.log("warning", "Tombol Save periodik tidak ditemukan.")

    # ── Helper: centang checkbox baris hasil pencarian RK ─────────────────

    def _tick_rk_checkbox(self, rk: str) -> bool:
        """Cari checkbox baris pertama hasil pencarian RK dan pastikan
        benar-benar tercentang (verifikasi is_selected() setelah klik,
        dengan beberapa lapis fallback jika klik pertama tidak berhasil).

        CATATAN (dikonfirmasi dari dump debug_rk_checkbox/*.html pengguna):
        Tabel hasil pencarian menggunakan struktur Ant Design "fixed table"
        di mana HEADER dan BODY adalah DUA <table> TERPISAH, masing-masing
        di dalam div-nya sendiri — bukan <thead>+<tbody> dalam satu <table>:

            div.ant-table-content
              div.ant-table-scroll
                div.ant-table-header  → <table><thead>...<th class="ant-table-selection-column">
                div.ant-table-body    → <table><tbody><tr class="ant-table-row" data-row-key="...">
                                                    <td class="ant-table-selection-column">
                                                      <label class="ant-checkbox-wrapper">
                                                        <span class="ant-checkbox">
                                                          <input type="checkbox">

        XPath versi lama memakai "/div/div[1]/table/tbody/..." — padahal
        div[1] adalah div HEADER (isinya cuma <thead>, tidak punya <tbody>
        sama sekali), sehingga pencarian checkbox baris SELALU 0 hasil.

        Selain itu, baris IKI yang muncul sebagai expanded-row di bawah baris
        RK memakai struktur (dan class) tabel yang IDENTIK. Supaya tidak
        salah ambil checkbox dari tabel IKI bersarang, pencarian dibatasi
        hanya pada <tbody> TERLUAR (yang bukan keturunan dari baris
        ant-table-expanded-row manapun).
        """
        RK_TABLE_ROOT = '//*[@id="form-add_rencanaKinerja"]/div/div[2]/div/div/div/div/div/div'

        # tbody terluar = tbody yang BUKAN keturunan dari <tr> expanded-row manapun
        # (mengecualikan tbody milik tabel IKI yang bersarang di dalam expanded-row)
        OUTER_TBODY = "tbody[not(ancestor::tr[contains(@class,'ant-table-expanded-row')])]"
        # baris data asli: punya class 'ant-table-row', BUKAN measure-row/expanded-row
        OUTER_FIRST_ROW = (
            f"{OUTER_TBODY}/tr["
            "contains(concat(' ',normalize-space(@class),' '),' ant-table-row ')"
            " and not(contains(@class,'ant-table-expanded-row'))"
            " and not(contains(@class,'ant-table-measure-row'))][1]"
        )

        candidates = [
            # Utama: checkbox baris pertama di div.ant-table-body (bukan header,
            # bukan baris IKI bersarang) — sesuai struktur DOM sebenarnya.
            RK_TABLE_ROOT + "//div[contains(@class,'ant-table-body')]//table/"
            + OUTER_FIRST_ROW
            + "/td[contains(@class,'ant-table-selection-column')][1]//input[@type='checkbox']",
            # Sama tanpa syarat div.ant-table-body (jaga-jaga jika markup berbeda versi)
            RK_TABLE_ROOT + "//table/" + OUTER_FIRST_ROW
            + "/td[contains(@class,'ant-table-selection-column')][1]//input[@type='checkbox']",
            RK_TABLE_ROOT + "//table/" + OUTER_FIRST_ROW + "/td[1]//input[@type='checkbox']",
            # Fallback: checkbox "select all" di HEADER tabel (thead, div.ant-table-header).
            # Karena hasil pencarian selalu menyisakan satu baris, mencentang
            # select-all otomatis mencentang baris tunggal yang tampil.
            RK_TABLE_ROOT + "//div[contains(@class,'ant-table-header')]"
            "//th[contains(@class,'ant-table-selection-column')]//input[@type='checkbox']",
            # Fallback generik terakhir: cari di mana saja di bawah komponen RK
            '//*[@id="form-add_rencanaKinerja"]//' + OUTER_FIRST_ROW + "/td[1]//input[@type='checkbox']",
        ]

        def _find_first_match(require_displayed: bool):
            for xp in candidates:
                try:
                    for el in self.driver.find_elements(By.XPATH, xp):
                        try:
                            if (not require_displayed) or el.is_displayed():
                                return el
                        except StaleElementReferenceException:
                            continue
                except Exception:
                    continue
            return None

        # Polling sampai ~8 detik: tabel hasil pencarian bisa butuh waktu untuk
        # render/re-render setelah karakter terakhir diketik (debounce), jadi
        # satu kali cek instan sering terlalu cepat dan menganggap "tidak ada".
        cb = None
        deadline = time.time() + 8
        while cb is None and time.time() < deadline:
            cb = _find_first_match(require_displayed=True)
            if cb is None:
                time.sleep(0.3)

        # Beberapa versi Ant Design (v3) memberi ukuran 0 / opacity 0 pada
        # <input> asli sehingga is_displayed() Selenium bisa keliru menganggap
        # elemen tidak tampil padahal secara visual ada. Coba sekali lagi
        # TANPA syarat is_displayed sebelum benar-benar menyerah.
        if cb is None:
            cb = _find_first_match(require_displayed=False)
            if cb is not None:
                self.log("info", f"  Checkbox '{rk}' ditemukan (tanpa filter is_displayed).")

        if cb is None:
            diag = ""
            try:
                tables = self.driver.find_elements(By.XPATH, RK_TABLE_ROOT + '//table')
                texts = [t.text.strip() for t in tables if t.is_displayed() and t.text.strip()]
                diag = " | ".join(texts)[:300]
            except Exception:
                pass
            if diag:
                self.log("warning",
                    f"  Checkbox '{rk}' tidak ditemukan. Isi tabel saat itu: {diag}")
            else:
                self.log("warning",
                    f"  Checkbox '{rk}' tidak ditemukan — kemungkinan hasil pencarian "
                    f"KOSONG (0 baris). Periksa apakah teks RK di spreadsheet PERSIS "
                    f"sama (termasuk ejaan, kapitalisasi, spasi) dengan opsi Rencana "
                    f"Kinerja yang ada di sistem kipapp.")

            # ── Simpan bukti debug (screenshot + HTML mentah area tabel) ──────
            # Supaya XPath berikutnya bisa dipastikan dari struktur DOM yang
            # SEBENARNYA saat ini, bukan tebakan lagi.
            try:
                import os
                debug_dir = os.path.join(os.getcwd(), "debug_rk_checkbox")
                os.makedirs(debug_dir, exist_ok=True)
                ts = time.strftime("%Y%m%d_%H%M%S")
                safe_rk = re.sub(r"[^a-zA-Z0-9]+", "_", rk)[:40]

                shot_path = os.path.join(debug_dir, f"{ts}_{safe_rk}.png")
                self.driver.save_screenshot(shot_path)

                html_path = os.path.join(debug_dir, f"{ts}_{safe_rk}.html")
                try:
                    container = self.driver.find_element(By.XPATH, RK_TABLE_ROOT)
                    html = container.get_attribute("outerHTML")
                except Exception:
                    html = self.driver.page_source
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html)

                self.log("warning",
                    f"  Bukti debug disimpan: {shot_path} dan {html_path} "
                    f"— kirimkan kedua file ini untuk analisis lebih lanjut.")
            except Exception as e2:
                self.log("warning", f"  Gagal menyimpan bukti debug: {e2}")

            return False

        def _is_checked(input_el) -> bool:
            """Cek status tercentang. is_selected() pada <input> kadang tidak
            akurat di Ant Design (input asli bisa disembunyikan/di-restyle),
            jadi cek juga class 'ant-checkbox-checked' pada span pembungkus
            (<span class="ant-checkbox">), yang merupakan cara Ant Design
            menandai status checked secara visual/DOM."""
            try:
                if input_el.is_selected():
                    return True
            except Exception:
                pass
            try:
                wrapper = input_el.find_element(
                    By.XPATH, "./ancestor::span[contains(@class,'ant-checkbox')][1]")
                cls = wrapper.get_attribute("class") or ""
                if "ant-checkbox-checked" in cls:
                    return True
            except Exception:
                pass
            try:
                return bool(self.driver.execute_script(
                    "return !!arguments[0].checked;", input_el))
            except Exception:
                return False

        try:
            self._scroll_into_view(cb)
            if _is_checked(cb):
                self.log("info", f"  Checkbox '{rk}' sudah tercentang.")
                return True

            # Percobaan 1: klik <label> pembungkus (area klik AntD biasanya
            # lebih besar di label, bukan hanya input-nya, dan lebih andal
            # memicu handler onChange React ketimbang klik <input> langsung)
            try:
                label = cb.find_element(By.XPATH, "./ancestor::label[1]")
                self._safe_click(label)
                self._sleep(0.4)
            except NoSuchElementException:
                pass
            if _is_checked(cb):
                self.log("success", f"  Checkbox '{rk}' dicentang (via label).")
                return True

            # Percobaan 2: klik langsung ke <input>
            self._safe_click(cb)
            self._sleep(0.4)
            if _is_checked(cb):
                self.log("success", f"  Checkbox '{rk}' dicentang.")
                return True

            # Percobaan 3: paksa via JS + trigger event React (click & change)
            try:
                self.driver.execute_script(
                    "arguments[0].checked = true;"
                    "arguments[0].dispatchEvent(new MouseEvent('click', {bubbles:true}));"
                    "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
                    cb)
                self._sleep(0.4)
            except Exception as e:
                self.log("warning", f"  Gagal memaksa centang via JS: {e}")
            if _is_checked(cb):
                self.log("success", f"  Checkbox '{rk}' dicentang (paksa via JS).")
                return True

            self.log("warning",
                f"  Checkbox '{rk}' GAGAL dicentang setelah semua percobaan.")
            return False
        except StaleElementReferenceException:
            self.log("warning",
                f"  Checkbox '{rk}' berubah (stale) saat dicentang, coba lagi…")
            return False

    # ── Step 8b: RK dengan Jenis Kinerja = 'Tambahan' ─────────────────────
    # Sesuai flowchart: percabangan "isJenisKinerja = Utama?" — jika TIDAK
    # (Tambahan), RK ditambahkan lewat menu 'Rencana Kinerja' tersendiri
    # (bukan Perencanaan Kinerja > Periodik), dengan dropdown 'Jenis Kinerja'
    # di-set ke opsi 'Tambahan', dan tiap baris langsung dicentang status
    # 'Selesai' saat ditambahkan.

    def _click_sidebar_menu_by_text(self, text_options: list[str], label: str) -> bool:
        """Klik item menu sidebar berdasarkan teks tampilan (bukan index
        li[N]) — lebih tahan terhadap perubahan urutan/posisi menu di
        sidebar dibanding XPath posisional yang dipakai step-step lain."""
        try:
            items = self.driver.find_elements(By.XPATH, '//*[@id="sider"]//li')
        except Exception:
            items = []

        # Coba exact match dulu, baru substring, supaya "Rencana Kinerja"
        # tidak salah cocok dengan "Perencanaan Kinerja".
        for match_mode in ("exact", "substring"):
            for wanted in text_options:
                wl = wanted.strip().lower()
                for it in items:
                    try:
                        txt = it.text.strip().lower()
                    except StaleElementReferenceException:
                        continue
                    hit = (txt == wl) if match_mode == "exact" else (wl in txt)
                    if hit:
                        self._safe_click(it)
                        self.log("success",
                            f"Menu '{label}' diklik ({match_mode}: '{it.text.strip()}').")
                        return True

        self.log("warning",
            f"Menu '{label}' tidak ditemukan di sidebar (kandidat: {text_options}).")
        return False

    def _click_selesai_checkbox_tambahan(self) -> bool:
        """Klik checkbox berlabel 'Selesai' pada baris RK Tambahan."""
        xpath = (
            "//label[contains(@class,'ant-checkbox-wrapper')]"
            "[.//span[contains(translate(text(),"
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),"
            "'selesai')]]//input[@type='checkbox']"
        )
        try:
            candidates = [e for e in self.driver.find_elements(By.XPATH, xpath)
                          if e.is_displayed()]
            if not candidates:
                self.log("warning", "    Checkbox 'Selesai' tidak ditemukan.")
                return False
            cb = candidates[0]
            self._scroll_into_view(cb)
            if not cb.is_selected():
                self._safe_click(cb)
                self._sleep(0.3)
            self.log("info", "    Checkbox 'Selesai' dicentang.")
            return True
        except Exception as e:
            self.log("warning", f"    Gagal mencentang checkbox 'Selesai': {e}")
            return False

    def _step8b_add_rencana_kinerja_tambahan(self):
        rencana_list = list(dict.fromkeys(
            r.get("rencana_kinerja", "").strip()
            for r in self.rows
            if r.get("rencana_kinerja", "").strip()
            and r.get("jenis_kinerja", "").strip().lower() == "tambahan"
        ))
        if not rencana_list:
            self.log("info",
                "Tidak ada Rencana Kinerja berjenis 'Tambahan' — lewati langkah ini.")
            return

        self.log("info",
            f"Daftar Rencana Kinerja Tambahan ({len(rencana_list)} item): {rencana_list}")

        self.log("info", "Klik menu 'Rencana Kinerja'…")
        if not self._click_sidebar_menu_by_text(["Rencana Kinerja"], "Rencana Kinerja"):
            self._debug_dump("step8b_menu_rencana_kinerja_not_found")
            return
        self._sleep(1.2)

        self.log("info", "Klik 'Periode SKP'…")
        if not self._try_click(
            "//*[contains(translate(text(),"
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'periode skp')]",
            "Periode SKP", timeout=8):
            self.log("warning",
                "  Elemen 'Periode SKP' tidak ditemukan lewat teks, "
                "melanjutkan dengan asumsi sudah di halaman yang benar.")
        self._sleep(1)

        self.log("info", "Klik tombol 'Add'…")
        clicked_add = False
        for xp in (
            "//button[.//span[contains(translate(text(),"
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'add')]]",
            "//button[contains(translate(.,"
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'add')]",
        ):
            if self._try_click(xp, "Tombol Add", timeout=6):
                clicked_add = True
                break
        if not clicked_add:
            self.log("warning", "  Tombol 'Add' tidak ditemukan.")
            self._debug_dump("step8b_add_button_not_found")
            return
        self._sleep(1)

        self.log("info", "Membuka dropdown 'Jenis Kinerja' dan memilih 'Tambahan'…")
        opened = False
        for xp in ('//*[@id="3c9072f0-0dc9-494b-9790-5dbeb675aacb"]/ul/li'):
            try:
                self._click_xpath(xp, timeout=6)
                opened = True
                break
            except TimeoutException:
                continue
        if not opened:
            self.log("warning", "  Dropdown 'Jenis Kinerja' tidak ditemukan.")
            self._debug_dump("step8b_jenis_kinerja_dropdown_not_found")
        else:
            self._sleep(0.6)
            try:
                opts = self.driver.find_elements(
                    By.XPATH,
                    "//li[contains(@class,'ant-select-item-option')] | "
                    "//div[contains(@class,'ant-select-item-option')]")
                picked = False
                for opt in opts:
                    if opt.is_displayed() and "tambahan" in opt.text.strip().lower():
                        self._safe_click(opt)
                        picked = True
                        break
                if picked:
                    self.log("success", "  Jenis Kinerja 'Tambahan' dipilih.")
                else:
                    self.log("warning",
                        "  Opsi 'Tambahan' tidak ditemukan di dropdown Jenis Kinerja.")
            except Exception as e:
                self.log("warning", f"  Gagal memilih 'Tambahan': {e}")
            self._sleep(0.5)

        SAVE_XPATH = '/html/body/div[4]/div/div[2]/div/div[2]/div[3]/div/button[2]'

        for idx, rk in enumerate(rencana_list, start=1):
            self._check_stop()
            self.log("info", f"  [{idx}/{len(rencana_list)}] Mencari RK Tambahan: {rk}")
            try:
                search_el = self._get_rk_search_input(timeout=10)
                self._scroll_into_view(search_el)
                self._wait_interactable(search_el)
                search_el.click()
                self._sleep(0.3)
                self.driver.execute_script("arguments[0].value = '';", search_el)
                search_el.send_keys(Keys.CONTROL + "a")
                search_el.send_keys(Keys.DELETE)
                self._sleep(0.2)
                for ch in rk:
                    self._check_stop()
                    search_el.send_keys(ch)
                    time.sleep(random.uniform(0.04, 0.12))
                self._sleep(1.5)
            except TimeoutException:
                self.log("warning", f"  Input pencarian tidak ditemukan, skip RK: {rk}")
                continue
            except Exception as e:
                self.log("warning", f"  Error isi pencarian '{rk}': {e}")
                continue

            # Centang baris hasil pencarian, LALU centang status 'Selesai' —
            # sesuai flowchart, RK Tambahan langsung ditandai selesai saat
            # ditambahkan (berbeda dari RK Utama yang statusnya diatur
            # belakangan lewat menu Pelaksanaan Kinerja).
            self._tick_rk_checkbox(rk)
            self._click_selesai_checkbox_tambahan()

            try:
                search_el = self._get_rk_search_input(timeout=6)
                self._scroll_into_view(search_el)
                search_el.click()
                self._sleep(0.2)
                self.driver.execute_script("arguments[0].value = '';", search_el)
                search_el.send_keys(Keys.CONTROL + "a")
                search_el.send_keys(Keys.DELETE)
                self._sleep(0.3)
            except Exception as e:
                self.log("warning", f"  Gagal menghapus isian pencarian: {e}")

            if idx < len(rencana_list):
                self.log("info", "  Jeda 3 detik sebelum RK Tambahan berikutnya…")
                for _ in range(30):
                    self._check_stop()
                    time.sleep(0.1)

        self._sleep(0.8)
        self.log("info", "Klik tombol Save (Rencana Kinerja Tambahan)…")
        try:
            self._click_xpath(SAVE_XPATH, timeout=8)
            self._sleep(1.5)
            self.log("success", "Rencana Kinerja Tambahan disimpan.")
        except TimeoutException:
            self.log("warning", "Tombol Save Rencana Kinerja Tambahan tidak ditemukan.")

    # ── Step 9: Navigasi ke Pelaksanaan ───────────────────────────────────

    def _step9_to_pelaksanaan(self):
        self.log("info", "Klik menu Pelaksanaan Kinerja…")
        self._click_xpath('//*[@id="sider"]/div/div/ul[2]/li[6]/div')
        self._sleep(1)

        self.log("info", "Klik sub-menu Pelaksanaan…")
        self._click_xpath('//*[@id="sider"]/div/div/ul[2]/li[6]/ul')
        self._sleep(2)
        self.log("success", "Halaman Pelaksanaan dibuka.")

    # ── Steps 10-14 ───────────────────────────────────────────────────────

    def _step10_to_14_fill_pelaksanaan(self):
        rk_groups: dict[str, list[dict]] = defaultdict(list)
        for row in self.rows:
            rk = row.get("rencana_kinerja", "").strip()
            if rk:
                rk_groups[rk].append(row)

        for rk, entries in rk_groups.items():
            self._check_stop()
            self.log("info", f"Mengisi Pelaksanaan untuk RK: {rk}")
            self._step10_select_periode_skp()
            self._step11_select_rencana_kinerja(rk)
            self._step12_edit_status()
            for entry in entries:
                self._check_stop()
                self._step13_14_add_entry(entry)

    # ── Step 10: Pilih Periode SKP ────────────────────────────────────────

    def _step10_select_periode_skp(self):
        """Klik dropdown Periode SKP lalu pilih opsi ke-N berdasarkan triwulan.

        Dropdown XPath: //*[@id="components-layout-demo-responsive"]/...div[4]/div/div[2]/div
        Popup ID bersifat dinamis (contoh: 3c7cb75d-...), sehingga pemilihan
        menggunakan posisi li[N] dari popup yang sedang aktif.
        """
        self.log("info", "Memilih Periode SKP…")
        self._sleep(0.5)

        TRIWULAN_INDEX = {
            "Triwulan I":   1,
            "Triwulan II":  2,
            "Triwulan III": 3,
            "Triwulan IV":  4,
        }

        li_index = TRIWULAN_INDEX.get(self.period)
        if li_index is None:
            self.log("warning", f"  Periode tidak dikenali: {self.period}")
            return

        # XPath dropdown Periode SKP yang benar (div[4], bukan div[7])
        DROPDOWN_XPATH = (
            '//*[@id="components-layout-demo-responsive"]/section/main'
            '/div/div[2]/div/div/div[4]/div/div[2]/div'
        )

        # Klik dropdown untuk membukanya
        try:
            self._click_xpath(DROPDOWN_XPATH, timeout=10)
            self._sleep(1.2)   # beri waktu Ant Design selesai render popup
        except TimeoutException:
            self.log("warning", "  Dropdown Periode SKP tidak ditemukan.")
            return

        self.log("info", f"  Memilih {self.period} → li ke-{li_index}…")

        # ── Strategi: posisi li[N] di dalam popup yang sedang aktif ──────
        # ID popup dinamis (misal: 3c7cb75d-8a24-415f-ecef-8afbcae4b849),
        # sehingga semua XPath di bawah TIDAK menggunakan ID tersebut.
        POPUP_LI_XPATHS = [
            # 1. Cari popup dropdown Ant Design yang sedang visible,
            #    ambil li ke-N dari dalamnya
            f"(//div[contains(@class,'ant-select-dropdown') "
            f"and not(contains(@class,'ant-select-dropdown-hidden')) "
            f"and not(contains(@style,'display: none'))]"
            f"//li[contains(@class,'ant-select-item-option')])[{li_index}]",

            # 2. rc-virtual-list (Ant Design virtual scroll)
            f"(//div[contains(@class,'rc-virtual-list-holder-inner')]"
            f"//div[contains(@class,'ant-select-item')])[{li_index}]",

            # 3. li[@role='option'] ke-N di seluruh body
            f"(//body//li[@role='option' or contains(@class,'ant-select-item-option')])"
            f"[{li_index}]",

            # 4. Fallback: ul/li di popup body di luar sidebar dan nav
            f"(//body/div[not(@id='root') and not(@id='sider')]//ul/li"
            f"[not(ancestor::*[@id='sider']) and not(ancestor::nav)])[{li_index}]",
        ]

        for xpath in POPUP_LI_XPATHS:
            try:
                el = WebDriverWait(self.driver, 6).until(
                    EC.element_to_be_clickable((By.XPATH, xpath)))
                if el.is_displayed():
                    self._scroll_into_view(el)
                    self.log("info", f"  Opsi ditemukan: '{el.text.strip()}'")
                    self._safe_click(el)
                    self.log("success", f"  Periode SKP '{self.period}' dipilih.")
                    self._sleep(0.5)
                    return
            except Exception:
                continue

        self.log("warning",
            f"  Semua strategi gagal untuk Periode SKP li[{li_index}]. "
            f"Pastikan dropdown terbuka dan memiliki minimal {li_index} opsi.")

    # ── Step 11: Pilih Rencana Kinerja ────────────────────────────────────

    def _step11_select_rencana_kinerja(self, rk: str):
        self.log("info", f"  Memilih Rencana Kinerja: {rk}")
        self._sleep(0.5)

        RK_DROPDOWN_XPATH = (
            '//*[@id="components-layout-demo-responsive"]/section/main'
            '/div/div[2]/div/div/div[7]/div/div[2]/div/div/div'
        )
        RK_LIST_XPATH = '//*[@id="b6a2935b-72f1-4bf6-8878-c09be0759071"]/ul/li/ul/li[1]'

        # Klik dropdown / search box RK
        try:
            self._click_xpath(RK_DROPDOWN_XPATH, timeout=10)
            self._sleep(0.5)
            # Ketik nama RK untuk filter
            active = self.driver.switch_to.active_element
            active.send_keys(rk)
            self._sleep(1)
        except Exception as e:
            self.log("warning", f"  Dropdown RK tidak ditemukan: {e}")
            return

        # Klik opsi pertama dari list dropdown
        try:
            self._click_xpath(RK_LIST_XPATH, timeout=8)
            self.log("success", f"  RK '{rk}' dipilih.")
            self._sleep(0.5)
        except TimeoutException:
            # Fallback: cari opsi berdasarkan teks
            self.log("warning", "  List RK spesifik tidak ditemukan, mencoba fallback…")
            try:
                opts = self.driver.find_elements(
                    By.XPATH,
                    "//div[contains(@class,'ant-select-item-option')] | "
                    "//li[@role='option']")
                for opt in opts:
                    if opt.is_displayed() and rk.lower() in opt.text.lower():
                        self._safe_click(opt)
                        self.log("success", f"  RK '{rk}' dipilih (fallback).")
                        self._sleep(0.5)
                        return
                self.log("warning", f"  RK '{rk}' tidak ditemukan di dropdown.")
            except Exception as e2:
                self.log("warning", f"  Fallback RK error: {e2}")

    # ── Step 12: Edit Status + Checklist + Save ───────────────────────────

    def _step12_edit_status(self):
        EDIT_STATUS_XPATH = (
            '//*[@id="components-layout-demo-responsive"]/section/main'
            '/div/div[2]/div/div/div[7]/div/div[2]/div/div[2]'
            '/div/div/div/span[2]/div/button'
        )
        self.log("info", "  Klik Edit Status…")
        try:
            self._click_xpath(EDIT_STATUS_XPATH, timeout=10)
            self._sleep(0.8)
        except TimeoutException:
            self.log("warning", "  Tombol Edit Status tidak ditemukan.")
            self._debug_dump("edit_status_button_not_found")
            return

        # ── Cari modal yang BENAR-BENAR tampil ───────────────────────────
        # Bukti debug (checklist_button_not_found.html) menunjukkan bahwa
        # xpath lama `//div[contains(@class,'ant-modal') and
        # not(contains(@class,'ant-modal-hidden'))]` salah menangkap modal
        # tutorial "KipApp Work Flow" yang selalu ada di DOM tapi
        # disembunyikan lewat inline style="display:none" (bukan lewat
        # class 'ant-modal-hidden'). Modal yang seharusnya diisi adalah
        # "Edit Status Rencana Kinerja", yang isinya HANYA sebuah checkbox
        # berlabel "Selesai" + tombol Cancel/Save — TIDAK ADA tombol
        # terpisah bernama "Checklist". Jadi "checklist" di sini maksudnya
        # adalah checkbox status itu sendiri.
        modal = self._wait_visible_modal(tag_on_fail="edit_status_modal_not_visible")
        if modal is None:
            return

        self.log("info", "  Centang status 'Selesai' (jika belum tercentang)…")
        try:
            checkbox = WebDriverWait(self.driver, 8).until(
                lambda d: modal.find_element(
                    By.XPATH,
                    ".//label[contains(@class,'ant-checkbox-wrapper')]"
                    "//input[@type='checkbox']"))
            self._wait_interactable(checkbox)
            if not checkbox.is_selected():
                self._safe_click(checkbox)
            self._sleep(0.5)
        except Exception:
            self.log("warning", "  Checkbox status 'Selesai' tidak ditemukan di modal Edit Status.")
            self._debug_dump("edit_status_checkbox_not_found", scope_element=modal)
            return

        self.log("info", "  Klik Save status…")
        try:
            save_btn = modal.find_element(
                By.XPATH,
                ".//button[contains(., 'Save') or contains(., 'Simpan')]")
            self._safe_click(save_btn)
            self._sleep(1)
            self.log("success", "  Status Rencana Kinerja disimpan.")
        except Exception:
            self.log("warning", "  Tombol Save status tidak ditemukan.")
            self._debug_dump("save_status_button_not_found", scope_element=modal)

    # ── Steps 13-14: Tambah entri kegiatan ───────────────────────────────

    def _step13_14_add_entry(self, row: dict):
        kegiatan    = row.get("kegiatan", "").strip()
        progres     = row.get("progres", "").strip()
        capaian     = row.get("capaian", "").strip()
        data_dukung = row.get("data_dukung", "").strip()
        tgl_mulai   = row.get("tanggal_mulai", "").strip()
        tgl_selesai = row.get("tanggal_selesai", "").strip()
        try:
            lama_hari = int(float(row.get("lama_hari", "1").strip() or "1"))
        except ValueError:
            lama_hari = 1

        # Bersihkan popup kalender/dropdown yang mungkin masih tertinggal
        # dari entri sebelumnya (mis. kalau proses terhenti di tengah jalan
        # sebelum sempat blur sendiri) — supaya tidak menghalangi klik
        # tombol "+ Add" di bawah ini.
        self._dismiss_stray_pickers()

        self.log("info", f"    Klik Add untuk kegiatan: {kegiatan[:50]}…")
        ADD_BTN_XPATH = (
            '//*[@id="components-layout-demo-responsive"]/section/main/div/'
            'div[2]/div/div/div[8]/div/button[2]')
        ADD_BTN_FALLBACK = (
            "//button[contains(text(),'Add') or contains(text(),'Tambah')"
            " or contains(@class,'btn-add')]")
        try:
            try:
                self._click_xpath(ADD_BTN_XPATH, timeout=5)
            except TimeoutException:
                self._click_xpath(ADD_BTN_FALLBACK, timeout=8)
            self._sleep(1.2)
        except TimeoutException:
            self.log("warning", "    Tombol Add tidak ditemukan.")
            self._debug_dump("step13_add_button_not_found")
            return

        # ── Cari modal Add yang BENAR-BENAR tampil ───────────────────────
        # Xpath absolut lama (mis. '/html/body/div[6]/...' dan
        # '/html/body/div[5]/...') RAPUH karena situs ini selalu menaruh
        # modal lain (mis. modal tutorial "KipApp Work Flow") di DOM secara
        # bersamaan meski tersembunyi — sehingga indeks div[N] bisa bergeser
        # kapan saja dan salah menangkap elemen. Sebagai gantinya kita cari
        # modal yang is_displayed()==True lalu cari elemen SECARA RELATIF
        # di dalamnya.
        modal = self._wait_visible_modal(tag_on_fail="step13_add_modal_not_visible")
        if modal is None:
            return

        # Pastikan modal yang tertangkap benar-benar form "Add entri" (ada
        # field form-add_kegiatan di dalamnya) — bukan modal lain yang
        # kebetulan masih tampil (mis. sisa modal Edit Status yang belum
        # sempat tertutup). Kalau bukan, jangan lanjut mengisi field ke
        # modal yang salah.
        try:
            WebDriverWait(self.driver, 5).until(
                lambda d: modal.find_element(By.XPATH, './/*[@id="form-add_kegiatan"]'))
        except Exception:
            self.log("warning", "    Modal yang tampil bukan form Add entri yang diharapkan.")
            self._debug_dump("step13_add_modal_wrong_modal", scope_element=modal)
            return

        # ── Tanggal ───────────────────────────────────────────────────────
        date_str_mulai   = self._normalise_date(tgl_mulai)
        date_str_selesai = self._normalise_date(tgl_selesai) if tgl_selesai else None

        if lama_hari == 1:
            # Single date picker — pastikan checkbox "Gunakan Periode Tanggal"
            # TIDAK tercentang dulu. Modal Add dipakai ulang antar entri, jadi
            # kalau entri SEBELUMNYA lama_hari > 1 (checkbox tercentang),
            # status tercentang itu bisa terbawa ke entri ini kalau tidak
            # eksplisit di-uncheck — membuat field Tanggal salah render
            # sebagai range picker dan validasi "Pilih tanggal kegiatan" gagal
            # terus meski cuma perlu 1 tanggal.
            unchecked = self._click_periode_checkbox_and_verify(modal, desired=False)
            if unchecked:
                # Tunggu field Tanggal kembali ke mode single (1 input)
                deadline = time.time() + 5
                while time.time() < deadline:
                    try:
                        n_inputs = len(modal.find_elements(
                            By.XPATH, './/*[@id="form-add_tanggal"]//input'))
                        if n_inputs <= 1:
                            break
                    except StaleElementReferenceException:
                        pass
                    self._sleep(0.2)
            self.log("info", f"    Set tanggal mulai: {date_str_mulai}")
            self._set_datepicker_single(date_str_mulai)
        else:
            # Klik checkbox "Gunakan Periode Tanggal" dulu — dicari relatif
            # terhadap modal yang tampil, bukan lewat xpath absolut rapuh.
            # PENTING: verifikasi checkbox benar-benar tercentang (bukan
            # cuma "diklik") sebelum lanjut — klik yang tidak ter-apply
            # membuat field Tanggal tetap dalam mode single-date walau
            # lama_hari > 1, sehingga start/end datepicker gagal ditemukan.
            self.log("info", "    Klik checkbox Gunakan Periode Tanggal…")
            toggled = self._click_periode_checkbox_and_verify(modal, desired=True)
            if toggled:
                # Tunggu field Tanggal benar-benar berubah struktur ke range
                # (2 input) sebelum mencoba isi start/end.
                is_range = False
                deadline = time.time() + 5
                while time.time() < deadline:
                    try:
                        n_inputs = len(modal.find_elements(
                            By.XPATH, './/*[@id="form-add_tanggal"]//input'))
                        if n_inputs >= 2:
                            is_range = True
                            break
                    except StaleElementReferenceException:
                        pass
                    self._sleep(0.2)
                if not is_range:
                    self.log("warning",
                        "    Field Tanggal belum berubah ke mode range setelah "
                        "checkbox dicentang — lanjut mencoba isi tetap, tapi "
                        "kemungkinan masih gagal.")
                    self._debug_dump("step13_tanggal_not_range_after_checkbox", scope_element=modal)

            self.log("info", f"    Set tanggal mulai: {date_str_mulai}, selesai: {date_str_selesai}")
            self._set_datepicker_range(date_str_mulai, date_str_selesai)

        # ── Isian form ────────────────────────────────────────────────────
        self._fill_by_id('//*[@id="form-add_kegiatan"]',   kegiatan,    "Kegiatan")
        self._fill_by_id('//*[@id="form-add_progres"]',    progres,     "Progres")
        self._fill_by_id('//*[@id="form-add_capaian"]',    capaian,     "Capaian")
        self._fill_by_id('//*[@id="form-add_dataDukung"]', data_dukung, "Data Dukung")

        # ── Checkbox masukkan ke capaian SKP ─────────────────────────────
        self.log("info", "    Centang masukkan ke Capaian SKP…")
        try:
            cb = self._find('//*[@id="form-add_isCapaianSKP"]', timeout=6)
            if not cb.is_selected():
                self._safe_click(cb)
            self._sleep(0.3)
        except TimeoutException:
            self.log("warning", "    Checkbox Capaian SKP tidak ditemukan.")
            self._debug_dump("step13_capaian_skp_checkbox_not_found", scope_element=modal)

        # ── Simpan ────────────────────────────────────────────────────────
        self.log("info", "    Klik Save…")
        try:
            save_btn = modal.find_element(
                By.XPATH,
                ".//button[contains(., 'Save') or contains(., 'Simpan')]")
            self._safe_click(save_btn)
            self._sleep(1.5)
            # Pastikan modal benar-benar tertutup setelah Save. Kalau masih
            # terbuka (mis. validasi form gagal), modal yang tertinggal ini
            # akan memblokir klik tombol "+ Add" pada baris berikutnya —
            # jadi coba tutup paksa supaya iterasi berikutnya tidak macet.
            try:
                WebDriverWait(self.driver, 5).until_not(
                    lambda d: modal.is_displayed())
                self.log("success", f"    Entry disimpan: {kegiatan[:50]}")
            except StaleElementReferenceException:
                # Modal sudah tidak ada lagi di DOM sama sekali — ini
                # justru konfirmasi bahwa modal berhasil tertutup.
                self.log("success", f"    Entry disimpan: {kegiatan[:50]}")
            except Exception:
                self.log("warning",
                    "    Modal Add tampaknya masih terbuka setelah Save "
                    "(kemungkinan validasi form gagal).")
                self._debug_dump("step13_modal_still_open_after_save", scope_element=modal)
                self._force_close_modal(modal)
        except Exception:
            self.log("warning", "    Tombol Save entry tidak ditemukan.")
            self._debug_dump("step13_save_entry_button_not_found", scope_element=modal)
            self._force_close_modal(modal)

    def _click_periode_checkbox_and_verify(self, modal, desired: bool = True) -> bool:
        """Pastikan checkbox 'Gunakan Periode Tanggal' berada pada status
        `desired` (True = tercentang/range, False = tidak tercentang/single).

        Modal Add entri dipakai ULANG untuk setiap baris, jadi kalau entri
        sebelumnya lama_hari > 1 (checkbox dicentang), entri berikutnya yang
        lama_hari == 1 bisa mewarisi checkbox yang MASIH tercentang kalau
        tidak eksplisit di-uncheck — menyebabkan field Tanggal salah tampil
        sebagai range picker dan validasi "Pilih tanggal kegiatan" gagal.

        Coba beberapa strategi klik karena checkbox Ant Design kadang tidak
        ter-toggle dengan klik native biasa (mis. karena elemen visual yang
        menutupi input asli)."""
        PERIODE_XPATH = (
            ".//label[contains(@class,'ant-checkbox-wrapper')]"
            "[.//span[contains(translate(., "
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
            "'abcdefghijklmnopqrstuvwxyz'), 'periode')]]"
            "//input[@type='checkbox']")
        try:
            cb = WebDriverWait(self.driver, 8).until(
                lambda d: modal.find_element(By.XPATH, PERIODE_XPATH))
        except Exception:
            self.log("warning", "    Checkbox Gunakan Periode Tanggal tidak ditemukan.")
            self._debug_dump("step13_periode_checkbox_not_found", scope_element=modal)
            return False

        # Sudah dalam status yang diinginkan — tidak perlu apa-apa.
        try:
            if cb.is_selected() == desired:
                return True
        except Exception:
            pass

        label = "tercentang" if desired else "tidak tercentang"
        strategies = [
            ("klik native", lambda el: self._safe_click(el)),
            ("klik JS pada input", lambda el: self.driver.execute_script(
                "arguments[0].click();", el)),
            ("klik label pembungkus", lambda el: self.driver.execute_script(
                "var l = arguments[0].closest('label'); if (l) l.click();", el)),
            ("dispatch change langsung", lambda el: self.driver.execute_script(
                """
                var el = arguments[0], want = arguments[1];
                el.checked = want;
                el.dispatchEvent(new Event('click',  {bubbles:true}));
                el.dispatchEvent(new Event('change', {bubbles:true}));
                """, el, desired)),
        ]

        for name, action in strategies:
            try:
                action(cb)
            except Exception:
                pass
            # Beri waktu re-render, lalu cek status
            for _ in range(10):
                self._sleep(0.2)
                try:
                    if cb.is_selected() == desired:
                        self.log("info", f"    Checkbox Periode Tanggal {label} (via {name}).")
                        return True
                except StaleElementReferenceException:
                    break
            # Cari ulang elemen (referensi lama mungkin stale setelah re-render)
            try:
                cb = modal.find_element(By.XPATH, PERIODE_XPATH)
                if cb.is_selected() == desired:
                    self.log("info", f"    Checkbox Periode Tanggal {label} (via {name}).")
                    return True
            except Exception:
                pass

        self.log("warning",
            f"    Checkbox Periode Tanggal gagal diubah ke status '{label}' "
            "setelah beberapa percobaan klik.")
        self._debug_dump("step13_periode_checkbox_not_toggled", scope_element=modal)
        return False

    def _fill_by_id(self, xpath: str, value: str, label: str):
        """Isi field form berdasarkan XPath.
        Menangani 3 tipe elemen dari DOM aktual form Add entri:
        - ant-input-number  : Progres  — <div id="form-add_progres" class="ant-input-number">
                              input aktual ada di dalam dengan class ant-input-number-input
        - <textarea>        : Kegiatan, Capaian — ada button .ant-btn-circle di sekitarnya
                              yang membuat element_to_be_clickable sering timeout
        - <input type=text> : Data Dukung
        """
        if not value:
            return
        try:
            el = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, xpath)))
            self._scroll_into_view(el)
            self._sleep(0.2)

            tag        = el.tag_name.lower()
            el_classes = el.get_attribute("class") or ""

            # ── ant-input-number (Progres) ───────────────────────────────
            # Struktur: <div class="ant-input-number ...">
            #             <div class="ant-input-number-input-wrap">
            #               <input class="ant-input-number-input" ...>
            if tag == "div" and "ant-input-number" in el_classes:
                try:
                    inp = el.find_element(By.CLASS_NAME, "ant-input-number-input")
                except Exception:
                    inp = el.find_element(By.TAG_NAME, "input")
                self._scroll_into_view(inp)
                self.driver.execute_script("""
                    var el = arguments[0], val = arguments[1];
                    el.focus();
                    var d = Object.getOwnPropertyDescriptor(
                            window.HTMLInputElement.prototype, 'value');
                    d.set.call(el, val);
                    el.dispatchEvent(new Event('input',  {bubbles:true}));
                    el.dispatchEvent(new Event('change', {bubbles:true}));
                    el.dispatchEvent(new KeyboardEvent('keyup', {bubbles:true}));
                """, inp, value)
                self._sleep(0.3)
                self.log("info", f"    Field '{label}' diisi: {value[:40]}")
                return

            # ── textarea / input biasa (Kegiatan, Capaian, Data Dukung) ──
            # Klik via JS agar tidak terganggu elemen lain yang menutupi
            self.driver.execute_script(
                "arguments[0].focus(); arguments[0].click();", el)
            self._sleep(0.2)
            # Hapus isi lama via JS lalu trigger event
            self.driver.execute_script("""
                var el = arguments[0];
                var proto = el.tagName === 'TEXTAREA'
                    ? window.HTMLTextAreaElement.prototype
                    : window.HTMLInputElement.prototype;
                var d = Object.getOwnPropertyDescriptor(proto, 'value');
                if (d && d.set) { d.set.call(el, ''); } else { el.value = ''; }
                el.dispatchEvent(new Event('input',  {bubbles:true}));
                el.dispatchEvent(new Event('change', {bubbles:true}));
            """, el)
            self._sleep(0.1)
            # Ketik karakter per karakter agar event onInput Vue/React terpicu
            for ch in value:
                el.send_keys(ch)
                time.sleep(random.uniform(0.03, 0.09))
            self._sleep(0.2)
            self.log("info", f"    Field '{label}' diisi: {value[:40]}")

        except TimeoutException:
            self.log("warning", f"    Field '{label}' tidak ditemukan ({xpath})")
            self._debug_dump(f"step13_field_{label}_not_found")
        except Exception as e:
            self.log("warning", f"    Field '{label}' error: {e}")
            self._debug_dump(f"step13_field_{label}_error")

    def _date_to_antd_display(self, date_str: str) -> str | None:
        """Normalisasi ke YYYY-MM-DD — format yang memang dipakai input
        kalender KipApp (BUKAN DD-MM-YYYY seperti sebelumnya)."""
        import re as _re
        s = date_str.strip()
        m = _re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        m = _re.match(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", s)
        if m:
            return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
        return None

    def _antd_calendar_type(self, display_date: str, slot: str = "start"):
        """Ketik tanggal ke input header kalender Ant Design yang sedang terbuka.

        Kalender di-render ke document.body (bukan di dalam modal).
        Slot: 'start' → input pertama, 'end' → input kedua (range picker).
        """
        XPATH = (
            "//div[contains(@class,'ant-calendar') "
            "and not(contains(@class,'ant-calendar-picker-container-hidden'))]"
            "//input[contains(@class,'ant-calendar-input')]"
        )
        try:
            inputs = WebDriverWait(self.driver, 8).until(
                EC.presence_of_all_elements_located((By.XPATH, XPATH)))
            inp = inputs[-1] if (slot == "end" and len(inputs) > 1) else inputs[0]
            self._scroll_into_view(inp)
            # Hapus & isi via JS lalu ketik karakter untuk trigger AntD filter
            self.driver.execute_script(
                "arguments[0].value=''; arguments[0].focus();", inp)
            self._sleep(0.2)
            for ch in display_date:
                inp.send_keys(ch)
                time.sleep(random.uniform(0.05, 0.1))
            self._sleep(0.3)
            inp.send_keys(Keys.ENTER)
            self._sleep(0.6)
            self.log("info", f"    Tanggal ({slot}) diisi: {display_date}")
        except TimeoutException:
            self.log("warning", f"    Input kalender ({slot}) tidak muncul.")
            self._debug_dump(f"step13_datepicker_{slot}_error")
        except Exception as e:
            self.log("warning", f"    Input kalender ({slot}) error: {e}")
            self._debug_dump(f"step13_datepicker_{slot}_error")

    def _set_datepicker_single(self, date_str: str | None):
        """Isi single date picker Ant Design (lama_hari = 1).

        Input readonly="true" — tidak bisa di-set via value setter.
        Fix: klik span picker → kalender popup muncul → ketik di
        ant-calendar-input → Enter → kalender menutup sendiri.
        JANGAN pakai Keys.ESCAPE (menutup seluruh ant-modal).
        """
        if not date_str:
            return
        display = self._date_to_antd_display(date_str)
        if not display:
            self.log("warning", f"    Format tanggal tidak dikenali: {date_str}")
            return
        PICKER = '//*[@id="form-add_tanggal"]'
        try:
            container = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, PICKER)))
            # PENTING: klik harus mengenai <input> di dalamnya, BUKAN <span>
            # pembungkus id="form-add_tanggal" — handler buka-kalender Ant
            # Design terpasang pada <input> itu sendiri (onFocus/onClick).
            # Klik yang di-dispatch pada elemen ANCESTOR tidak menjalar ke
            # handler yang terpasang pada elemen DESCENDANT, jadi kalender
            # tidak pernah terbuka walau "klik" tampak berhasil.
            try:
                inp = container.find_element(
                    By.XPATH, './/input[contains(@class,"ant-calendar-picker-input")]')
            except Exception:
                inp = container.find_element(By.TAG_NAME, "input")
            self._scroll_into_view(inp)
            self.driver.execute_script(
                "arguments[0].focus(); arguments[0].click();", inp)
            self._sleep(0.8)
        except Exception as e:
            self.log("warning", f"    Single date picker tidak ditemukan: {e}")
            self._debug_dump("step13_datepicker_start_not_found")
            return
        self._antd_calendar_type(display, slot="start")

    def _set_datepicker_range(self, start: str | None, end: str | None):
        """Isi range date picker Ant Design (lama_hari > 1).

        Kedua input readonly="true". Klik span picker sekali → kalender
        range muncul → ketik start → Enter → ketik end → Enter.
        """
        if not start and not end:
            return
        PICKER = '//*[@id="form-add_tanggal"]'
        try:
            container = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, PICKER)))
            # Sama seperti single date picker: klik harus mengenai <input>
            # di dalamnya, bukan <span> pembungkusnya.
            try:
                inp = container.find_element(
                    By.XPATH, './/input[contains(@class,"ant-calendar-picker-input") '
                              'or contains(@class,"ant-calendar-range-picker-input")]')
            except Exception:
                inp = container.find_element(By.TAG_NAME, "input")
            self._scroll_into_view(inp)
            self.driver.execute_script(
                "arguments[0].focus(); arguments[0].click();", inp)
            self._sleep(0.8)
        except Exception as e:
            self.log("warning", f"    Range date picker tidak ditemukan: {e}")
            self._debug_dump("step13_datepicker_start_not_found")
            return
        if start:
            display_s = self._date_to_antd_display(start)
            if display_s:
                self._antd_calendar_type(display_s, slot="start")
                self._sleep(0.4)
        if end:
            display_e = self._date_to_antd_display(end)
            if display_e:
                self._antd_calendar_type(display_e, slot="end")
