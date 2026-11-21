"""CardBrowser --self-test [--ci] [--report FILE] [--persist write|read]: the real app code against a fixture site and
folder on 127.0.0.1, with external effects recorded (no Photoshop, file manager or browser opens). Safe mode (no --ci)
never touches the real clipboard. --persist: two runs (same CARDBROWSER_HOME) prove the saved web data (the site's
sign-in) survives a restart. Exits 0 only if every step passes."""
import hashlib
import http.server
import json
import logging
import os
import platform
import shutil
import socket
import socketserver
import sys
import tempfile
import threading
import time
import zlib
from pathlib import Path

import actions
import cardbrowser
import guards

OS = cardbrowser.OS
CARDS = {"chris-jordi": ("Creatures/Everhood/5 Stars/Chris_&_Jordi.psd", "Creatures/Everhood/5 Stars/Chris_&_Jordi.png"),
         "the-evil-fricked-up-cursed-idol": ("N.M.E/The_Evil,_Fricked_Up_Cursed_Idol.psd",
                                             "N.M.E/The_Evil,_Fricked_Up_Cursed_Idol.png"),
         "bone-s-loans": ("Items/Equip/1 Stars/Bone's_Loans.psd", "Items/Equip/1 Stars/Bone's_Loans.png"),
         "z": ("Creatures/Other/5 Stars/Z!!!!!.psd", "Creatures/Other/5 Stars/Z!!!!!.png"),
         "a-snack2": ("Items/Heal/2 Stars/A_Snack.psd", "Items/Heal/2 Stars/A_Snack2.png"),
         "cho-gath": ("MDW/The Morgue/Cho'Gath.psd", "MDW/The Morgue/Cho'Gath.png")}
GHOST = ("Creatures/Other/1 Stars/Ghost.psd", "Creatures/Other/1 Stars/Ghost.png")       # not in the folder
HALF = ("Creatures/Other/2 Stars/Half.psd", "Creatures/Other/2 Stars/Half.png")           # its PNG not pulled yet
OUT_LINK = "Creatures/Other/5 Stars/Out.png"                                               # a link out of the folder
IN_LINKS = {"Creatures/Other/1 Stars/Evil.psd": "../../../tools/run.command",               # links to non-card files
            "Creatures/Other/5 Stars/Cfg.png": "../../../.git/config"}
ATTACKS = ["../x.psd", "/etc/x.psd", "C:/x.psd", "Creatures\\..\\x.psd", "Creatures/a.psd:s.psd", ".git/x.psd",
           "MDW/Linked/x.png", "Types/x.png", "Creatures/x.txt", "Creatures/a/CON.psd", "",
           "Creatures/" + "a" * 227 + ".psd"] + ([OUT_LINK, *IN_LINKS] if os.name == "posix" else [])
PATCHES = {"mac": 4, "win": 5, "linux": 4}[OS]
LABELS = {"mac": ["Open in Photoshop", "Show in Finder", "Copy PNG"], "win": ["Open in Photoshop", "Show in Explorer",
          "Copy PNG"], "linux": ["Open PSD", "Show in folder", "Copy PNG"]}[OS]
STALE = 600                          # a self-test ends within 120 s (watchdog): older temp folders are from runs that died


def png_bytes(seed, w=3, h=2):
    """A tiny RGBA PNG made at run time (no card pictures in the repo)."""
    def chunk(t, d):
        return len(d).to_bytes(4, "big") + t + d + zlib.crc32(t + d).to_bytes(4, "big")
    rows = b"".join(b"\x00" + bytes(((x * 70 + y * 30 + seed) % 256, seed % 256, 200, 255)[i] for x in range(w)
                                    for i in range(4)) for y in range(h))
    ihdr = w.to_bytes(4, "big") + h.to_bytes(4, "big") + bytes((8, 6, 0, 0, 0))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


def make_fixture(root):
    """A pretend TTSCardMaker folder: Types/, MDW/Templates/, MDW/Linked/x.png and the odd-named cards."""
    for d in ("Types", "MDW/Templates", "MDW/Linked"):
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / "MDW/Linked/x.png").write_bytes(png_bytes(1))
    for n, (psd, png) in enumerate(CARDS.values()):
        for rel, data in ((psd, b"8BPS" + bytes(22)), (png, png_bytes(n * 17 + 5))):
            p = root.joinpath(*rel.split("/"))
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
    root.joinpath(*HALF[0].split("/")).parent.mkdir(parents=True, exist_ok=True)
    root.joinpath(*HALF[0].split("/")).write_bytes(b"8BPS" + bytes(22))
    if os.name == "posix":
        outside = root.parent / "outside.png"
        outside.write_bytes(png_bytes(9))
        root.joinpath(*OUT_LINK.split("/")).symlink_to(outside)
        for d, f in (("tools", "run.command"), (".git", "config")):
            (root / d).mkdir(exist_ok=True)
            (root / d / f).write_bytes(b"not a card")
        for link, target in IN_LINKS.items():
            p = root.joinpath(*link.split("/"))
            p.parent.mkdir(parents=True, exist_ok=True)
            p.symlink_to(target)


def snapshot(root):
    out = {}
    for p in sorted(root.rglob("*")):
        if p.name in (".DS_Store", "desktop.ini") or not p.is_file() or p.is_symlink():
            continue
        st = p.stat()
        out[p.relative_to(root).as_posix()] = (st.st_size, st.st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
    return out


class Pages(http.server.ThreadingHTTPServer):
    """A loopback server for a dict of pages; it logs every path asked for."""
    daemon_threads = True

    def __init__(self, port=0):
        self.pages, self.seen, self.down = {}, [], False
        super().__init__(("127.0.0.1", port), Handler)
        self.url = f"http://127.0.0.1:{self.server_address[1]}"

    def server_bind(self):
        """Binds without http.server's reverse DNS lookup of 127.0.0.1 (it stalled the built macOS app ~35 s)."""
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = "127.0.0.1", self.server_address[1]
        threading.Thread(target=self.serve_forever, daemon=True).start()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        self.server.seen.append(path)
        if self.server.down:                         # ST16: the site unreachable (connection dropped, no reply)
            self.close_connection = True
            return
        body = self.server.pages.get(path)
        if body is None:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        data = body.encode("utf-8") if isinstance(body, str) else body
        kind = "application/json" if path.endswith(".json") else "image/png" if path.endswith(".png") else "text/html"
        self.send_response(200)
        self.send_header("Content-Type", kind + ("; charset=utf-8" if kind != "image/png" else ""))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


DIALOG = """<script>
const esc = s => String(s).replace(/[&<>"']/g, c => "&#" + c.charCodeAt(0) + ";");
window.openCard = (id, psd, png, hook = true) => {     // the hook contract (TTSCardMaker site/assets/app.js appHook)
  const modal = document.getElementById("modal");
  modal.innerHTML = '<div class="dialog"><div class="detail"><div class="image-wrap"><div class="actions card-actions">' +
    '<button type="button">Add to deck</button></div>' + (hook && (psd || png) ? `<div class="actions card-app" data-id="${esc(id)}"` +
    ` data-file-psd="${esc(psd || "")}" data-file-png="${esc(png || "")}"></div>` : "") + `</div><div><h2>${esc(id)}</h2></div></div></div>`;
  modal.hidden = false;
  const slot = modal.querySelector(".card-app");
  if (slot) document.dispatchEvent(new CustomEvent("card-dialog", { detail: { id, psd: psd || null, png: png || null, slot } }));
};
</script>"""


def site_pages(S, O, prefix="/TTSCardMaker/"):
    snack = CARDS["a-snack2"]
    index = f"""<!doctype html><meta charset="utf-8"><title>S</title><div id="modal" hidden></div>
<a id="same" href="{O}/other.html">same</a> <a id="blank" target="_blank" rel="noopener" href="{O}/blank.html">blank</a>
<a id="bfile" target="_blank" href="file:///etc/hosts">file</a> <a id="bms" target="_blank" href="ms-settings:display">ms</a>
{DIALOG}<script>openCard("a-snack2", {json.dumps(snack[0])}, {json.dumps(snack[1])});</script>"""
    frames = f"""<!doctype html><meta charset="utf-8"><title>F</title><iframe src="{O}/frame.html"></iframe>
<iframe srcdoc="{FRAME_POST.replace('"', '&quot;')}"></iframe>"""
    nohook = f"""<!doctype html><meta charset="utf-8"><title>N</title><div id="modal" hidden></div>{DIALOG}
<script>openCard("mini-doomer", "Auxiliary/Minions/Mini_Doomer.psd", "Auxiliary/Minions/Mini_Doomer.png", false);</script>"""
    rel = lambda tags: json.dumps([{"tag_name": t, "draft": d, "prerelease": p} for t, d, p in tags])
    return {prefix: index, prefix + "index.html": index, prefix + "frames.html": frames, prefix + "nohook.html": nohook,
            prefix + "releases.json": rel([("v0.1.0", False, True), ("v99.0.0", False, True), ("v100.0.0", True, True),
                                           ("nightly", False, False)]),
            prefix + "releases-old.json": rel([("v0.0.9", False, True), (f"v{cardbrowser.VERSION}", False, True)]),
            "/Other/": "<!doctype html><title>Other</title>another Pages site"}


FRAME_POST = """<script>const m = ["copy_png", ["Items/Heal/2 Stars/A_Snack2.png"], "99"];
try { window.webkit.messageHandlers.jsBridge.postMessage(JSON.stringify({ funcName: m[0], params: m[1], id: m[2] })); } catch (e) {}
try { window.chrome.webview.postMessage([m[0], JSON.stringify(m[1]), m[2]]); } catch (e) {}</script>"""


def other_pages():
    return {"/other.html": "<!doctype html><title>O</title>other origin", "/blank.html": "<!doctype html>blank",
            "/frame.html": "<!doctype html>" + FRAME_POST, "/full.png": png_bytes(3)}


# ---- quiet runs: never in the Dock, never focused, no saved web data (unless kept), effects recorded ----
def quiet(keep_data=False):
    if OS != "mac":
        return
    import AppKit
    import WebKit
    from webview.platforms import cocoa
    real = cocoa.BrowserView.app
    real.setActivationPolicy_(AppKit.NSApplicationActivationPolicyProhibited)

    class App:
        def __getattr__(self, n):
            return getattr(real, n)

        def activateIgnoringOtherApps_(self, _flag):
            pass

    class Store:
        defaultDataStore = staticmethod(lambda: WebKit.WKWebsiteDataStore.nonPersistentDataStore())
        allWebsiteDataTypes = staticmethod(lambda: WebKit.WKWebsiteDataStore.allWebsiteDataTypes())

    class Kit:
        WKWebsiteDataStore = Store

        def __getattr__(self, n):
            return getattr(WebKit, n)
    cocoa.BrowserView.app = App()
    if not keep_data:                                # pywebview's private mode clears the default store: use a throwaway one
        cocoa.WebKit = Kit()


class Recorder:
    """Swaps the external effects for recorders; counts the Api's calls and the guards' log lines."""
    def __init__(self, ci=False):
        self.rec, self.calls, self.logs, self.pb, self.ci = [], [], [], None, ci
        actions.call = lambda argv: self.rec.append(("call", list(argv))) or 0
        actions.spawn = lambda argv: self.rec.append(("spawn", argv if isinstance(argv, str) else list(argv)))
        actions.startfile = lambda p: self.rec.append(("startfile", str(p)))
        guards._browser = lambda url: self.rec.append(("browser", url))
        real_act = cardbrowser.act

        def act(rel, exts, fn):
            self.calls.append((fn.__name__, rel))
            return real_act(rel, exts, fn)
        cardbrowser.act = act
        if OS == "mac" and not ci:
            from AppKit import NSPasteboard
            self.pb = actions.pasteboard = NSPasteboard.pasteboardWithUniqueName()
        elif not ci:
            actions.clipboard = lambda data, path: self.rec.append(("clipboard", len(data))) or True
        rec = self

        class Catch(logging.Handler):
            def emit(self, r):
                rec.logs.append(r.getMessage())
        cardbrowser.log.addHandler(Catch())

    def take(self):
        out, self.rec[:] = list(self.rec), []
        return out

    def release(self):
        if self.pb is not None:
            self.pb.releaseGlobally()
            self.pb = actions.pasteboard = None


class Harness:
    """Drives the window from the start() thread with run_js and synchronous evaluate_js only."""
    def __init__(self, window):
        self.w, self.loaded = window, threading.Event()
        window.events.loaded += lambda: self.loaded.set()
        self.replies = []

    def js(self, expr):
        return self.w.evaluate_js(expr)

    def until(self, expr, secs=8.0):
        end = time.monotonic() + secs
        while time.monotonic() < end:
            if self.js(expr):
                return True
            time.sleep(0.1)
        return False

    def ready(self, secs=20.0):
        """The page loaded and the page side ran."""
        return self.loaded.wait(secs) and self.until("window.__cardBrowser === true", secs)

    def load(self, url, injected=True):
        self.loaded.clear()
        self.w.load_url(url)
        return self.ready() if injected else self.loaded.wait(20)

    def buttons(self):
        return self.js("[...document.querySelectorAll('#modal .card-app button')].map(b => b.textContent)") or []

    def click(self, i):
        """Clicks the dialog's button i and returns what it said."""
        cardbrowser._recent.clear()
        self.js(f"document.querySelector('#modal .card-app-say').textContent = ''; "
                f"document.querySelectorAll('#modal .card-app button')[{i}].click(); 1")
        self.until("(t => !!t && t !== '\\u2026')(document.querySelector('#modal .card-app-say').textContent)")
        said = self.js("document.querySelector('#modal .card-app-say').textContent")
        self.replies.append(said)
        return said

    def api(self, call, arg):
        """pywebview.api.<call>(arg) from the page; its reply's msg (None if no reply)."""
        cardbrowser._recent.clear()
        self.js(f"window.__r = undefined; pywebview.api.{call}({json.dumps(arg)}).then(r => {{ window.__r = r.msg; }}); 1")
        got = self.until("window.__r !== undefined", 5) and self.js("window.__r")
        self.replies.append(got)
        return got or None

    def raw(self, name, params, value_id):
        """A message on this engine's bridge channel, as pywebview's own JS sends it."""
        self.js(f"window.pywebview._jsApiCallback({json.dumps(name)}, {json.dumps(params)}, {json.dumps(value_id)}); 1")

    def url(self):
        return self.w.get_current_url()


def went_out(got, url, link=True):
    """Right for a scripted navigation to url: a link click opens url in the system browser, a location change opens
    nothing. Windows: either, as WebView2 decides whether a script's click is the user's (never another URL)."""
    return got == ([("browser", url)] if link else []) or (OS == "win" and got in ([], [("browser", url)]))


def expect_open(p):
    """(what Open records, how its reply starts) on this OS."""
    p = str(p)
    if OS == "mac":
        return [("call", ["/usr/bin/open", "-b", actions.PS_BUNDLE, p])], "Opening"
    if OS == "win":
        how, exe = actions.win_photoshop()
        if how == "exe":
            return [("spawn", [exe, p])], "Opening"
        return [("startfile", p)], "Opening" if how == "assoc" else actions.NO_PS     # no Photoshop: the default app
    return [("spawn", ["xdg-open", p])], "Opening"


def expect_reveal(p):
    if OS == "mac":
        return [("call", ["/usr/bin/open", "-R", str(p)])]
    if OS == "win":
        windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot") or r"C:\Windows"
        return [("spawn", f'"{windir}\\explorer.exe" /select,"{p}"')]
    return [("call", ["gdbus", "call", "--session", "--dest", "org.freedesktop.FileManager1", "--object-path",
                      "/org/freedesktop/FileManager1", "--method", "org.freedesktop.FileManager1.ShowItems",
                      f"['{Path(p).as_uri()}']", ""])]


def read_clipboard(r):
    """The PNG bytes now on the clipboard the copy used (None: not readable here)."""
    if OS == "mac":
        from AppKit import NSPasteboard, NSPasteboardTypePNG
        data = (r.pb or NSPasteboard.generalPasteboard()).dataForType_(NSPasteboardTypePNG)
        return bytes(data) if data is not None else None
    if not r.ci:
        return None
    if OS == "win":
        import clr
        clr.AddReference("System.Windows.Forms")
        from System.IO import MemoryStream
        from System.Threading import ApartmentState, Thread, ThreadStart
        from System.Windows.Forms import Clipboard
        out = {}

        def get():
            s = Clipboard.GetData("PNG")
            out["png"] = bytes(s.ToArray()) if isinstance(s, MemoryStream) else None
            out["image"] = bool(Clipboard.ContainsImage())
        t = Thread(ThreadStart(get))
        t.SetApartmentState(ApartmentState.STA)
        t.Start()
        t.Join(5000)
        return out.get("png") if out.get("image") else None
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gdk, GLib, Gtk
    done, out = threading.Event(), {}

    def get():
        out["image"] = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).wait_is_image_available()
        done.set()
        return False
    GLib.idle_add(get)
    done.wait(5)
    return b"image" if out.get("image") else None


def pywebview_version():
    from webview import _version
    return _version.__version__


def sweep(base=None):
    """Removes temp folders of earlier self-tests that died (the watchdog's exit, a crash)."""
    for p in Path(base or tempfile.gettempdir()).glob("cardbrowser-selftest-*"):
        try:
            if p.is_dir() and not p.is_symlink() and time.time() - p.stat().st_mtime > STALE:
                shutil.rmtree(p, ignore_errors=True)
        except OSError:
            pass


def run(opts):
    started = time.monotonic()
    sweep()
    tmp = Path(tempfile.mkdtemp(prefix="cardbrowser-selftest-"))
    os.environ["CARDBROWSER_HOME"] = str(tmp / "home")
    clone = tmp / "clone"
    make_fixture(clone)
    S, O = Pages(), Pages()
    S.down = True                                    # ST16: the first load fails
    S.pages.update(site_pages(S.url, O.url))
    O.pages.update(other_pages())
    site = S.url + "/TTSCardMaker/"
    cardbrowser.setup_logging()
    threading.excepthook = cardbrowser.thread_error
    cardbrowser.save_settings({"folder": str(clone)})
    cardbrowser._first, cardbrowser.RELEASES = True, site + "releases-old.json"      # offline: never GitHub
    report = {"app": cardbrowser.VERSION, "os": OS, "python": platform.python_version(), "machine": platform.machine(),
              "pywebview": pywebview_version(), "mode": "ci" if opts["ci"] else "safe", "steps": []}
    steps = report["steps"]

    def step(sid, name, ok, detail=""):
        steps.append({"id": sid, "name": name, "pass": bool(ok), "detail": detail})

    def finish(code):
        report["ok"] = code == 0
        report["seconds"] = round(time.monotonic() - started, 1)
        text = json.dumps(report, indent=1)
        if opts["report"]:
            Path(opts["report"]).write_text(text, encoding="utf-8")
        print(text)
        return code

    def watchdog():
        step("WD", "watchdog", False, "120 s passed")
        finish(3)
        shutil.rmtree(tmp, ignore_errors=True)
        os._exit(3)
    dog = threading.Timer(120, watchdog)
    dog.daemon = True
    dog.start()
    quiet()
    rec = Recorder(opts["ci"])
    window = cardbrowser.make_window(site, hidden=True)
    h = Harness(window)
    before = snapshot(clone)
    root = clone.resolve()

    def body():
        try:
            steps_body(h, rec, S, O, site, root, step, window)
        except Exception as e:                       # noqa: BLE001
            step("X", "unexpected error", False, cardbrowser.where(e))
        finally:
            step("ST14", "no writes", snapshot(clone) == before, "fixture unchanged")
            window.destroy()
    cardbrowser.start(body, private=True)
    rec.release()
    for srv in (S, O):
        srv.shutdown()
        srv.server_close()
    logging.shutdown()
    for hd in list(cardbrowser.log.handlers):
        cardbrowser.log.removeHandler(hd)
    shutil.rmtree(tmp, ignore_errors=True)
    closed = all(_refused(s.server_address[1]) for s in (S, O))
    step("ST15", "clean-up", closed and not tmp.exists() and rec.pb is None, "servers stopped, temp folder gone")
    dog.cancel()
    steps.sort(key=lambda s: (len(s["id"]), s["id"]))
    return finish(0 if all(s["pass"] for s in steps) else 1)


def _refused(port):
    try:
        socket.create_connection(("127.0.0.1", port), 0.5).close()
        return False
    except OSError:
        return True


def offline_start(h, rec, S, site, step, window):
    """ST16: the site unreachable at start (macOS: a blank window, no API); the menu's Reload and Open this page in my
    browser still work."""
    end = time.monotonic() + 20
    while not S.seen and time.monotonic() < end:
        time.sleep(0.1)
    time.sleep(1.0)                                  # the engine gives up on the dropped load
    blank = not window.events.before_load.is_set()
    menu = {m.title: m.function for m in cardbrowser.menus()[0].items if hasattr(m, "function")}
    rec.take()
    guards._opened.clear()
    t0 = time.monotonic()
    menu["Open this page in my browser"]()
    opened = rec.take()
    S.down = False
    h.loaded.clear()
    menu["Reload"]()
    secs = time.monotonic() - t0
    ok = h.ready() and h.js("document.title") == "S"
    step("ST16", "offline start", ok and opened == [("browser", site)] and secs < 5 and (blank or OS != "mac"),
         f"{'blank window' if blank else 'error page'}; menu calls {secs:.1f} s; browser {len(opened)}; site {'up' if ok else 'NOT up'}")


def steps_body(h, rec, S, O, site, root, step, window):
    offline_start(h, rec, S, site, step, window)
    ok = h.ready()
    renderer = getattr(window.gui, "renderer", "?")
    gated = getattr(getattr(guards.PLATFORM, "js_bridge_call", None), "gated", False) and \
        getattr(guards.PLATFORM, "webbrowser", None).open is guards.outside
    version = pywebview_version()
    step("ST1", "engine + pins", ok and renderer == guards.ENGINE[OS] and version == "6.2.1" and gated
         and len(guards.PATCHED) == PATCHES, f"renderer {renderer}, pywebview {version}, patched {guards.PATCHED}")
    # ST2: the dialog opened before pywebview attached gets its buttons late
    b = h.buttons()
    say = h.js("document.querySelectorAll('#modal .card-app .card-app-say').length")
    step("ST2", "late attach", b == LABELS and say == 1, f"{b}")
    # ST3: the event path, and a second event on the same slot doubles nothing
    snack = CARDS["a-snack2"]
    h.js(f"openCard('a-snack2', {json.dumps(snack[0])}, {json.dumps(snack[1])}); 1")
    b1 = h.buttons()
    h.js("document.dispatchEvent(new CustomEvent('card-dialog', { detail: { slot: document.querySelector('#modal .card-app') } })); 1")
    b2 = h.buttons()
    step("ST3", "event path", b1 == LABELS and b2 == LABELS, f"{len(b1)} then {len(b2)} buttons")
    # ST4: each button records exactly this OS's command, the path one argument, unchanged
    rec.take()
    bad = []
    for cid, (psd, png) in CARDS.items():
        h.js(f"openCard({json.dumps(cid)}, {json.dumps(psd)}, {json.dumps(png)}); 1")
        P, G = root.joinpath(*psd.split("/")), root.joinpath(*png.split("/"))
        said = h.click(0)
        got = rec.take()
        want, says = expect_open(P)
        if got != want or not said.startswith(says):
            bad.append(f"open {cid}: {said} {len(got)}")
        said = h.click(1)
        got = rec.take()
        if got != expect_reveal(G) or not said.startswith("Showing"):
            bad.append(f"reveal {cid}: {said} {len(got)}")
    step("ST4", "actions", not bad, "; ".join(bad) or f"{len(CARDS)} cards: open + show recorded exactly")
    # ST5: copy
    h.js(f"openCard('a-snack2', {json.dumps(snack[0])}, {json.dumps(snack[1])}); 1")
    said = h.click(2)
    want = root.joinpath(*snack[1].split("/")).read_bytes()
    got = read_clipboard(rec)
    if OS != "mac" and not rec.ci:
        step("ST5", "copy", said == "PNG copied." and rec.take() == [("clipboard", len(want))], "skipped (safe mode)")
    else:
        step("ST5", "copy", said == "PNG copied." and got in (want, b"image"),
             f"{said}; read back {'equal' if got == want else 'image' if got == b'image' else 'different'}")
    rec.take()
    # ST6: a card the folder doesn't have yet
    h.js(f"openCard('ghost', {json.dumps(GHOST[0])}, {json.dumps(GHOST[1])}); 1")
    said = [h.click(0), h.click(1), h.click(2)]
    none = not rec.take()
    h.js(f"openCard('half', {json.dumps(HALF[0])}, {json.dumps(HALF[1])}); 1")
    show, copy = h.click(1), h.click(2)
    psd = rec.take() == expect_reveal(root.joinpath(*HALF[0].split("/")))
    step("ST6", "missing", said == [cardbrowser.NOT_YET] * 3 and none and show.startswith("Showing") and psd
         and copy == cardbrowser.NOT_YET, f"{said[0]} Show with no PNG: {'the PSD' if psd else 'NOT the PSD'}")
    # ST7: path attacks through each call
    n0, bad = len(h.replies), []
    for a in ATTACKS:
        for call in ("open_psd", "reveal", "copy_png"):
            got = h.api(call, a)
            if got != cardbrowser.NOT_CARD:
                bad.append(f"{call}({a[:30]!r}) -> {got}")
    step("ST7", "path attacks", not bad and not rec.take(), "; ".join(bad[:4]) or f"{len(h.replies) - n0} refused")
    # ST8: the gate (no dotted or internal names, no odd ids, one string argument)
    calls, version, xy = len(rec.calls), cardbrowser.VERSION, (window.x, window.y)
    drops0 = sum("bridge: dropped" in m for m in rec.logs)
    h.js("window.__pwned = 0; window.x = () => { window.__pwned = 1; }; 1")
    sent = [("open_psd.__globals__.pop", ["VERSION"], "1"), ("open_psd.__globals__.__setitem__", ["VERSION", "x"], "2"),
            ("__class__", [], "3"), ("pywebviewMoveWindow", [3000, 3000], "move"),
            ("pywebviewStateUpdate", {"key": "x", "value": 1}, "4"), ("pywebviewStateDelete", "x", "5"),
            ("pywebviewAsyncCallback", "1", "6"), ("open_psd", [snack[0]], '"]);x();//'), ("open_psd", [], "7"),
            ("open_psd", [snack[0], snack[0]], "8"), ("open_psd", [42], "9"), ("reveal", ["x" * 2000], "10"),
            (["open_psd"], [snack[0]], "11")]
    for name, params, vid in sent:
        h.raw(name, params, vid)
    if OS != "win":                                   # not JSON at all: refused without a crash
        h.js("window.webkit.messageHandlers.jsBridge.postMessage('not json'); 1")
    time.sleep(1.5)
    drops = sum("bridge: dropped" in m for m in rec.logs) - drops0
    intact = cardbrowser.VERSION == version and "VERSION" in vars(cardbrowser)
    bad_json = sum("bridge: bad message" in m for m in rec.logs)
    step("ST8", "gate", intact and (window.x, window.y) == xy and h.js("window.__pwned") == 0 and h.js("1 + 1") == 2
         and len(rec.calls) == calls and drops == len(sent) and (OS == "win" or bad_json == 1) and not rec.take(),
         f"{drops} of {len(sent)} dropped, {bad_json} non-JSON message refused")
    # ST9: navigation stays on the site; only http(s) link clicks reach the system browser
    home, bad = h.url(), []
    guards._opened.clear()
    h.js("document.getElementById('same').click(); 1")
    time.sleep(1.0)
    got = rec.take()
    gesture = bool(got)                                # Windows: did WebView2 take the script's click as the user's?
    if h.url() != home or not went_out(got, O.url + "/other.html"):
        bad.append(f"same-window link {len(got)}")
    for target in (O.url + "/other.html", S.url + "/Other/", "file:///etc/hosts", "data:text/html,hi"):
        h.js(f"location.href = {json.dumps(target)}; 1")
        time.sleep(0.8)
        got = rec.take()
        if h.url() != home or not went_out(got, target, link=False) or not h.js("window.__cardBrowser === true"):
            bad.append(f"{target.split(':')[0]} {target[-12:]}")
    h.js("document.getElementById('blank').click(); 1")
    time.sleep(0.8)
    got = rec.take()
    if not went_out(got, O.url + "/blank.html"):
        bad.append(f"_blank {len(got)}")
    h.js("document.getElementById('bfile').click(); document.getElementById('bms').click(); 1")
    time.sleep(0.8)
    if rec.take():
        bad.append("_blank file:/ms-settings: reached the browser")
    h.js("window.__w = window.open('', '_blank'); 1")                  # the deck's Print proxies
    time.sleep(0.5)
    if not h.js("window.__w === null && /Copy share link/.test((document.querySelector('.card-app-note') || {}).textContent)"):
        bad.append("print: no note")
    if rec.take():
        bad.append("print: reached the browser")
    step("ST9", "navigation", not bad and h.url() == home, ("; ".join(bad) or "stayed on the site")
         + (f"; script clicks open links: {'yes' if gesture else 'no'}" if OS == "win" else ""))
    # ST10: frames never reach the bridge (another origin's frame never loads on macOS/Linux; Linux: no srcdoc frame)
    count = lambda text: sum(text in m for m in rec.logs)
    calls, refused0, srcdoc0 = len(rec.calls), count("sender refused"), count("navigation: refused about")
    ok = h.load(site + "frames.html")
    time.sleep(1.5)
    o_frame = "/frame.html" in O.seen
    refused, srcdoc = count("sender refused") - refused0, count("navigation: refused about") - srcdoc0
    step("ST10", "frames", ok and len(rec.calls) == calls and (OS == "win" or not o_frame) and (OS != "mac" or refused >= 1)
         and (OS != "linux" or srcdoc >= 1), f"api calls +{len(rec.calls) - calls}, other origin's frame "
         f"{'loaded' if o_frame else 'cancelled'}, {refused} sender refused, {srcdoc} srcdoc frame refused")
    # ST12: a site version without the hook
    ok = h.load(site + "nohook.html")
    n1 = h.js("document.querySelectorAll('.card-app-missing').length")
    h.js("openCard('mini-doomer', 'Auxiliary/Minions/Mini_Doomer.psd', 'Auxiliary/Minions/Mini_Doomer.png', false); 1")
    time.sleep(0.3)
    n2 = h.js("document.querySelectorAll('.card-app-missing').length")
    step("ST12", "missing hook", ok and n1 == 1 and n2 == 1 and not h.buttons(), f"note {n1}, after a re-render {n2}")
    # ST13: the update note (and none when nothing is newer); the first load asked the loopback list, never GitHub
    first = "/TTSCardMaker/releases-old.json" in S.seen
    cardbrowser._first, cardbrowser.RELEASES = True, site + "releases.json"
    ok = h.load(site) and h.until("!!document.querySelector('.card-app-update a')")
    text = h.js("(document.querySelector('.card-app-update') || {}).textContent || ''")
    href = h.js("(document.querySelector('.card-app-update a') || {}).href || ''")
    guards._opened.clear()
    rec.take()
    h.js("document.querySelector('.card-app-update a') && document.querySelector('.card-app-update a').click(); 1")
    time.sleep(0.8)
    opened = rec.take()
    cardbrowser._first, cardbrowser.RELEASES = True, site + "releases-old.json"
    h.load(site)
    time.sleep(1.5)
    none = h.js("document.querySelectorAll('.card-app-update').length") == 0
    tag_url = "https://github.com/MichaelJSr/CardBrowser/releases/tag/"
    step("ST13", "update note", ok and "v99.0.0" in text and "v100" not in text and href == tag_url + "v99.0.0"
         and went_out(opened, href) and none and first,
         f"{text.strip()[:60]}; old list: {'no note' if none else 'NOTE'}; first load's list {'local' if first else 'NOT local'}")
    # ST17: a reply that lands after a full reload: one log line (no stderr traceback), the next click works
    real, late0 = actions.reveal, sum("thread: JavascriptException" in m for m in rec.logs)

    def reveal(p):
        h.loaded.wait(10)                            # answers once the page has reloaded
        return real(p)
    actions.reveal = reveal
    cardbrowser._recent.clear()
    rec.take()
    h.loaded.clear()
    h.js("document.querySelectorAll('#modal .card-app button')[1].click(); setTimeout(() => location.reload(), 200); 1")
    ok = h.ready() and h.until("document.querySelectorAll('#modal .card-app button').length === 3")
    time.sleep(1.0)
    actions.reveal = real
    late = sum("thread: JavascriptException" in m for m in rec.logs) - late0
    first = rec.take()
    said = h.click(1)
    step("ST17", "reload mid-reply", ok and late == 1 and len(first) == 1 and said.startswith("Showing") and len(rec.take()) == 1
         and threading.excepthook is cardbrowser.thread_error, f"late reply logged {late}x; next Show: {said}")
    # ST18: the menu's Open this page in my browser takes the page's escaped address after a full load
    page = site + "index.html?q=a%20b#/cards?q=mini%20doomer"
    ok = h.load(page)
    raw = h.url()
    rec.take()
    guards._opened.clear()
    menu = {m.title: m.function for m in cardbrowser.menus()[0].items if hasattr(m, "function")}
    menu["Open this page in my browser"]()
    opened = rec.take()
    step("ST18", "page link", ok and opened == [("browser", page)], f"browser got {len(opened)}, "
         f"{'the escaped address' if opened == [('browser', page)] else 'NOT the address'}; pywebview's URL "
         f"{'escaped' if raw == page else 'unescaped' if raw == page.replace('%20', ' ') else 'other'}")
    # ST11: nothing the page or log saw holds a path or a traceback
    log_text = (cardbrowser.app_home() / "cardbrowser.log").read_text(encoding="utf-8")
    seen = "\n".join(map(str, h.replies)) + log_text + "\n".join(rec.logs)      # raw text: JSON doubles backslashes
    leaks = [w for w in (str(root), str(root.parent), str(Path.home()), "Traceback") if w and w in seen]
    step("ST11", "no leaks", not leaks and h.replies, f"{len(h.replies)} replies + log checked")


# ---- --persist write|read: the site's sign-in (localStorage + IndexedDB) survives a restart ----
PERSIST_PORT = 47613                                 # fixed: both runs need the same origin
KEPT = "kept-by-cardbrowser"
WRITE = """window.__p = undefined;
localStorage.setItem("cardbrowser-persist", %(v)s);
const q = indexedDB.open("cardbrowser-persist", 1);
q.onupgradeneeded = () => q.result.createObjectStore("s");
q.onerror = () => { window.__p = "idb open failed"; };
q.onsuccess = () => { const t = q.result.transaction("s", "readwrite"); t.objectStore("s").put(%(v)s, "k");
  t.oncomplete = () => { q.result.close(); window.__p = "ok"; }; t.onerror = () => { window.__p = "idb put failed"; }; };
1"""
READ = """window.__p = undefined;
const ls = localStorage.getItem("cardbrowser-persist");
const q = indexedDB.open("cardbrowser-persist", 1);
q.onupgradeneeded = () => q.result.createObjectStore("s");
q.onerror = () => { window.__p = JSON.stringify({ ls, idb: "open failed" }); };
q.onsuccess = () => { const g = q.result.transaction("s").objectStore("s").get("k");
  g.onsuccess = () => { q.result.close(); localStorage.removeItem("cardbrowser-persist");
    const d = indexedDB.deleteDatabase("cardbrowser-persist");            // leave nothing behind
    d.onsuccess = d.onerror = d.onblocked = () => { window.__p = JSON.stringify({ ls, idb: g.result === undefined ? null : g.result }); }; };
  g.onerror = () => { window.__p = JSON.stringify({ ls, idb: "get failed" }); }; };
1"""


def persist(opts):
    mode = opts["persist"]
    if mode not in ("write", "read") or not os.environ.get("CARDBROWSER_HOME"):
        print("--persist takes write or read, with CARDBROWSER_HOME set (the same for both runs)", file=sys.stderr)
        return 2
    started = time.monotonic()
    report = {"app": cardbrowser.VERSION, "os": OS, "python": platform.python_version(), "machine": platform.machine(),
              "pywebview": pywebview_version(), "mode": "persist " + mode, "steps": []}

    def finish(ok, detail):
        report["steps"].append({"id": "P", "name": "persist " + mode, "pass": bool(ok), "detail": detail})
        report["ok"] = bool(ok)
        report["seconds"] = round(time.monotonic() - started, 1)
        text = json.dumps(report, indent=1)
        if opts["report"]:
            Path(opts["report"]).write_text(text, encoding="utf-8")
        print(text)
        return 0 if ok else 1
    try:
        S = Pages(PERSIST_PORT)
    except OSError as e:
        return finish(False, f"port {PERSIST_PORT} busy ({type(e).__name__})")
    S.pages["/TTSCardMaker/"] = "<!doctype html><meta charset=utf-8><title>P</title>persist"
    site = f"{S.url}/TTSCardMaker/"
    dog = threading.Timer(90, lambda: (finish(False, "90 s passed"), os._exit(3)))
    dog.daemon = True
    dog.start()
    cardbrowser.setup_logging()
    quiet(keep_data=True)
    cardbrowser._first = False                       # no update check
    window = cardbrowser.make_window(site, hidden=True)
    h, out = Harness(window), {}

    def body():
        try:
            if not h.ready():
                out["detail"] = "page not loaded"
                return
            t0 = time.monotonic()
            h.js((WRITE if mode == "write" else READ) % {"v": json.dumps(KEPT)})
            if not h.until("window.__p !== undefined", 10):
                out["detail"] = "no answer from the page"
                return
            got = h.js("window.__p")
            report["timing"] = f"page at {t0 - started:.1f} s, answer in {time.monotonic() - t0:.1f} s"
            if mode == "write":
                out["ok"], out["detail"] = got == "ok", f"wrote localStorage + IndexedDB: {got}"
            else:
                got = json.loads(got)
                out["ok"] = got == {"ls": KEPT, "idb": KEPT}
                out["detail"] = "read back: localStorage {}, IndexedDB {}".format(
                    *("kept" if got.get(k) == KEPT else f"LOST ({str(got.get(k))[:20]})" for k in ("ls", "idb")))
            time.sleep(2.0)                          # the engine writes (or removes) on disk after the call
        except Exception as e:                       # noqa: BLE001
            out["detail"] = cardbrowser.where(e)
        finally:
            window.destroy()
    cardbrowser.start(body, private=False)
    S.shutdown()
    S.server_close()
    logging.shutdown()
    dog.cancel()
    return finish(out.get("ok"), out.get("detail", "?"))


def main(argv):
    opts = {"ci": "--ci" in argv, "report": None, "persist": None}
    for flag in ("--report", "--persist"):
        if flag in argv:
            i = argv.index(flag)
            opts[flag[2:]] = argv[i + 1] if i + 1 < len(argv) else ""
    return persist(opts) if opts["persist"] is not None else run(opts)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
