# Mine Browser

A small, keyboard-driven web browser written in Python with PyQt6 and Qt WebEngine (Chromium). No tab bar, no toolbar: just the page, with an overlay search bar and shortcuts for everything.

**Version 0.1.4** · Tested on Arch Linux · WhatsApp Web and Crunchyroll work

> Mine Browser is a hobby project. It is built on Qt WebEngine, so how current and secure its Chromium engine is depends on the PyQt6-WebEngine version you have installed. See [Security notes](#security-notes).

---

## Features

**Browsing**
* Tabs without a tab bar. A small `1/3` counter shows where you are; jump with `Ctrl+1` to `Ctrl+9`, `Ctrl+Tab`, or reopen a closed tab with `Ctrl+Shift+T`.
* One overlay bar for addresses, searches, history and bookmarks. Type a URL or a search; suggestions come from your history and bookmarks (bookmarks are starred).
* Find in page, zoom, fullscreen, back/forward, reload.
* Session restore: your tabs come back after the browser is closed (closing the last tab with `Ctrl+W` starts fresh).
* Downloads with an optional "ask where to save" prompt.
* PDF viewer, WebGL, GPU rasterization and WebGPU enabled.

**Customization**
* **Settings** (`Ctrl+,` or type `settings` in the bar): download folder, search engine (DuckDuckGo, Google, Bing, Startpage or a custom URL), fonts and sizes, language, DRM setup and clearing data.
* **Fonts:** choose standard, monospace, serif and sans-serif fonts and sizes, and optionally force your font on every site (icon fonts and code are left alone).
* **Every shortcut can be changed.** Open the shortcut table with `F1` or `Ctrl+/`. Conflicts are detected for you.
* **Wallpaper** for blank tabs (PNG, JPG, WebP, GIF, BMP), including animated GIFs.
* **Languages:** 13 options, including English, Urdu, Arabic, Hindi, French, German, Spanish, Portuguese (Brazil), Russian, Turkish, Chinese (Simplified) and Japanese.

**Sites and media**
* **WhatsApp Web** works. Mine Browser identifies itself as Chrome.
* **Crunchyroll and other DRM video** work when a Widevine library is found. Mine Browser does not ship Widevine: it looks for the copy installed with Google Chrome, Edge, Brave or Chromium, or you can choose the file yourself (`Ctrl+Shift+V`).
* **Google sign-in** is handled by sending a Firefox user agent to `accounts.google.com`, which avoids "this browser is not secure" blocks.
* **Extensions** (`Ctrl+Shift+E`): add an unpacked folder or a `.zip`. Manifest V3 only, and it needs Qt WebEngine 6.10 or newer.

**Privacy and control**
* Per-site permission prompts for location, microphone, camera, notifications, screen sharing, clipboard, local fonts and window management. The default button is **Deny**, and you can remember your choice for each site.
* One command (`Ctrl+Shift+Del`) clears history, cookies, cache and saved permissions. Bookmarks are kept.
* `javascript:` and `vbscript:` addresses are refused in the bar.
* On Linux and macOS the data folder is private to your user (mode `700`).

---

## Requirements

* **Python 3.9+**
* **PyQt6** and **PyQt6-WebEngine**
* For extensions: Qt WebEngine **6.10 or newer**
* For DRM video: Widevine from an installed Chrome, Edge, Brave or Chromium

## Install and run

### 1. Get the code

Install [Git](https://git-scm.com/downloads) (on Arch: `sudo pacman -S git`), then clone the repository and enter it:

```bash
git clone https://github.com/aliplayz24-arch/mine-browser.git
cd mine-browser
```

To get updates later, run this inside the folder:

```bash
git pull
```

No Git? On the repository page click **Code → Download ZIP**, then unzip it.

### 2. Install the dependencies

**Arch Linux** (recommended, because Arch blocks system-wide `pip install`):

```bash
sudo pacman -S python-pyqt6 python-pyqt6-webengine
```

**Anywhere else**, use a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate        # on Windows: .venv\Scripts\activate
pip install PyQt6 PyQt6-WebEngine
```

### 3. Run it

```bash
python mine_browser.py
```

Or open a page directly:

```bash
python mine_browser.py https://example.com
```

## Optional: build an executable

You can turn `mine_browser.py` into a program you can launch without typing `python`. There are three ways, and they suit different situations:

| | pyle / compyle | PyInstaller |
|---|---|---|
| What it produces | A tiny launcher (a few KB) that runs your script on the system's Python | A bundle that includes Python, Qt and the Chromium engine |
| Size | Tiny | Large (Qt WebEngine alone is over 100 MB) |
| Python and PyQt6 needed on the target machine | **Yes** | **No** |
| Best for | You and other Linux users who already have the dependencies | Giving the browser to people who don't have Python, such as most Windows users |
| Build it on | The OS you are targeting | The OS you are targeting (it cannot cross-compile) |

### With pyle or compyle

Mine Browser works with [pyle](https://github.com/aliplayz24-arch/pyle) (Haskell) and compyle (Bun):

```bash
# with pyle
pyle mine_browser.py -o mine-browser

# with compyle
bun compyle.js mine_browser.py -o mine-browser
```

The launcher is only a few KB, but **Python and PyQt6 must still be installed** on the machine that runs it. If you built it inside a virtual environment, activate that environment first so the launcher points at the right Python.

### With PyInstaller

```bash
pip install pyinstaller

# a folder with the program inside (starts faster)
pyinstaller --noconfirm --windowed --name mine-browser mine_browser.py

# or a single file (slower to start, because it unpacks itself each time)
pyinstaller --noconfirm --onefile --windowed --name mine-browser mine_browser.py
```

The result is in the `dist/` folder. `--windowed` hides the console window on Windows.

* Build on each OS you want to release for: a Windows `.exe` must be built on Windows, and a Linux binary on Linux.
* For Linux releases, build on an older distribution (or in a container). The binary uses the system's glibc, so one built on a very new distro may not start on an older one.
* Widevine is still not bundled. Crunchyroll and other DRM video need a Widevine library from an installed Chrome, Edge, Brave or Chromium on the user's machine.

---

## Keyboard shortcuts

All of these can be changed in the shortcut table (`F1`).

| Action | Shortcut |
|--------|----------|
| Search / address bar | `Ctrl+L`, `Ctrl+K` |
| Settings | `Ctrl+,` |
| History | `Ctrl+H` |
| Bookmarks list | `Ctrl+B` |
| Bookmark this page / delete bookmark | `Ctrl+D` / `Ctrl+Shift+D` |
| Find in page | `Ctrl+F` |
| New tab / close tab / reopen tab | `Ctrl+T` / `Ctrl+W` / `Ctrl+Shift+T` |
| Next / previous tab | `Ctrl+Tab` / `Ctrl+Shift+Tab` |
| Jump to tab | `Ctrl+1` to `Ctrl+9` (fixed) |
| Zoom in / out / reset | `Ctrl+=` / `Ctrl+-` / `Ctrl+0` |
| Back / forward / reload | `Alt+Left` / `Alt+Right` / `F5` |
| Choose / remove wallpaper | `Ctrl+Shift+W` / `Ctrl+Alt+W` |
| Clear browsing data | `Ctrl+Shift+Del` |
| Change language | `Ctrl+Shift+L` |
| DRM / Widevine setup | `Ctrl+Shift+V` |
| Extensions | `Ctrl+Shift+E` |
| Fullscreen | `F11` |
| Shortcut list | `F1`, `Ctrl+/` |
| Close the bar or a dialog | `Esc` (fixed) |

On macOS, `Ctrl` is `Cmd`.

---

## Where your data lives

Everything is stored in `~/.minibrowser/`:

| File or folder | Contents |
|----------------|----------|
| `config.json` | Settings, shortcuts, site permissions, session |
| `history.db` | History and bookmarks (SQLite) |
| `web/`, `cache/` | Cookies, local storage and cache |

Set the `MINIBROWSER_HOME` environment variable to use a different folder.

## Platform support

| Platform | Status |
|----------|--------|
| Linux | Tested (Arch Linux) |
| Windows, macOS | The code has paths for them (Widevine search, user agent), but they have not been tested |

## Limitations

* There is no ad or tracker blocking, no password manager and no sync.
* Extensions must be Manifest V3, and the Chrome Web Store cannot be used directly.
* DRM video needs a Widevine library already installed on your system.
* Menus and error pages change language only after a restart.
* Mine Browser identifies itself as Chrome, using the version of its own Chromium engine. If your PyQt6-WebEngine is old, some sites may ask you to update the browser.

## Security notes

Mine Browser uses the Chromium engine inside PyQt6-WebEngine. Keep it updated (`pip install -U PyQt6 PyQt6-WebEngine`, or your distro's packages) so you get Chromium's security fixes. It is a personal project, so for banking or anything sensitive, a mainstream, actively maintained browser is the safer choice.

## License

See `LICENSE`.
