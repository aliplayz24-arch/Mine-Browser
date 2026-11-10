import base64
import json
import mimetypes
import os
import platform
import re
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import quote_plus

from PyQt6.QtCore import QEvent, QLocale, QStringListModel, Qt, QTimer, QUrl
from PyQt6.QtGui import QFont, QKeySequence, QShortcut
from PyQt6.QtWebEngineCore import (
    QWebEngineDownloadRequest,
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineScript,
    QWebEngineSettings,
    QWebEngineUrlRequestInfo,
    QWebEngineUrlRequestInterceptor,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

DATA = Path(os.environ.get("MINIBROWSER_HOME", Path.home() / ".minibrowser"))
SEARCH = "https://duckduckgo.com/?q="
IMG_FILTER = "Images (*.png *.jpg *.jpeg *.webp *.gif *.bmp)"

SEARCH_ENGINES = [
    ("DuckDuckGo", "https://duckduckgo.com/?q="),
    ("Google", "https://www.google.com/search?q="),
    ("Bing", "https://www.bing.com/search?q="),
    ("Startpage", "https://www.startpage.com/sp/search?query="),
]

ACTIONS = [
    ("search", "Search bar", ["Ctrl+L", "Ctrl+K"]),
    ("settings", "Browser Settings", ["Ctrl+,"]),
    ("history", "History", ["Ctrl+H"]),
    ("bookmarks", "Bookmarks list", ["Ctrl+B"]),
    ("bookmark", "Bookmark this page", ["Ctrl+D"]),
    ("delete_bookmark", "Delete bookmark", ["Ctrl+Shift+D"]),
    ("find", "Find in page", ["Ctrl+F"]),
    ("new_tab", "New tab", ["Ctrl+T"]),
    ("close_tab", "Close tab (last one quits)", ["Ctrl+W"]),
    ("reopen_tab", "Reopen closed tab", ["Ctrl+Shift+T"]),
    ("next_tab", "Next tab", ["Ctrl+Tab", "Ctrl+PgDown"]),
    ("prev_tab", "Previous tab", ["Ctrl+Shift+Tab", "Ctrl+PgUp"]),
    ("zoom_in", "Zoom in", ["Ctrl+=", "Ctrl++"]),
    ("zoom_out", "Zoom out", ["Ctrl+-"]),
    ("zoom_reset", "Reset zoom", ["Ctrl+0"]),
    ("back", "Back", ["Alt+Left"]),
    ("forward", "Forward", ["Alt+Right"]),
    ("reload", "Reload", ["F5", "Ctrl+R"]),
    ("wallpaper", "Choose wallpaper", ["Ctrl+Shift+W"]),
    ("wallpaper_off", "Remove wallpaper", ["Ctrl+Alt+W"]),
    ("clear_data", "Clear history, cookies, cache, permissions", ["Ctrl+Shift+Del"]),
    ("language", "Change language", ["Ctrl+Shift+L"]),
    ("widevine", "DRM / Widevine setup", ["Ctrl+Shift+V"]),
    ("extensions", "Extensions", ["Ctrl+Shift+E"]),
    ("fullscreen", "Fullscreen", ["F11"]),
    ("help", "Shortcuts (this window)", ["F1", "Ctrl+/"]),
]
DEFAULTS = {aid: keys for aid, _d, keys in ACTIONS}
FIXED = [("Ctrl+1 .. Ctrl+9", "Jump to tab"), ("Esc", "Close search bar / dialogs")]


def norm(key):
    return QKeySequence(key).toString(QKeySequence.SequenceFormat.PortableText)


def reserved_keys():
    return {norm("Esc")} | {norm(f"Ctrl+{i}") for i in range(1, 10)}


DEFAULT_LANG = "en-US"
LANGUAGES = [
    ("English (US)", "en-US"),
    ("English (UK)", "en-GB"),
    ("Urdu", "ur"),
    ("Arabic", "ar"),
    ("Hindi", "hi"),
    ("French", "fr"),
    ("German", "de"),
    ("Spanish", "es"),
    ("Portuguese (Brazil)", "pt-BR"),
    ("Russian", "ru"),
    ("Turkish", "tr"),
    ("Chinese (Simplified)", "zh-CN"),
    ("Japanese", "ja"),
    ("System default", ""),
]


def accept_language(code):
    if not code:
        return ""
    base = code.split("-")[0]
    return f"{code},{base};q=0.9" if base != code else code


LOCAL_RE = re.compile(r"^(localhost|\d{1,3}(\.\d{1,3}){3})(:\d+)?([/?#].*)?$")


FALLBACK_CHROME_MAJOR = "131"


def get_chrome_user_agent(engine_ua=""):
    system = platform.system()
    # Report the Chromium version of the embedded engine so the user agent never
    # goes stale. Real Chrome reports "MAJOR.0.0.0"; fall back to a fixed
    # version if the engine's own user agent can't be read.
    match = re.search(r"Chrome/(\d+)\.", engine_ua or "")
    chrome_version = f"{match.group(1) if match else FALLBACK_CHROME_MAJOR}.0.0.0"
    if system == "Windows":
        ua = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version} Safari/537.36"
        plat = "Windows"
    elif system == "Darwin":
        ua = f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version} Safari/537.36"
        plat = "macOS"
    else:
        ua = f"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version} Safari/537.36"
        plat = "Linux"
    return ua, plat, chrome_version


def get_firefox_user_agent():
    system = platform.system()
    if system == "Windows":
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"
    elif system == "Darwin":
        return "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0"
    else:
        return "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0"


class AuthRequestInterceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.firefox_ua = get_firefox_user_agent().encode("utf-8")

    def interceptRequest(self, info: QWebEngineUrlRequestInfo):
        host = info.requestUrl().host().lower()
        if (
            host == "accounts.google.com"
            or host.endswith(".accounts.google.com")
            or host == "accounts.youtube.com"
        ):
            info.setHttpHeader(b"User-Agent", self.firefox_ua)


def find_widevine_path(custom_path=None):
    if custom_path and Path(custom_path).is_file():
        return str(Path(custom_path).resolve())

    filename = (
        "widevinecdm.dll"
        if sys.platform == "win32"
        else (
            "libwidevinecdm.dylib" if sys.platform == "darwin" else "libwidevinecdm.so"
        )
    )

    for cand in [DATA / "widevine" / filename, DATA / filename]:
        if cand.is_file():
            return str(cand.resolve())

    system = platform.system()
    search_dirs = []

    if system == "Windows":
        local = os.environ.get("LOCALAPPDATA", "")
        appdata = os.environ.get("APPDATA", "")
        pf = os.environ.get("PROGRAMFILES", "C:\\Program Files")
        pf86 = os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")
        if local:
            search_dirs.extend(
                [
                    Path(local) / "Google" / "Chrome" / "User Data" / "WidevineCdm",
                    Path(local) / "Microsoft" / "Edge" / "User Data" / "WidevineCdm",
                    Path(local)
                    / "BraveSoftware"
                    / "Brave-Browser"
                    / "User Data"
                    / "WidevineCdm",
                ]
            )
        if pf:
            search_dirs.extend(
                [
                    Path(pf) / "Google" / "Chrome" / "Application",
                    Path(pf) / "Microsoft" / "Edge" / "Application",
                ]
            )
        if pf86:
            search_dirs.append(Path(pf86) / "Google" / "Chrome" / "Application")
        if appdata:
            search_dirs.append(Path(appdata) / "Mozilla" / "Firefox" / "Profiles")
    elif system == "Darwin":
        home = Path.home()
        search_dirs.extend(
            [
                Path("/Applications/Google Chrome.app/Contents/Frameworks"),
                Path("/Applications/Microsoft Edge.app/Contents/Frameworks"),
                Path("/Applications/Brave Browser.app/Contents/Frameworks"),
                home / "Library/Application Support/Google/Chrome/WidevineCdm",
                home / "Library/Application Support/Firefox/Profiles",
            ]
        )
    else:
        home = Path.home()
        search_dirs.extend(
            [
                Path("/opt/google/chrome"),
                Path("/opt/brave.com"),
                Path("/usr/lib/chromium"),
                Path("/usr/lib/chromium-browser"),
                Path("/usr/lib/x86_64-linux-gnu/chromium"),
                home / ".config/google-chrome",
                home / ".mozilla/firefox",
            ]
        )

    for base_dir in search_dirs:
        try:
            if base_dir.is_dir():
                for p in base_dir.rglob(filename):
                    if p.is_file():
                        return str(p.resolve())
        except OSError:
            continue
    return None


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.executescript(
            "CREATE TABLE IF NOT EXISTS history(url TEXT PRIMARY KEY, title TEXT,"
            " visits INTEGER DEFAULT 1, last REAL);"
            "CREATE TABLE IF NOT EXISTS bookmarks(url TEXT PRIMARY KEY, title TEXT,"
            " added REAL);"
        )

    def visit(self, url, title):
        self.db.execute(
            "INSERT INTO history(url,title,visits,last) VALUES(?,?,1,?) "
            "ON CONFLICT(url) DO UPDATE SET title=excluded.title, "
            "visits=visits+1, last=excluded.last",
            (url, title, time.time()),
        )
        self.db.commit()

    def toggle_bookmark(self, url, title):
        if self.db.execute("SELECT 1 FROM bookmarks WHERE url=?", (url,)).fetchone():
            self.db.execute("DELETE FROM bookmarks WHERE url=?", (url,))
            added = False
        else:
            self.db.execute(
                "INSERT INTO bookmarks VALUES(?,?,?)", (url, title, time.time())
            )
            added = True
        self.db.commit()
        return added

    def remove_bookmark(self, url):
        if self.db.execute("SELECT 1 FROM bookmarks WHERE url=?", (url,)).fetchone():
            self.db.execute("DELETE FROM bookmarks WHERE url=?", (url,))
            self.db.commit()
            return True
        return False

    def clear_bookmarks(self):
        self.db.execute("DELETE FROM bookmarks")
        self.db.commit()

    def suggest(self, q, kind="all"):
        q = q.strip().lower()
        like = "(instr(lower(url),?)>0 OR instr(lower(title),?)>0)"
        out, seen = [], set()

        def add(sql, star):
            for url, title in self.db.execute(sql, (q, q)):
                if url not in seen:
                    seen.add(url)
                    out.append((url, title or "", star))

        if kind in ("all", "bookmarks"):
            add(
                f"SELECT url,title FROM bookmarks WHERE {like} ORDER BY added DESC LIMIT 10",
                True,
            )
        if kind in ("all", "history"):
            order = "visits DESC, last DESC" if q else "last DESC"
            add(
                f"SELECT url,title FROM history WHERE {like} ORDER BY {order} LIMIT 12",
                False,
            )
        return out

    def clear_history(self):
        self.db.execute("DELETE FROM history")
        self.db.commit()


def load_config():
    try:
        return json.loads((DATA / "config.json").read_text())
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    try:
        (DATA / "config.json").write_text(json.dumps(cfg, indent=2))
    except OSError:
        pass


def to_url(text, search_base=SEARCH):
    text = text.strip()
    if not text:
        return None
    lower = text.lower()
    if lower.startswith(("javascript:", "vbscript:")):
        return None
    if "://" in text or text.startswith(("about:", "file:", "data:")):
        return QUrl(text)
    if " " not in text:
        if LOCAL_RE.match(text):
            return QUrl("http://" + text)
        if "." in text:
            return QUrl("https://" + text)
    return QUrl(search_base + quote_plus(text))


class CustomWebPage(QWebEnginePage):
    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        # Prevent double-dialog registration: use either Qt 6.8+ or fallback
        if hasattr(self, "permissionRequested"):
            try:
                self.permissionRequested.connect(self._on_permission_requested)
            except Exception:
                pass
        elif hasattr(self, "featurePermissionRequested"):
            try:
                self.featurePermissionRequested.connect(self._on_feature_permission)
            except Exception:
                pass

        self.windowCloseRequested.connect(self._on_window_close)

    def _get_browser(self):
        view = self.view()
        if view and hasattr(view, "browser"):
            return view.browser
        return None

    def _prompt_permission(self, origin_url, feature_key, feature_name):
        qurl = QUrl(origin_url) if isinstance(origin_url, str) else origin_url
        if qurl.isValid() and qurl.host():
            origin_str = f"{qurl.scheme()}://{qurl.host()}"
            if qurl.port() != -1:
                origin_str += f":{qurl.port()}"
        else:
            origin_str = qurl.toString() if qurl.isValid() else "Unknown Origin"

        browser = self._get_browser()
        if browser and "permissions" in browser.cfg:
            site_perms = browser.cfg["permissions"].get(origin_str, {})
            if feature_key in site_perms:
                return site_perms[feature_key]

        parent_win = browser or self.view()
        msg_box = QMessageBox(parent_win)
        msg_box.setWindowTitle("Security & Privacy Request")
        msg_box.setIcon(QMessageBox.Icon.Question)
        msg_box.setText(
            f"The website at:\n\n{origin_str}\n\n"
            f"is requesting access to:\n🔒 {feature_name}\n\n"
            f"Do you want to grant this website access?"
        )
        allow_btn = msg_box.addButton("Allow", QMessageBox.ButtonRole.AcceptRole)
        deny_btn = msg_box.addButton("Deny", QMessageBox.ButtonRole.RejectRole)
        msg_box.setDefaultButton(deny_btn)

        cb = QCheckBox("Remember this choice for this site")
        msg_box.setCheckBox(cb)
        msg_box.exec()
        allowed = msg_box.clickedButton() == allow_btn

        if cb.isChecked() and browser:
            perms = browser.cfg.setdefault("permissions", {})
            perms.setdefault(origin_str, {})[feature_key] = allowed
            save_config(browser.cfg)

        if browser:
            browser.toast(f"{feature_name}: {'granted' if allowed else 'denied'}")
        return allowed

    def _on_permission_requested(self, permission):
        try:
            ptype = permission.permissionType()
            type_name = getattr(ptype, "name", str(ptype))
            readable = {
                "Geolocation": "Physical Location (GPS)",
                "Microphone": "Microphone / Audio Recording",
                "Camera": "Webcam / Camera",
                "Notifications": "Desktop Notifications",
                "DesktopVideoCapture": "Screen Capture / Sharing",
                "DesktopAudioVideoCapture": "Screen & Audio Capture",
                "ClipboardReadWrite": "Clipboard Read / Write",
                "LocalFonts": "Locally Installed Fonts",
                "WindowManagement": "Multi-Window Control",
            }.get(type_name, type_name)

            if self._prompt_permission(permission.origin(), type_name, readable):
                permission.grant()
            else:
                permission.deny()
        except Exception:
            try:
                permission.deny()
            except Exception:
                pass

    def _on_feature_permission(self, origin, feature):
        try:
            feature_name = getattr(feature, "name", str(feature))
            readable = {
                "Geolocation": "Physical Location (GPS)",
                "MediaAudioCapture": "Microphone / Audio Recording",
                "MediaVideoCapture": "Webcam / Camera",
                "MediaAudioVideoCapture": "Camera & Microphone",
                "MouseLock": "Mouse Pointer Lock",
                "DesktopVideoCapture": "Screen Capture / Sharing",
                "DesktopAudioVideoCapture": "Screen & Audio Capture",
                "Notifications": "Desktop Notifications",
            }.get(feature_name, feature_name)

            allowed = self._prompt_permission(origin, feature_name, readable)
            policy = (
                QWebEnginePage.PermissionPolicy.PermissionGrantedByUser
                if allowed
                else QWebEnginePage.PermissionPolicy.PermissionDeniedByUser
            )
            self.setFeaturePermission(origin, feature, policy)
        except Exception:
            try:
                self.setFeaturePermission(
                    origin,
                    feature,
                    QWebEnginePage.PermissionPolicy.PermissionDeniedByUser,
                )
            except Exception:
                pass

    def _on_window_close(self):
        view = self.view()
        if view and hasattr(view, "browser"):
            view.browser.close_tab_instance(view)


class Tab(QWebEngineView):
    def __init__(self, browser, blank=True):
        super().__init__()
        self.browser = browser
        self.blank = blank
        self.pending = None
        self.setPage(CustomWebPage(browser.profile, self))
        self.page().settings().setAttribute(
            QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True
        )
        self.page().fullScreenRequested.connect(browser.on_fullscreen)
        self.titleChanged.connect(browser.refresh_title)
        self.loadFinished.connect(self._loaded)

    def navigate(self, url):
        self.blank = False
        self.pending = None
        self.setUrl(url)

    def _loaded(self, ok):
        url = self.url()
        url_str = url.toString()
        if ok and not self.blank and url.scheme() in ("http", "https"):
            self.browser.store.visit(url_str, self.title())
            if self.browser.cfg.get("force_fonts", True):
                self.browser.inject_fonts_to_tab(self)
            if "crunchyroll.com" in url_str and not self.browser.widevine_path:
                self.browser.toast(
                    "Notice: Crunchyroll requires Widevine DRM (Press Ctrl+Shift+V)"
                )

    def show_blank(self):
        self.blank = True
        self.setHtml(self.browser.get_wallpaper_html(), QUrl("about:blank"))

    def current_url(self):
        return self.pending or self.url().toString()

    def createWindow(self, _type):
        return self.browser.new_tab(focus_bar=False, blank=False)


class SettingsDialog(QDialog):
    def __init__(self, browser):
        super().__init__(browser)
        self.b = browser
        self.setWindowTitle("Settings")
        self.resize(650, 580)
        self.setStyleSheet(
            "QDialog,QTabWidget::pane{background:#14141a;color:#ddd;}"
            "QTabBar::tab{background:#1d1d25;color:#aaa;padding:8px 16px;border-top-left-radius:6px;border-top-right-radius:6px;margin-right:2px;}"
            "QTabBar::tab:selected{background:#282834;color:#fff;font-weight:bold;}"
            "QLabel{color:#ccc;font-size:13px;}"
            "QLineEdit,QSpinBox,QFontComboBox,QComboBox{background:#1d1d25;color:#fff;border:1px solid #444;border-radius:5px;padding:6px 8px;font-size:13px;}"
            "QLineEdit:focus,QSpinBox:focus,QFontComboBox:focus,QComboBox:focus{border:1px solid #4a7;}"
            "QPushButton{background:#22222a;color:#ccc;border:1px solid #444;border-radius:6px;padding:6px 14px;font-size:13px;}"
            "QPushButton:hover{background:#2c2c36;color:#fff;}"
            "QPushButton#primary{background:#2a6645;color:#fff;border:1px solid #3c885c;}"
            "QPushButton#primary:hover{background:#358057;}"
            "QCheckBox{color:#ddd;font-size:13px;spacing:6px;}"
            "QGroupBox{border:1px solid #333;border-radius:6px;margin-top:12px;padding-top:14px;color:#8ab;font-weight:bold;}"
            "QGroupBox::title{subcontrol-origin:margin;left:10px;padding:0 4px;}"
        )

        main_lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        main_lay.addWidget(self.tabs)

        # Tab 1: General & Downloads
        t_gen = QWidget()
        lay_gen = QVBoxLayout(t_gen)

        gb_dl = QGroupBox("Downloads")
        lay_dl = QVBoxLayout(gb_dl)
        row_dl = QHBoxLayout()
        self.dl_edit = QLineEdit(str(self.b.get_download_dir()))
        btn_browse_dl = QPushButton("Browse...")
        btn_browse_dl.clicked.connect(self.browse_download_folder)
        row_dl.addWidget(self.dl_edit)
        row_dl.addWidget(btn_browse_dl)
        lay_dl.addWidget(QLabel("Download Folder:"))
        lay_dl.addLayout(row_dl)

        self.cb_ask_dl = QCheckBox(
            "Always ask where to save each file before downloading"
        )
        self.cb_ask_dl.setChecked(self.b.cfg.get("ask_download", True))
        lay_dl.addWidget(self.cb_ask_dl)
        lay_gen.addWidget(gb_dl)

        gb_search = QGroupBox("Search Engine")
        lay_search = QFormLayout(gb_search)
        self.search_combo = QComboBox()
        for name, url in SEARCH_ENGINES:
            self.search_combo.addItem(name, url)
        self.search_combo.addItem("Custom URL Pattern", "custom")

        curr_search = self.b.cfg.get("search_url", SEARCH)
        matched_idx = -1
        for idx in range(self.search_combo.count() - 1):
            if self.search_combo.itemData(idx) == curr_search:
                matched_idx = idx
                break
        if matched_idx != -1:
            self.search_combo.setCurrentIndex(matched_idx)
        else:
            self.search_combo.setCurrentIndex(self.search_combo.count() - 1)

        self.custom_search_edit = QLineEdit(curr_search)
        self.custom_search_edit.setPlaceholderText("https://example.com/search?q=")
        self.search_combo.currentIndexChanged.connect(self._on_search_changed)
        self._on_search_changed()

        lay_search.addRow("Default Search:", self.search_combo)
        lay_search.addRow("Search URL Pattern:", self.custom_search_edit)
        lay_gen.addWidget(gb_search)
        lay_gen.addStretch()
        self.tabs.addTab(t_gen, "General & Downloads")

        # Tab 2: Fonts & Appearance
        t_fonts = QWidget()
        lay_fonts = QVBoxLayout(t_fonts)

        gb_families = QGroupBox("Font Families")
        form_families = QFormLayout(gb_families)
        f_cfg = self.b.cfg.get("fonts", {})

        self.font_standard = QFontComboBox()
        if f_cfg.get("standard"):
            self.font_standard.setCurrentFont(QFont(f_cfg["standard"]))

        self.font_fixed = QFontComboBox()
        try:
            self.font_fixed.setFontFilters(QFontComboBox.FontFilter.MonospacedFonts)
        except Exception:
            pass
        if f_cfg.get("fixed"):
            self.font_fixed.setCurrentFont(QFont(f_cfg["fixed"]))

        self.font_serif = QFontComboBox()
        if f_cfg.get("serif"):
            self.font_serif.setCurrentFont(QFont(f_cfg["serif"]))

        self.font_sans = QFontComboBox()
        if f_cfg.get("sans_serif"):
            self.font_sans.setCurrentFont(QFont(f_cfg["sans_serif"]))

        form_families.addRow("Standard Font:", self.font_standard)
        form_families.addRow("Fixed-Pitch (Monospace):", self.font_fixed)
        form_families.addRow("Serif Font:", self.font_serif)
        form_families.addRow("Sans-Serif Font:", self.font_sans)
        lay_fonts.addWidget(gb_families)

        gb_sizes = QGroupBox("Font Sizes (Pixels)")
        form_sizes = QFormLayout(gb_sizes)

        self.spin_def_size = QSpinBox()
        self.spin_def_size.setRange(8, 72)
        self.spin_def_size.setValue(int(f_cfg.get("default_size", 16)))

        self.spin_fixed_size = QSpinBox()
        self.spin_fixed_size.setRange(8, 72)
        self.spin_fixed_size.setValue(int(f_cfg.get("default_fixed_size", 13)))

        self.spin_min_size = QSpinBox()
        self.spin_min_size.setRange(0, 32)
        self.spin_min_size.setValue(int(f_cfg.get("min_size", 0)))

        form_sizes.addRow("Default Size:", self.spin_def_size)
        form_sizes.addRow("Fixed-Pitch Size:", self.spin_fixed_size)
        form_sizes.addRow("Minimum Size:", self.spin_min_size)
        lay_fonts.addWidget(gb_sizes)

        self.cb_force_fonts = QCheckBox(
            "Force custom fonts on all websites (overrides website font styles)"
        )
        self.cb_force_fonts.setChecked(self.b.cfg.get("force_fonts", True))
        lay_fonts.addWidget(self.cb_force_fonts)

        btn_reset_fonts = QPushButton("Reset Fonts to Defaults")
        btn_reset_fonts.clicked.connect(self.reset_fonts)
        lay_fonts.addWidget(btn_reset_fonts)
        lay_fonts.addStretch()
        self.tabs.addTab(t_fonts, "Fonts & Appearance")

        # Tab 3: Language & Privacy
        t_priv = QWidget()
        lay_priv = QVBoxLayout(t_priv)

        gb_lang = QGroupBox("Language")
        form_lang = QFormLayout(gb_lang)
        self.lang_combo = QComboBox()
        curr_lang = self.b.cfg.get("language", DEFAULT_LANG)
        for name, code in LANGUAGES:
            self.lang_combo.addItem(name, code)
            if code == curr_lang:
                self.lang_combo.setCurrentIndex(self.lang_combo.count() - 1)
        form_lang.addRow("Browser Language:", self.lang_combo)
        lay_priv.addWidget(gb_lang)

        gb_drm = QGroupBox("DRM & Widevine")
        lay_drm = QVBoxLayout(gb_drm)
        drm_txt = self.b.widevine_path or "Not automatically detected"
        lay_drm.addWidget(QLabel(f"Current CDM: {drm_txt}"))
        btn_drm = QPushButton("Configure Widevine Path...")
        btn_drm.clicked.connect(self.b.manage_widevine)
        lay_drm.addWidget(btn_drm)
        lay_priv.addWidget(gb_drm)

        gb_data = QGroupBox("Browsing Data")
        lay_data = QVBoxLayout(gb_data)
        btn_clear = QPushButton("Clear Browsing Data (Cookies, Cache, History)...")
        btn_clear.clicked.connect(self.b.clear_data)
        lay_data.addWidget(btn_clear)
        lay_priv.addWidget(gb_data)

        lay_priv.addStretch()
        self.tabs.addTab(t_priv, "Language & Privacy")

        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        btn_save = QPushButton("Save & Apply")
        btn_save.setObjectName("primary")
        btn_save.clicked.connect(self.save)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        bottom_row.addWidget(btn_cancel)
        bottom_row.addWidget(btn_save)
        main_lay.addLayout(bottom_row)

    def _on_search_changed(self):
        is_custom = self.search_combo.currentData() == "custom"
        self.custom_search_edit.setEnabled(is_custom)
        if not is_custom:
            self.custom_search_edit.setText(self.search_combo.currentData())

    def browse_download_folder(self):
        current = self.dl_edit.text()
        chosen = QFileDialog.getExistingDirectory(
            self, "Select Download Directory", current
        )
        if chosen:
            self.dl_edit.setText(str(Path(chosen).resolve()))

    def reset_fonts(self):
        self.font_standard.setCurrentFont(QFont("Times New Roman"))
        self.font_fixed.setCurrentFont(QFont("Courier New"))
        self.font_serif.setCurrentFont(QFont("Times New Roman"))
        self.font_sans.setCurrentFont(QFont("Arial"))
        self.spin_def_size.setValue(16)
        self.spin_fixed_size.setValue(13)
        self.spin_min_size.setValue(0)
        self.cb_force_fonts.setChecked(True)

    def save(self):
        dl_dir = self.dl_edit.text().strip()
        if dl_dir:
            self.b.cfg["download_dir"] = dl_dir
        self.b.cfg["ask_download"] = self.cb_ask_dl.isChecked()

        search_data = self.search_combo.currentData()
        if search_data == "custom":
            self.b.cfg["search_url"] = self.custom_search_edit.text().strip() or SEARCH
        else:
            self.b.cfg["search_url"] = search_data

        self.b.cfg["fonts"] = {
            "standard": self.font_standard.currentFont().family(),
            "fixed": self.font_fixed.currentFont().family(),
            "serif": self.font_serif.currentFont().family(),
            "sans_serif": self.font_sans.currentFont().family(),
            "default_size": self.spin_def_size.value(),
            "default_fixed_size": self.spin_fixed_size.value(),
            "min_size": self.spin_min_size.value(),
        }
        self.b.cfg["force_fonts"] = self.cb_force_fonts.isChecked()

        new_lang = self.lang_combo.currentData()
        if new_lang != self.b.cfg.get("language"):
            self.b.cfg["language"] = new_lang
            self.b.profile.setHttpAcceptLanguage(
                accept_language(new_lang) or "en-US,en"
            )

        save_config(self.b.cfg)
        self.b.apply_font_settings()
        self.b.toast("Settings saved and applied")
        self.accept()


class KeysDialog(QDialog):
    def __init__(self, browser):
        super().__init__(browser)
        self.b = browser
        self.setWindowTitle("Shortcuts")
        self.resize(680, 700)
        self.setStyleSheet(
            "QDialog,QTableWidget{background:#14141a;color:#ddd;}"
            "QTableWidget{gridline-color:#2a2a33;border:1px solid #333;}"
            "QHeaderView::section{background:#22222a;color:#aaa;border:0;padding:6px;}"
            "QPushButton{background:#22222a;color:#ccc;border:1px solid #444;"
            "border-radius:6px;padding:4px 10px;}"
            "QPushButton:hover{background:#2c2c36;}"
            "QKeySequenceEdit{background:#1d1d25;color:#7fd;border:1px solid #444;}"
            "QLabel{color:#aaa;}"
        )
        lay = QVBoxLayout(self)
        lay.addWidget(
            QLabel(
                "Click a Shortcut box, then press the keys you want.  "
                "Click a Default to restore it.  (Ctrl = Cmd on macOS)"
            )
        )

        self.table = QTableWidget(len(ACTIONS) + len(FIXED), 3)
        self.table.setHorizontalHeaderLabels(["Action", "Shortcut", "Default"])
        self.table.verticalHeader().hide()
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 240)
        self.table.setColumnWidth(1, 190)
        self.edits = {}
        for row, (aid, desc, defaults) in enumerate(ACTIONS):
            self.table.setItem(row, 0, self._cell(desc))
            edit = QKeySequenceEdit(QKeySequence(browser.keys_for(aid)[0]))
            try:
                edit.setMaximumSequenceLength(1)
            except AttributeError:
                pass
            edit.editingFinished.connect(lambda aid=aid: self.changed(aid))
            self.table.setCellWidget(row, 1, edit)
            self.edits[aid] = edit
            btn = QPushButton(" / ".join(defaults))
            btn.setToolTip("Restore the default")
            btn.clicked.connect(lambda _=False, aid=aid: self.reset(aid))
            self.table.setCellWidget(row, 2, btn)
        for i, (key, desc) in enumerate(FIXED):
            row = len(ACTIONS) + i
            self.table.setItem(row, 0, self._cell(desc))
            self.table.setItem(row, 1, self._cell(key))
            self.table.setItem(row, 2, self._cell("fixed"))
        lay.addWidget(self.table)

        self.msg = QLabel("")
        lay.addWidget(self.msg)
        buttons = QHBoxLayout()
        reset_all = QPushButton("Reset all to defaults")
        reset_all.clicked.connect(self.reset_all)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        buttons.addWidget(reset_all)
        buttons.addStretch()
        buttons.addWidget(close)
        lay.addLayout(buttons)

    @staticmethod
    def _cell(text):
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        return item

    def _desc(self, aid):
        return next(d for a, d, _ in ACTIONS if a == aid)

    def changed(self, aid):
        edit = self.edits[aid]
        key = edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        current = self.b.keys_for(aid)[0]
        if not key:
            edit.setKeySequence(QKeySequence(current))
            return
        owner = self.b.key_owner(key, skip=aid)
        if owner:
            self.msg.setText(f"{key} is already used by: {owner}")
            edit.setKeySequence(QKeySequence(current))
            return
        self.b.set_key(aid, key)
        self.msg.setText(f"{self._desc(aid)} = {key}")

    def reset(self, aid):
        for key in DEFAULTS[aid]:
            owner = self.b.key_owner(key, skip=aid)
            if owner:
                self.msg.setText(
                    f"Default {key} is used by: {owner} - change that first"
                )
                return
        self.b.set_key(aid, None)
        self.edits[aid].setKeySequence(QKeySequence(DEFAULTS[aid][0]))
        self.msg.setText(f"{self._desc(aid)} restored to default")

    def reset_all(self):
        self.b.reset_keys()
        for aid, edit in self.edits.items():
            edit.setKeySequence(QKeySequence(DEFAULTS[aid][0]))
        self.msg.setText("All shortcuts restored to defaults")


class ExtensionsDialog(QDialog):
    def __init__(self, browser, manager):
        super().__init__(browser)
        self.b, self.m, self.infos = browser, manager, []
        self.setWindowTitle("Extensions")
        self.resize(620, 440)
        self.setStyleSheet(
            "QDialog,QListWidget{background:#14141a;color:#ddd;}"
            "QListWidget{border:1px solid #333;font-size:14px;}"
            "QListWidget::item{padding:6px;}"
            "QPushButton{background:#22222a;color:#ccc;border:1px solid #444;"
            "border-radius:6px;padding:5px 12px;}"
            "QPushButton:hover{background:#2c2c36;}QLabel{color:#aaa;}"
        )
        lay = QVBoxLayout(self)
        lay.addWidget(
            QLabel(
                "Tick = enabled.  Add an unpacked extension folder (with manifest.json) "
                "or a .zip.\nOnly Manifest V3 extensions work. The Chrome Web Store "
                "can't be used directly."
            )
        )
        self.list = QListWidget()
        lay.addWidget(self.list)
        row = QHBoxLayout()
        for text, fn in [
            ("Add folder...", self.add_folder),
            ("Add .zip...", self.add_zip),
            ("Open popup", self.open_popup),
            ("Remove", self.remove),
        ]:
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, fn=fn: fn())
            row.addWidget(b)
        row.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)

        for sig in (
            manager.loadFinished,
            manager.uninstallFinished,
            manager.unloadFinished,
        ):
            sig.connect(lambda *_: self.refresh())
        manager.installFinished.connect(self.installed)
        self.list.itemChanged.connect(self.toggled)
        self.refresh()

    def refresh(self):
        self.infos = list(self.m.extensions())
        self.list.blockSignals(True)
        self.list.clear()
        for info in self.infos:
            text = info.name() or info.path()
            if info.error():
                text += f"   (error: {info.error()})"
            elif info.description():
                text += f"  -  {info.description()}"
            item = QListWidgetItem(text)
            item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            item.setCheckState(
                Qt.CheckState.Checked if info.isEnabled() else Qt.CheckState.Unchecked
            )
            self.list.addItem(item)
        self.list.blockSignals(False)

    def toggled(self, item):
        row = self.list.row(item)
        if 0 <= row < len(self.infos):
            self.m.setExtensionEnabled(
                self.infos[row], item.checkState() == Qt.CheckState.Checked
            )

    def installed(self, info):
        if info.isLoaded():
            if not info.isEnabled():
                self.m.setExtensionEnabled(info, True)
            self.refresh()
        else:
            QMessageBox.warning(
                self,
                "Extension not installed",
                info.error() or "The extension could not be installed.",
            )

    def add_folder(self):
        path = QFileDialog.getExistingDirectory(
            self, "Choose an unpacked extension folder (contains manifest.json)"
        )
        if path:
            self.m.installExtension(path)

    def add_zip(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose an extension .zip", "", "Extension (*.zip)"
        )
        if path:
            self.m.installExtension(path)

    def selected(self):
        row = self.list.currentRow()
        return self.infos[row] if 0 <= row < len(self.infos) else None

    def remove(self):
        info = self.selected()
        if (
            info
            and QMessageBox.question(
                self, "Remove extension", f"Remove {info.name() or info.path()}?"
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.m.uninstallExtension(info)

    def open_popup(self):
        info = self.selected()
        if not info:
            return
        url = info.actionPopupUrl()
        if url.isEmpty():
            QMessageBox.information(
                self, "No popup", "This extension has no popup page."
            )
            return
        self.b.new_tab(focus_bar=False, blank=False).navigate(url)
        self.accept()


class Browser(QMainWindow):
    def __init__(self, start_url=None, widevine_path=None):
        super().__init__()
        DATA.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "chmod") and sys.platform != "win32":
            try:
                os.chmod(DATA, 0o700)
            except OSError:
                pass

        self.cfg = load_config()
        self.store = Store(DATA / "history.db")
        self.closed = []
        self.mode = "url"
        self.kind = "all"
        self.sugg = {}
        self.quitting_clean = False
        self.widevine_path = widevine_path

        self._wallpaper_cache_path = None
        self._wallpaper_html_cache = None

        self.profile = QWebEngineProfile("mini", QApplication.instance())
        self.profile.setPersistentStoragePath(str(DATA / "web"))
        self.profile.setCachePath(str(DATA / "cache"))
        self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
        self.profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
        )

        # Read the engine's default user agent *before* overriding it
        ua_str, ua_platform, ua_version = get_chrome_user_agent(
            self.profile.httpUserAgent()
        )
        self.profile.setHttpUserAgent(ua_str)

        self.auth_interceptor = AuthRequestInterceptor(self)
        self.profile.setUrlRequestInterceptor(self.auth_interceptor)

        settings = self.profile.settings()
        for disabled_attr in [
            "LocalContentCanAccessRemoteUrls",
            "LocalContentCanAccessFileUrls",
        ]:
            if hasattr(QWebEngineSettings.WebAttribute, disabled_attr):
                settings.setAttribute(
                    getattr(QWebEngineSettings.WebAttribute, disabled_attr), False
                )

        for enabled_attr in [
            "FullScreenSupportEnabled",
            "LocalStorageEnabled",
            "WebGLEnabled",
            "Accelerated2dCanvasEnabled",
            "PluginsEnabled",
            "DnsPrefetchEnabled",
            "PdfViewerEnabled",
            "ScreenCaptureEnabled",
            "JavascriptCanAccessClipboard",
            "JavascriptCanPaste",
        ]:
            if hasattr(QWebEngineSettings.WebAttribute, enabled_attr):
                settings.setAttribute(
                    getattr(QWebEngineSettings.WebAttribute, enabled_attr), True
                )

        if hasattr(QWebEngineSettings.WebAttribute, "PlaybackRequiresUserGesture"):
            settings.setAttribute(
                getattr(QWebEngineSettings.WebAttribute, "PlaybackRequiresUserGesture"),
                True,
            )

        accept = accept_language(self.cfg.get("language", DEFAULT_LANG))
        if accept:
            self.profile.setHttpAcceptLanguage(accept)
        self.profile.downloadRequested.connect(self.on_download)

        # 1. Instantiate visual shell widgets first
        self.setWindowTitle("Mini")
        self.resize(1200, 800)
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.bar = QLineEdit(self)
        self.bar.setStyleSheet(
            "QLineEdit{background:rgba(20,20,24,235);color:#eee;border:1px solid #555;"
            "border-radius:10px;padding:10px 14px;font-size:16px;"
            "selection-background-color:#4a7;}"
        )
        self.bar.returnPressed.connect(self.go)
        self.bar.textEdited.connect(self.on_edit)
        self.bar.hide()

        # 2. Now safe to apply fonts across settings, UI, and injection
        self.apply_font_settings()

        self.model = QStringListModel(self)
        self.completer = QCompleter(self.model, self)
        self.completer.setCompletionMode(
            QCompleter.CompletionMode.UnfilteredPopupCompletion
        )
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setMaxVisibleItems(12)
        self.completer.popup().setStyleSheet(
            "QListView{background:#14141a;color:#ddd;border:1px solid #555;font-size:14px;}"
            "QListView::item:selected{background:#2a5;color:#fff;}"
        )
        self.completer.popup().installEventFilter(self)
        self.completer.activated.connect(self.picked)
        self.bar.setCompleter(self.completer)

        pill = "background:rgba(20,20,24,235);color:#bbb;border-radius:8px;padding:4px 10px;"
        self.counter = QLabel(self)
        self.counter.setStyleSheet(pill)
        self.counter.hide()
        self.toast_lbl = QLabel(self)
        self.toast_lbl.setStyleSheet(pill + "font-size:14px;")
        self.toast_lbl.hide()
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.setInterval(2200)
        self.toast_timer.timeout.connect(self.toast_lbl.hide)

        self.handlers = {
            "search": lambda: self.open_bar(),
            "settings": self.show_settings,
            "history": lambda: self.open_bar(kind="history"),
            "bookmarks": lambda: self.open_bar(kind="bookmarks"),
            "bookmark": self.bookmark,
            "delete_bookmark": self.delete_bookmark,
            "find": lambda: self.open_bar(mode="find"),
            "new_tab": lambda: self.new_tab(),
            "close_tab": self.close_tab,
            "reopen_tab": self.reopen_tab,
            "next_tab": lambda: self.step_tab(1),
            "prev_tab": lambda: self.step_tab(-1),
            "zoom_in": lambda: self.zoom(0.1),
            "zoom_out": lambda: self.zoom(-0.1),
            "zoom_reset": lambda: self.zoom(0),
            "back": lambda: self.tab().back() if self.tab() else None,
            "forward": lambda: self.tab().forward() if self.tab() else None,
            "reload": lambda: self.tab().reload() if self.tab() else None,
            "wallpaper": self.pick_wallpaper,
            "wallpaper_off": self.clear_wallpaper,
            "clear_data": self.clear_data,
            "fullscreen": self.toggle_fullscreen,
            "language": self.pick_language,
            "widevine": self.manage_widevine,
            "extensions": self.show_extensions,
            "help": self.show_help,
        }
        self._shortcuts = []
        self.bind_all()

        self.restore_session()
        if start_url:
            self.new_tab(focus_bar=False, blank=False).navigate(
                to_url(start_url, self.get_search_url())
            )
        elif self.stack.count() == 0:
            self.new_tab()

    def tab(self):
        return self.stack.currentWidget()

    def get_search_url(self):
        return self.cfg.get("search_url", SEARCH)

    def get_download_dir(self):
        dl_dir = self.cfg.get("download_dir")
        if dl_dir and Path(dl_dir).is_dir():
            return Path(dl_dir)
        d = Path.home() / "Downloads"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def get_font_override_js(self):
        font_cfg = self.cfg.get("fonts", {})
        if not self.cfg.get("force_fonts", True):
            return ""

        std = font_cfg.get("standard")
        fixed = font_cfg.get("fixed")
        if not std and not fixed:
            return ""

        rules = []
        if std:
            safe_std = std.replace("\\", "\\\\").replace('"', '\\"')
            rules.append(
                f"*:not(pre,code,kbd,samp,tt,var,pre *,code *,kbd *,samp *,tt *,var *,"
                f'[class*="icon" i],[class*="fa-" i],[class*="fas" i],[class*="far" i],[class*="fab" i],'
                f'[class*="material" i],[class*="glyph" i],[class*="octicon" i],[class*="bi-" i],'
                f'[data-icon],svg,svg *,i[class],span[class*="icon" i],[class*="feather" i],[class*="tabler" i]) '
                f'{{ font-family: "{safe_std}", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important; }}'
            )
        if fixed:
            safe_fixed = fixed.replace("\\", "\\\\").replace('"', '\\"')
            rules.append(
                f"pre,code,kbd,samp,tt,var,pre *,code *,kbd *,samp *,tt *,var *,"
                f".blob-code,.highlight,textarea.code,.monaco-editor,.ace_editor "
                f'{{ font-family: "{safe_fixed}", monospace !important; }}'
            )

        css_str = "\n".join(rules)
        return f"""(function(){{
    function applyFonts(){{
        var style = document.getElementById('__minibrowser_forced_fonts__');
        if(!style){{
            style = document.createElement('style');
            style.id = '__minibrowser_forced_fonts__';
            (document.head || document.documentElement).appendChild(style);
        }}
        if(style && style.textContent !== {json.dumps(css_str)}){{
            style.textContent = {json.dumps(css_str)};
        }}
    }}
    if(document.readyState === 'loading'){{
        document.addEventListener('DOMContentLoaded', applyFonts);
    }} else {{
        applyFonts();
    }}
    window.addEventListener('load', applyFonts);
}})();"""

    def apply_font_settings(self):
        font_cfg = self.cfg.get("fonts", {})
        settings = self.profile.settings()

        std = font_cfg.get("standard")
        if std:
            settings.setFontFamily(QWebEngineSettings.FontFamily.StandardFont, std)
            if hasattr(self, "bar"):
                bar_font = self.bar.font()
                bar_font.setFamily(std)
                self.bar.setFont(bar_font)

        fixed = font_cfg.get("fixed")
        if fixed:
            settings.setFontFamily(QWebEngineSettings.FontFamily.FixedFont, fixed)

        serif = font_cfg.get("serif")
        if serif:
            settings.setFontFamily(QWebEngineSettings.FontFamily.SerifFont, serif)

        sans = font_cfg.get("sans_serif")
        if sans:
            settings.setFontFamily(QWebEngineSettings.FontFamily.SansSerifFont, sans)

        def_size = font_cfg.get("default_size")
        if def_size:
            settings.setFontSize(
                QWebEngineSettings.FontSize.DefaultFontSize, int(def_size)
            )

        def_fixed = font_cfg.get("default_fixed_size")
        if def_fixed:
            settings.setFontSize(
                QWebEngineSettings.FontSize.DefaultFixedFontSize, int(def_fixed)
            )

        min_size = font_cfg.get("min_size")
        if min_size is not None:
            settings.setFontSize(
                QWebEngineSettings.FontSize.MinimumFontSize, int(min_size)
            )

        try:
            scripts = self.profile.scripts()
            for s in scripts.findScripts("custom_user_fonts"):
                scripts.remove(s)
        except Exception:
            pass

        js_code = self.get_font_override_js()
        if js_code:
            try:
                script = QWebEngineScript()
                script.setName("custom_user_fonts")
                script.setSourceCode(js_code)
                script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
                script.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
                script.setRunsOnSubFrames(True)
                self.profile.scripts().insert(script)
            except Exception:
                pass

        if hasattr(self, "stack"):
            clean_js = "var s=document.getElementById('__minibrowser_forced_fonts__');if(s)s.remove();"
            for i in range(self.stack.count()):
                tab = self.stack.widget(i)
                if tab and not tab.blank:
                    try:
                        tab.page().runJavaScript(
                            js_code if js_code else clean_js,
                            int(QWebEngineScript.ScriptWorldId.ApplicationWorld),
                        )
                    except Exception:
                        tab.page().runJavaScript(js_code if js_code else clean_js)

    def inject_fonts_to_tab(self, tab):
        if not tab or tab.blank:
            return
        js_code = self.get_font_override_js()
        if js_code:
            try:
                tab.page().runJavaScript(
                    js_code, int(QWebEngineScript.ScriptWorldId.ApplicationWorld)
                )
            except Exception:
                tab.page().runJavaScript(js_code)

    def toast(self, text):
        self.toast_lbl.setText(text)
        self.toast_lbl.adjustSize()
        self.place_overlays()
        self.toast_lbl.show()
        self.toast_lbl.raise_()
        self.toast_timer.start()

    def refresh_title(self, *_):
        t = self.tab()
        title = t.title() if t and not t.blank else ""
        self.setWindowTitle(title or "Mini")
        self.counter.setText(f"{self.stack.currentIndex() + 1}/{self.stack.count()}")
        self.counter.adjustSize()
        self.place_overlays()

    def place_overlays(self):
        w = min(680, int(self.width() * 0.8))
        self.bar.setGeometry(
            (self.width() - w) // 2, 24, w, self.bar.sizeHint().height()
        )
        self.counter.move(self.width() - self.counter.width() - 12, 12)
        self.toast_lbl.move(
            (self.width() - self.toast_lbl.width()) // 2,
            self.height() - self.toast_lbl.height() - 24,
        )

    def keys_for(self, aid):
        custom = self.cfg.get("keys", {}).get(aid)
        return [custom] if custom else DEFAULTS[aid]

    def key_owner(self, key, skip=None):
        n = norm(key)
        if n in reserved_keys():
            return "a fixed shortcut"
        for aid, desc, _ in ACTIONS:
            if aid != skip and n in [norm(k) for k in self.keys_for(aid)]:
                return desc
        return None

    def set_key(self, aid, key):
        keys = self.cfg.setdefault("keys", {})
        if key is None:
            keys.pop(aid, None)
        else:
            keys[aid] = key
        save_config(self.cfg)
        self.bind_all()

    def reset_keys(self):
        self.cfg["keys"] = {}
        save_config(self.cfg)
        self.bind_all()

    def bind_all(self):
        for sc in self._shortcuts:
            sc.setEnabled(False)
            sc.deleteLater()
        self._shortcuts = []

        def add(key, fn):
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(Qt.ShortcutContext.WindowShortcut)
            sc.activated.connect(fn)
            self._shortcuts.append(sc)

        for aid, _desc, _defaults in ACTIONS:
            for key in self.keys_for(aid):
                add(key, self.handlers[aid])
        add("Esc", self.close_bar)
        for i in range(1, 10):
            add(f"Ctrl+{i}", lambda i=i: self.goto_tab(i - 1))

    def show_help(self):
        self.close_bar()
        KeysDialog(self).exec()

    def show_settings(self):
        self.close_bar()
        SettingsDialog(self).exec()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.place_overlays()

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def on_fullscreen(self, req):
        req.accept()
        self.showFullScreen() if req.toggleOn() else self.showNormal()

    def open_bar(self, mode="url", kind="all"):
        self.mode, self.kind = mode, kind
        t = self.tab()
        if mode == "find":
            self.bar.setCompleter(None)
            self.bar.setPlaceholderText("Find in page")
            self.bar.setText("")
        else:
            self.bar.setCompleter(self.completer)
            self.bar.setPlaceholderText(
                {
                    "all": "Search or enter address (type 'settings' for settings)",
                    "history": "History - type to filter",
                    "bookmarks": "Bookmarks - type to filter",
                }[kind]
            )
            self.bar.setText(
                "" if (not t or t.blank or kind != "all") else t.current_url()
            )
        self.refresh_title()
        self.bar.show()
        self.counter.show()
        self.bar.raise_()
        self.counter.raise_()
        self.bar.setFocus()
        self.bar.selectAll()
        if mode == "url" and kind != "all":
            QTimer.singleShot(0, lambda: self.on_edit(""))

    def close_bar(self):
        if self.bar.isVisible():
            if self.mode == "find" and self.tab():
                self.tab().findText("")
            self.bar.hide()
            self.counter.hide()
            self.completer.popup().hide()
            if self.tab():
                self.tab().setFocus()

    def on_edit(self, text):
        if self.mode == "find":
            if self.tab():
                self.tab().findText(text)
            return
        rows = self.store.suggest(text, self.kind)
        self.sugg = {}
        labels = []
        for url, title, star in rows:
            label = f"{'* ' if star else ''}{(title or url)[:60]}  -  {url}"
            self.sugg[label] = url
            labels.append(label)
        self.model.setStringList(labels)
        if labels and (text or self.kind != "all"):
            self.completer.setCompletionPrefix(text)
            self.completer.complete()
        else:
            self.completer.popup().hide()

    def picked(self, label):
        url = self.sugg.get(label, label)
        QTimer.singleShot(0, lambda: (self.bar.setText(url), self.go()))

    def go(self):
        if self.mode == "find":
            if self.tab():
                self.tab().findText(self.bar.text())
            return
        raw = self.bar.text().strip()
        if raw.lower() in ("settings", "about:settings", "about:config"):
            self.close_bar()
            self.show_settings()
            return
        url = to_url(raw, self.get_search_url())
        if url:
            if not self.tab():
                self.new_tab(focus_bar=False, blank=False)
            self.tab().navigate(url)
        self.close_bar()

    def new_tab(self, focus_bar=True, blank=True):
        t = Tab(self, blank=blank)
        if blank:
            t.show_blank()
        self.stack.addWidget(t)
        self.select(self.stack.count() - 1)
        if focus_bar:
            self.open_bar()
        return t

    def select(self, i):
        self.stack.setCurrentIndex(i)
        t = self.tab()
        if t and t.pending:
            url, t.pending = t.pending, None
            t.navigate(QUrl(url))
        self.refresh_title()

    def close_tab(self):
        self.close_tab_at(self.stack.currentIndex())

    def close_tab_at(self, idx):
        if self.stack.count() <= 1:
            self.quitting_clean = True
            self.close()
            return
        t = self.stack.widget(idx)
        if t:
            if not t.blank and t.current_url():
                self.closed.append(t.current_url())
            self.stack.removeWidget(t)
            t.deleteLater()
        self.close_bar()
        self.select(min(idx, self.stack.count() - 1))
        if self.tab():
            self.tab().setFocus()

    def close_tab_instance(self, t):
        idx = self.stack.indexOf(t)
        if idx != -1:
            self.close_tab_at(idx)

    def reopen_tab(self):
        if self.closed:
            self.new_tab(focus_bar=False, blank=False).navigate(QUrl(self.closed.pop()))
        else:
            self.toast("No closed tabs")

    def goto_tab(self, i):
        if 0 <= i < self.stack.count():
            self.select(i)
            if self.bar.isVisible():
                self.open_bar(self.mode, self.kind)
            elif self.tab():
                self.tab().setFocus()

    def step_tab(self, d):
        self.goto_tab((self.stack.currentIndex() + d) % self.stack.count())

    def zoom(self, delta):
        t = self.tab()
        if not t:
            return
        z = 1.0 if delta == 0 else max(0.25, min(5.0, t.zoomFactor() + delta))
        t.setZoomFactor(z)
        self.toast(f"{round(z * 100)}%")

    def bookmark(self):
        t = self.tab()
        if not t or t.blank or not t.current_url():
            return
        added = self.store.toggle_bookmark(t.current_url(), t.title())
        self.toast("* Bookmarked" if added else "Bookmark removed")

    def delete_bookmark(self):
        if self.bar.isVisible() and self.completer.popup().isVisible():
            idx = self.completer.popup().currentIndex()
            if idx.isValid():
                label = self.model.data(idx, Qt.ItemDataRole.DisplayRole)
                url = self.sugg.get(label)
                if url and self.store.remove_bookmark(url):
                    self.toast("Bookmark deleted")
                    self.on_edit(self.bar.text())
                    return

        t = self.tab()
        if t and not t.blank and t.current_url():
            url = t.current_url()
            if self.store.remove_bookmark(url):
                self.toast("Bookmark removed")
            else:
                self.toast("Page is not bookmarked")
        else:
            self.toast("No bookmark to remove")

    def eventFilter(self, obj, event):
        if (
            hasattr(self, "completer")
            and obj == self.completer.popup()
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Delete
        ):
            idx = self.completer.popup().currentIndex()
            if idx.isValid():
                label = self.model.data(idx, Qt.ItemDataRole.DisplayRole)
                url = self.sugg.get(label)
                if url and self.store.remove_bookmark(url):
                    self.toast("Bookmark deleted")
                    self.on_edit(self.bar.text())
                    return True
        return super().eventFilter(obj, event)

    def on_download(self, d):
        folder = self.get_download_dir()
        folder.mkdir(parents=True, exist_ok=True)

        raw_name = Path(
            d.suggestedFileName() or d.downloadFileName() or "download"
        ).name
        clean_name = re.sub(r'[\\/*?:"<>|\0]', "_", raw_name)

        ask = self.cfg.get("ask_download", True)
        if ask:
            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Downloaded File",
                str(folder / clean_name),
                "All Files (*)",
            )
            if not save_path:
                d.cancel()
                self.toast("Download cancelled")
                return
            target = Path(save_path)
        else:
            target = folder / clean_name
            counter = 1
            stem = target.stem
            suffix = target.suffix
            while target.exists():
                target = folder / f"{stem} ({counter}){suffix}"
                counter += 1

        d.setDownloadDirectory(str(target.parent))
        d.setDownloadFileName(target.name)

        def handle_finished():
            if d.isFinished():
                self.toast(f"Downloaded: {target.name}")

        d.isFinishedChanged.connect(handle_finished)
        d.accept()
        self.toast(f"Downloading {target.name} ...")

    def clear_data(self):
        ok = QMessageBox.question(
            self,
            "Clear browsing data",
            "Clear history, cookies, cache, and saved site permissions? (Bookmarks are kept.)",
        )
        if ok == QMessageBox.StandardButton.Yes:
            self.store.clear_history()
            self.profile.clearHttpCache()
            self.profile.cookieStore().deleteAllCookies()
            self.cfg.pop("permissions", None)
            save_config(self.cfg)
            self.toast("Browsing data & permissions cleared")

    def get_wallpaper_html(self):
        wp = self.cfg.get("wallpaper")
        fallback = "<!DOCTYPE html><html><body style='margin:0;height:100vh;background:#111;'></body></html>"
        if not wp:
            return fallback
        p = Path(wp)
        if not p.is_file():
            return fallback

        if self._wallpaper_cache_path == str(p) and self._wallpaper_html_cache:
            return self._wallpaper_html_cache

        try:
            ext = p.suffix.lower()
            if ext == ".gif":
                mime = "image/gif"
            elif ext == ".webp":
                mime = "image/webp"
            elif ext == ".png":
                mime = "image/png"
            elif ext in (".jpg", ".jpeg"):
                mime = "image/jpeg"
            elif ext == ".bmp":
                mime = "image/bmp"
            elif ext == ".svg":
                mime = "image/svg+xml"
            else:
                mime, _ = mimetypes.guess_type(str(p))
                if not mime or not mime.startswith("image/"):
                    mime = "image/gif" if ext == ".gif" else "image/jpeg"

            b64_data = base64.b64encode(p.read_bytes()).decode("ascii")
            img_src = f"data:{mime};base64,{b64_data}"

            html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body {{
    margin: 0;
    padding: 0;
    width: 100vw;
    height: 100vh;
    overflow: hidden;
    background-color: #111;
  }}
  .bg-media {{
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    object-fit: cover;
    object-position: center;
    pointer-events: none;
    user-select: none;
    display: block;
  }}
</style>
</head>
<body>
  <img class="bg-media" src="{img_src}" alt="Wallpaper" />
</body>
</html>"""
            self._wallpaper_cache_path = str(p)
            self._wallpaper_html_cache = html_content
            return html_content
        except Exception:
            return fallback

    def apply_wallpaper(self):
        for i in range(self.stack.count()):
            t = self.stack.widget(i)
            if t and t.blank:
                t.show_blank()

    def pick_wallpaper(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a wallpaper", "", IMG_FILTER
        )
        if path:
            self.cfg["wallpaper"] = path
            self._wallpaper_cache_path = None
            self._wallpaper_html_cache = None
            save_config(self.cfg)
            self.apply_wallpaper()

    def clear_wallpaper(self):
        self.cfg.pop("wallpaper", None)
        self._wallpaper_cache_path = None
        self._wallpaper_html_cache = None
        save_config(self.cfg)
        self.apply_wallpaper()

    def manage_widevine(self):
        self.close_bar()
        current = self.widevine_path or "Not found"
        msg = f"Current Widevine DRM CDM:\n{current}\n\n"
        if self.widevine_path:
            msg += (
                "Widevine DRM is loaded and active.\n"
                "Crunchyroll, Netflix, and other protected media should play properly.\n\n"
                "Do you want to select a different widevinecdm library file?"
            )
        else:
            msg += (
                "Widevine DRM library was not automatically detected on your system.\n"
                "To fix Crunchyroll KAT-6005, install Google Chrome or Edge,\n"
                "or manually choose a widevinecdm file.\n\n"
                "Would you like to browse and locate the file now?"
            )
        reply = QMessageBox.question(
            self,
            "Widevine DRM Setup",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            ext = (
                "*.dll"
                if sys.platform == "win32"
                else ("*.dylib" if sys.platform == "darwin" else "*.so*")
            )
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Select Widevine CDM Library",
                str(Path.home()),
                f"Widevine CDM ({ext});;All Files (*)",
            )
            if path and Path(path).is_file():
                self.cfg["widevine_path"] = str(Path(path).resolve())
                save_config(self.cfg)
                QMessageBox.information(
                    self,
                    "Restart Required",
                    "Widevine path saved!\nPlease restart the browser for DRM changes to take effect.",
                )

    def show_extensions(self):
        self.close_bar()
        try:
            manager = self.profile.extensionManager()
        except AttributeError:
            manager = None
        if manager is None:
            QMessageBox.information(
                self,
                "Extensions",
                "Extensions need Qt WebEngine 6.10 or newer.\n\n"
                "Update with:  pip install -U PyQt6 PyQt6-WebEngine",
            )
            return
        ExtensionsDialog(self, manager).exec()

    def pick_language(self):
        current = self.cfg.get("language", DEFAULT_LANG)
        names = [n for n, _ in LANGUAGES]
        idx = next((i for i, (_, c) in enumerate(LANGUAGES) if c == current), 0)
        name, ok = QInputDialog.getItem(
            self, "Language", "Browser language (pages + menus):", names, idx, False
        )
        if not ok:
            return
        code = dict(LANGUAGES)[name]
        self.cfg["language"] = code
        save_config(self.cfg)
        self.profile.setHttpAcceptLanguage(accept_language(code) or "en-US,en")
        if self.tab() and not self.tab().blank:
            self.tab().reload()
        self.toast(f"Language: {name} - restart for menus and error pages")

    def restore_session(self):
        s = self.cfg.get("session") or {}
        for url in s.get("tabs", []):
            t = self.new_tab(focus_bar=False, blank=not url)
            if url:
                t.pending = url
        if self.stack.count():
            self.select(min(max(s.get("current", 0), 0), self.stack.count() - 1))

    def closeEvent(self, e):
        if self.quitting_clean:
            self.cfg.pop("session", None)
        else:
            tabs = [
                ("" if t.blank else t.current_url())
                for t in (self.stack.widget(i) for i in range(self.stack.count()))
                if t is not None
            ]
            self.cfg["session"] = {"tabs": tabs, "current": self.stack.currentIndex()}
        save_config(self.cfg)
        self.store.db.close()
        super().closeEvent(e)


def setup_chromium_environment():
    cfg = load_config()
    custom_widevine = cfg.get("widevine_path")
    widevine_file = find_widevine_path(custom_widevine)

    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    flag_list = flags.split() if flags else []

    recommended = [
        "--enable-gpu-rasterization",
        "--enable-zero-copy",
        "--disable-blink-features=AutomationControlled",
    ]
    for rf in recommended:
        base = rf.split("=")[0]
        if not any(f.startswith(base) for f in flag_list):
            flag_list.append(rf)

    features = [
        "NetworkService",
        "NetworkServiceInProcess",
        "SharedArrayBuffer",
        "WebGPU",
        "UnrestrictedSharedArrayBuffer",
    ]
    feat_flag = next((f for f in flag_list if f.startswith("--enable-features=")), None)
    if feat_flag:
        flag_list.remove(feat_flag)
        existing = feat_flag.split("=", 1)[1].split(",")
        for feat in features:
            if feat not in existing:
                existing.append(feat)
        flag_list.append(f"--enable-features={','.join(existing)}")
    else:
        flag_list.append(f"--enable-features={','.join(features)}")

    if widevine_file and not any(f.startswith("--widevine-path") for f in flag_list):
        posix_path = Path(widevine_file).resolve().as_posix()
        flag_list.append(f"--widevine-path={posix_path}")

    lang = cfg.get("language", DEFAULT_LANG)
    if lang and not any(f.startswith("--lang") for f in flag_list):
        flag_list.append(f"--lang={lang}")
        QLocale.setDefault(QLocale(lang.replace("-", "_")))

    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(flag_list)
    return widevine_file


def main():
    widevine_file = setup_chromium_environment()
    app = QApplication(sys.argv)
    app.setApplicationName("minibrowser")
    win = Browser(
        sys.argv[1] if len(sys.argv) > 1 else None, widevine_path=widevine_file
    )
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
