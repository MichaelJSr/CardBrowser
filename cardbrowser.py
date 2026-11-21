"""CardBrowser: the TTSCardMaker card website in a window, read-only (no sign-in or edits: guards.py START), plus Open in
Photoshop, Show in Finder/Explorer and Copy PNG on each card, from the maker's own TTSCardMaker folder. The app never
writes, moves or deletes card files, never runs git, and never sends the folder path anywhere (it lives only in
settings.json on this computer)."""
import collections
import json
import logging
import os
import re
import stat
import sys
import threading
import time
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

import actions
import guards

VERSION = "0.1.0"
NAME = "CardBrowser"
BUNDLE_ID = "io.github.michaeljsr.cardbrowser"       # fixed for good: the saved web data is keyed on it
LIVE = "https://michaeljsr.github.io/TTSCardMaker/"
RELEASES = "https://api.github.com/repos/MichaelJSr/CardBrowser/releases?per_page=10"
OS = {"darwin": "mac", "win32": "win"}.get(sys.platform, "linux")
GUI = {"mac": "cocoa", "win": "edgechromium", "linux": "gtk"}
HERE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
LOCAL_SITE = re.compile(r"http://(127\.0\.0\.1|localhost):\d{1,5}/([^?#\s\\]*/)?")

log = logging.getLogger("cardbrowser")

# ---- messages (the page shows exactly these; never a path or error text) ----
CHOOSE = "Choose your TTSCardMaker folder first."
NOT_TC = "That folder isn't TTSCardMaker (it has no Types and MDW/Templates folders)."
NOT_CARD = "Not a card file."
NOT_YET = "Not in your folder yet: pull in GitHub Desktop, then try again."
NO_ACCESS = {"mac": "macOS blocked CardBrowser from your folder: allow it in System Settings > Privacy & Security > "
                    "Files and Folders.",
             "win": "CardBrowser can't read that folder (no access).",
             "linux": "CardBrowser can't read that folder (no access)."}[OS]
NO_LINKS = "Your copy has no linked pictures yet: pull in GitHub Desktop, or Photoshop will say links are missing."
BUSY = "Still working on the last click."
TOO_MANY = "Too many clicks: wait a few seconds."


# ---- where the app keeps its own files ----
def app_home():
    if os.environ.get("CARDBROWSER_HOME"):
        return Path(os.environ["CARDBROWSER_HOME"])
    if OS == "mac":
        return Path.home() / "Library" / "Application Support" / NAME
    if OS == "win":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / NAME
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / NAME


def load_settings():
    try:
        s = json.loads((app_home() / "settings.json").read_text(encoding="utf-8"))
        return s if isinstance(s, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(s):
    home = app_home()
    home.mkdir(parents=True, exist_ok=True)
    tmp = home / "settings.json.tmp"
    tmp.write_text(json.dumps(s, indent=1), encoding="utf-8")
    os.replace(tmp, home / "settings.json")


def setup_logging():
    home = app_home()
    home.mkdir(parents=True, exist_ok=True)
    h = RotatingFileHandler(home / "cardbrowser.log", maxBytes=256 * 1024, backupCount=1, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)
    return h


def where(e):
    """An error as type + file:line with base names only (no install or user paths)."""
    tb = traceback.extract_tb(e.__traceback__)
    last = tb[-1] if tb else None
    return f"{type(e).__name__} at {os.path.basename(last.filename)}:{last.lineno}" if last else type(e).__name__


# ---- the path rule: only card PSD/PNG files inside the chosen folder ----
# Card folders, matched in any case: on Windows resolve() gives a folder's case on disk (an old clone's may differ).
TOPS = ("creatures/", "items/", "field/", "n.m.e/", "auxiliary/", "mdw/the morgue/")
BAD = re.compile(r'[\x00-\x1f\\:*?"<>|]')
RESERVED = re.compile(r"(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?", re.I)


def card_path(rel, exts):
    """rel, by its text alone, is a card PSD/PNG repo path."""
    return (isinstance(rel, str) and 0 < len(rel) <= 240 and rel.lower().startswith(TOPS) and rel.lower().endswith(exts)
            and not BAD.search(rel) and not any(s in ("", ".", "..") or s != s.strip() or s.endswith(".")
                                                or RESERVED.fullmatch(s) for s in rel.split("/")))


def card_file(root, rel, exts):
    """The card file `rel` (a repo path from the site) inside root, or None when it is not a card PSD/PNG path."""
    if not card_path(rel, exts):
        return None
    root = Path(root).resolve()
    p = root.joinpath(*rel.split("/")).resolve()      # follows links
    if not p.is_relative_to(root):                    # a link out of the folder
        return None
    return p if card_path(p.relative_to(root).as_posix(), exts) else None   # a link in must land on a card file too


# ---- the folder ----
def _isdir(p):
    """Like Path.is_dir, but a refused read (macOS privacy) raises PermissionError instead of looking absent."""
    try:
        return stat.S_ISDIR(os.stat(p).st_mode)
    except (FileNotFoundError, NotADirectoryError):
        return False


def is_tc(p):
    """A TTSCardMaker folder has Types/ and MDW/Templates/ (the link-date hooks' own test)."""
    return _isdir(Path(p) / "Types") and _isdir(Path(p) / "MDW" / "Templates")


def tc_in(p):
    """The TTSCardMaker folder at p, or its TTSCardMaker subfolder (someone picked Documents/GitHub); else None."""
    p = Path(p)
    for c in (p, p / "TTSCardMaker"):
        if is_tc(c):
            return c
    return None


def links_missing(p):
    d = Path(p) / "MDW" / "Linked"
    try:
        return not any(d.iterdir())
    except OSError:
        return True


_window = None                                     # the app window (main())
_pick = threading.Lock()


def pick_folder():
    """Asks with the native folder picker. Returns (folder or None, message)."""
    import webview
    with _pick:
        chosen = _window.create_file_dialog(webview.FileDialog.FOLDER) if _window else None
    if not chosen:
        return None, CHOOSE
    root = tc_in(chosen[0])
    if root is None:
        log.info("folder: not TTSCardMaker")
        return None, NOT_TC
    save_settings({**load_settings(), "folder": str(root)})
    log.info("folder: chosen")
    return root, NO_LINKS if links_missing(root) else ""


def folder():
    """(the TTSCardMaker folder, a note for the first message): the saved one, else the picker's."""
    saved = load_settings().get("folder")
    if isinstance(saved, str) and saved and is_tc(saved):
        return Path(saved), ""
    if saved:
        log.info("folder: saved one gone or no longer TTSCardMaker")
    return pick_folder()


# ---- the page's three calls ----
_busy = threading.Lock()
_recent = collections.deque(maxlen=6)


def reply(ok, msg, **more):
    return {"ok": bool(ok), "msg": msg, **more}


def act(rel, exts, fn):
    """One file action: one at a time, at most 6 per 10 s, inside the folder, a card file that exists."""
    if not _busy.acquire(blocking=False):
        return reply(False, BUSY)
    try:
        now = time.monotonic()
        if len(_recent) == 6 and now - _recent[0] < 10:
            return reply(False, TOO_MANY)
        _recent.append(now)
        root, note = folder()
        if root is None:
            return reply(False, note)
        p = card_file(root, rel, exts)
        if p is None:
            log.info("refused %.80r", rel)
            return reply(False, NOT_CARD)
        if not p.is_file():
            log.info("missing %s", rel)
            return reply(False, NOT_YET, missing=True)          # Show then tries the card's PSD
        ok, msg = fn(p)
        log.info("%s %s: %s", fn.__name__, "ok" if ok else "no", rel)
        return reply(ok, f"{msg} {note}" if note else msg)
    except PermissionError as e:
        log.warning("no access: %s", where(e))
        return reply(False, NO_ACCESS)
    except Exception as e:                           # noqa: BLE001 (never a traceback to the page)
        log.error("error: %s", where(e))
        return reply(False, f"That didn't work ({type(e).__name__}).")
    finally:
        _busy.release()


class Api:
    """The page's only calls (the bridge gate passes exactly one str). No attributes: state lives in module globals."""
    __slots__ = ()

    def open_psd(self, rel):
        return act(rel, (".psd",), actions.open_psd)

    def reveal(self, rel):
        return act(rel, (".psd", ".png"), actions.reveal)

    def copy_png(self, rel):
        return act(rel, (".png",), actions.copy_png)


# ---- the window ----
_first = True
_start = LIVE                                      # the window's first page (make_window)


def inject_script():
    global _first
    cfg = {"os": OS, "version": VERSION, "pre": "-" in VERSION or VERSION.startswith("0."),
           "releases": RELEASES if _first else None}
    _first = False
    return guards.NO_KEYS + (HERE / "inject.js").read_text(encoding="utf-8").replace("%CONFIG%", json.dumps(cfg))


def page_url(window):
    """The window's URL as pywebview has it (WebView2 after a full load: System.Uri text, %20 shown as a space)."""
    return str((window.get_current_url() if window else None) or "")


def page_href(window):
    """The page's own location.href (escaped on every engine); pywebview's URL if the page cannot answer."""
    try:
        href = window.evaluate_js("location.href")
    except Exception:                                # noqa: BLE001 (mid-load, a JavaScript error)
        href = None
    return href if isinstance(href, str) and guards.on_site(href) else page_url(window)


def on_loaded(window):
    """After every main-frame load (pywebview's API is in): the page side, on site pages only. Off the main thread."""
    if guards.on_site(page_url(window)):
        window.run_js(inject_script())


def note(text):
    """A short note in the page's corner (fixed phrases only)."""
    if _window:
        _window.run_js(f"window.__cardBrowserNote && window.__cardBrowserNote({json.dumps(text)})")


def reload():
    """Reloads the page; if no site page ever loaded (offline at start: a blank window, no API), loads the first page."""
    if _window and _window.events.loaded.is_set() and guards.on_site(page_url(_window)):
        _window.run_js("location.reload()")
    elif _window:
        _window.load_url(_start)


def in_browser():
    if _window:
        guards.outside(page_href(_window) if _window.events.loaded.is_set() else _start)


def thread_error(a):
    """An uncaught thread error (e.g. a reply to a page that reloaded): one log line, no traceback on stderr."""
    if a.exc_type is not SystemExit:
        log.warning("thread: %s", where(a.exc_value) if a.exc_value else a.exc_type.__name__)


def choose_folder():
    try:
        root, msg = pick_folder()
    except PermissionError:
        msg = NO_ACCESS
    note(msg if msg else "Folder saved.")


def menus():
    from webview.menu import Menu, MenuAction, MenuSeparator
    return [Menu(NAME, [
        MenuAction("Choose TTSCardMaker folder…", choose_folder),
        MenuAction("Reload", reload),
        MenuAction("Open this page in my browser", in_browser),
        MenuSeparator(),
        MenuAction("Show log", lambda: actions.reveal(app_home() / "cardbrowser.log")),
    ])]


def make_window(site, hidden=False, url=None):
    """Guards installed, settings set, the window created (not started); url: a page of the site to open first."""
    global _window, _start
    import webview
    guards.install(site)
    _start = url or site
    webview.settings["ALLOW_DOWNLOADS"] = True        # the TTS deck export: a blob a[download]
    webview.settings["ALLOW_FILE_URLS"] = False
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True   # its opener is guards.outside
    _window = webview.create_window(NAME, url or site, js_api=Api(), width=1280, height=860, min_size=(420, 520),
                                    hidden=hidden, text_select=True, draggable=True, zoomable=True)
    _window.events.loaded += on_loaded
    return _window


def start(func=None, private=False):
    import webview
    web = app_home() / "web"
    webview.start(func, gui=GUI[OS], private_mode=private, storage_path=None if OS == "mac" else str(web),
                  http_server=False, debug=False, menu=menus())


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if sys.stdout is None or sys.stderr is None:     # a windowed Windows build has neither
        sys.stdout = sys.stderr = open(os.devnull, "w")
    if "--version" in argv:
        print(VERSION)
        return 0
    if "--self-test" in argv:
        import selftest
        return selftest.main(argv)
    site = LIVE
    if "--site" in argv:
        i = argv.index("--site")
        site = argv[i + 1] if i + 1 < len(argv) else ""
        if not LOCAL_SITE.fullmatch(site):
            print("--site takes only http://127.0.0.1:<port>/.../ or http://localhost:<port>/.../", file=sys.stderr)
            return 2
    setup_logging()
    threading.excepthook = thread_error
    log.info("start %s %s on %s", NAME, VERSION, OS)
    make_window(site)
    start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
