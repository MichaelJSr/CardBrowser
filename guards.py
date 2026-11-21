"""Bridge and window guards: the bridge answers only the card site, only three call names reach pywebview, only site
pages load in the window, and the system browser gets only http(s) links. install() patches pywebview 6.2.1 (pinned)."""
import collections
import logging
import re
import sys
import time
import types
import webbrowser
from urllib.parse import unquote, urlsplit

log = logging.getLogger("cardbrowser")
OS = {"darwin": "mac", "win32": "win"}.get(sys.platform, "linux")
LIVE = "https://michaeljsr.github.io/TTSCardMaker/"
SITE = urlsplit(LIVE)                       # install() may swap in a loopback copy (--site)
ALLOWED = frozenset({"open_psd", "reveal", "copy_png"})
ID_OK = re.compile(r"[0-9A-Za-z.+-]{1,32}").fullmatch
ARG_MAX = 1024                              # the path rule refuses over 240 with a plain reply
ENGINE = {"mac": "wkwebview", "win": "edgechromium", "linux": "gtkwebkit2"}
PATCHED = []                                # what install() patched (self-test ST1)
PLATFORM = None                             # the patched pywebview backend module
_browser = webbrowser.open                  # the self-test swaps in a recorder
# The app is read-only (owner 11-21). APP_FLAG tells the site so before its own scripts (the hook contract: the site then
# shows no Sign in, Edit or editor). NO_KEYS: no page may keep a WebCrypto key in IndexedDB (the site's sign-in and
# remembered deck passphrases do): WebKit seals one with a key in the macOS keychain, which asks for the Mac password
# after each unsigned update. START (both) runs at the start of every document, in every frame, on every engine; where it
# could not be added, no site page loads (never a page with Sign in).
APP_FLAG = """if (!("cardApp" in window)) Object.defineProperty(window, "cardApp", { value: Object.freeze({ readOnly: true }), enumerable: true });
"""
NO_KEYS = """(() => {
  if (window.__cardBrowserNoKeys || typeof IDBObjectStore === "undefined") return;
  window.__cardBrowserNoKeys = true;
  const isKey = v => { try { return v instanceof CryptoKey || (!!v && typeof v === "object" && Object.values(v).some(x => x instanceof CryptoKey)); } catch { return false; } };
  for (const [proto, name] of [[IDBObjectStore.prototype, "add"], [IDBObjectStore.prototype, "put"], [IDBCursor.prototype, "update"]]) {
    const real = proto[name];
    proto[name] = function (value, ...rest) {
      if (typeof CryptoKey !== "undefined" && isKey(value)) throw new DOMException("CardBrowser keeps no sign-in keys", "DataCloneError");
      return real.call(this, value, ...rest);
    };
  }
})();
"""
START = APP_FLAG + NO_KEYS


def _parts(u):
    return u.scheme, u.hostname, u.port or {"https": 443, "http": 80}.get(u.scheme)


def on_site(url):
    """A page of the card site: same scheme/host/port, path under the site's, no dot segments or backslashes."""
    try:
        u = urlsplit(str(url or ""))
        path = unquote(u.path)
        return ((*_parts(u), u.username, u.password) == (*_parts(SITE), None, None)
                and (path + "/").startswith(SITE.path) and "\\" not in path and not {".", ".."} & set(path.split("/")))
    except ValueError:                      # a bad port or bracket
        return False


def frame_ok(url):
    """What may load in any frame of the window: site pages, about:blank/srcdoc, the site's own blob: URLs."""
    url = str(url or "")
    if url in ("about:blank", "about:srcdoc"):
        return True
    if url.startswith("blob:"):
        try:
            return _parts(urlsplit(url[5:])) == _parts(SITE)
        except ValueError:
            return False
    return on_site(url)


_opened = collections.deque(maxlen=3)


def outside(url, *_, **__):
    """Opens an http(s) link in the system browser (at most 3 per 10 s); refuses every other scheme."""
    url = str(url)
    if len(url) > 2048 or not re.match(r"https?://[^\s/@\\]+(/|$)", url) or re.search(r"\s", url):
        log.warning("outside: refused %s", url.split(":", 1)[0][:20])
        return False
    if len(_opened) == 3 and time.monotonic() - _opened[0] < 10:
        log.warning("outside: too many")
        return False
    _opened.append(time.monotonic())
    log.info("outside: %s", url.split(":", 1)[0])
    _browser(url)
    return True


def gate(base):
    """pywebview's js_bridge_call, passing only the three names with a plain id and exactly one string argument."""
    def js_bridge_call(window, name, params, value_id):
        if (isinstance(name, str) and name in ALLOWED and isinstance(value_id, str) and ID_OK(value_id) and isinstance(params, list)
                and len(params) == 1 and isinstance(params[0], str) and len(params[0]) <= ARG_MAX):
            return base(window, name, params, value_id)
        log.warning("bridge: dropped %.40r", name)
    js_bridge_call.gated = True
    return js_bridge_call


def install(site=LIVE):
    """Checks the engine and patches pywebview for this OS. A missing name raises: the app does not start unguarded."""
    global SITE, PLATFORM
    SITE = urlsplit(site)
    if PATCHED:
        return PATCHED
    if OS == "mac":
        P = _install_mac()
    elif OS == "win":
        P = _install_win()
    else:
        P = _install_gtk()
    P.js_bridge_call = gate(P.js_bridge_call)          # each backend calls its own imported name
    P.webbrowser = types.SimpleNamespace(open=outside)  # pywebview's target=_blank openers
    PATCHED.extend(["js_bridge_call", "webbrowser"])
    PLATFORM = P
    return PATCHED


def _install_mac():
    import objc
    from webview.platforms import cocoa as P

    class CBBridge(P.BrowserView.JSBridge):            # ObjC class names are global: unique, defined once
        def userContentController_didReceiveScriptMessage_(self, ctl, msg):   # main thread; never raises into AppKit
            try:
                if msg.frameInfo().isMainFrame() and on_site(msg.webView().URL().absoluteString()):
                    return objc.super(CBBridge, self).userContentController_didReceiveScriptMessage_(ctl, msg)
                log.warning("bridge: sender refused")
            except Exception as e:                      # noqa: BLE001 (a malformed message)
                log.warning("bridge: bad message (%s)", type(e).__name__)

    class CBDelegate(P.BrowserView.BrowserDelegate):
        def webView_decidePolicyForNavigationAction_decisionHandler_(self, wv, action, handler):
            try:
                _start_mac(wv)
                started = True
            except Exception as e:                      # noqa: BLE001
                started = False
                log.error("start script: %s; no site page loads", type(e).__name__)
            try:
                url, frame = str(action.request().URL().absoluteString()), action.targetFrame()
                ok = (started and frame_ok(url)) or (frame is None and not action.shouldPerformDownload())   # None: a new window
                link = frame is not None and frame.isMainFrame() and action.navigationType() == 0   # a link click
            except Exception as e:                      # noqa: BLE001
                log.warning("navigation: %s", type(e).__name__)
                ok = link = False
            if ok:
                return objc.super(CBDelegate, self).webView_decidePolicyForNavigationAction_decisionHandler_(
                    wv, action, handler)
            if link:
                outside(url)
            handler(0)                                  # cancel, any frame

    P.BrowserView.JSBridge, P.BrowserView.BrowserDelegate = CBBridge, CBDelegate
    PATCHED.extend(["JSBridge", "BrowserDelegate"])
    return P


def _start_mac(wv):
    """START as a WKUserScript (document start, every frame), added before the first navigation goes on."""
    import WebKit
    ucc = wv.configuration().userContentController()
    if not any(s.source() == START for s in ucc.userScripts()):
        ucc.addUserScript_(WebKit.WKUserScript.alloc().initWithSource_injectionTime_forMainFrameOnly_(
            START, WebKit.WKUserScriptInjectionTimeAtDocumentStart, False))


MSHTML = "webview.platforms.mshtml"


def _install_win():
    sys.modules[MSHTML] = None                          # never IE: importing it writes IE mode to the registry
    try:
        from webview.platforms import winforms
    except ImportError as e:                            # no WebView2: winforms reached for IE
        if e.name != MSHTML:
            raise
        need_webview2()
    if winforms.renderer != "edgechromium":
        need_webview2()
    from webview.platforms import edgechromium as P
    E = P.EdgeChrome
    nav, notify, new, ready = E.on_navigation_start, E.on_script_notify, E.on_new_window_request, E.on_webview_ready

    def on_webview_ready(self, sender, args):          # START first; pywebview's (it loads the page) once it is in
        def go(task):
            try:
                if task.IsFaulted or task.IsCanceled:
                    log.error("start script: not added; no site page loads")
                else:
                    self._cb_start = True
            finally:
                ready(self, sender, args)
        try:
            if args.IsSuccess:
                task = sender.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(START)
                task.ContinueWith(P.Action[P.Task[P.String]](go), self.syncContextTaskScheduler)
                return
        except Exception as e:                          # noqa: BLE001
            log.error("start script: %s; no site page loads", type(e).__name__)
        ready(self, sender, args)

    def on_navigation_start(self, sender, args):       # main frame only; never raises into .NET
        try:
            url = str(args.Uri)
            ok = getattr(self, "_cb_start", False) and frame_ok(url)   # without START no page loads
            if not ok:
                args.Cancel = True
                if args.IsUserInitiated:
                    outside(url)
        except Exception as e:                          # noqa: BLE001
            log.warning("navigation: %s", type(e).__name__)
            ok = False
            try:
                args.Cancel = True
            except Exception:                           # noqa: BLE001
                pass
        if ok:
            return nav(self, sender, args)

    def on_script_notify(self, sender, args):
        try:
            if on_site(str(args.Source)):
                return notify(self, sender, args)
            log.warning("bridge: sender refused")
        except Exception as e:                          # noqa: BLE001
            log.warning("bridge: bad message (%s)", type(e).__name__)

    def on_new_window_request(self, sender, args):     # target=_blank, window.open: only a click leaves (as on macOS)
        try:
            if args.IsUserInitiated:
                return new(self, sender, args)
            log.warning("new window: not a click")
        except Exception as e:                          # noqa: BLE001
            log.warning("new window: %s", type(e).__name__)
        try:
            args.set_Handled(True)                      # no window; window.open() gets null
        except Exception:                               # noqa: BLE001
            pass

    E.on_navigation_start, E.on_script_notify, E.on_new_window_request, E.on_webview_ready = (
        on_navigation_start, on_script_notify, on_new_window_request, on_webview_ready)
    PATCHED.extend(["on_navigation_start", "on_script_notify", "on_new_window_request", "on_webview_ready"])
    return P


def need_webview2():
    """No WebView2 runtime: say where to get it, open that page, exit."""
    import ctypes
    page = "https://developer.microsoft.com/microsoft-edge/webview2/"
    ctypes.windll.user32.MessageBoxW(None, "CardBrowser needs Microsoft Edge WebView2. Install it from the page that "
                                     "opens now, then start CardBrowser again.", "CardBrowser", 0x10)
    outside(page)
    sys.exit(1)


def _install_gtk():
    try:
        from webview.platforms import gtk as P
    except (ImportError, ValueError) as e:              # no PyGObject / WebKit2GTK 4.1
        sys.exit(f"CardBrowser needs GTK 3 and WebKit2GTK ({type(e).__name__}). Debian/Ubuntu: sudo apt install "
                 "python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1; Fedora: sudo dnf install "
                 "python3-gobject webkit2gtk4.1")
    nav, bridge = P.BrowserView.on_navigation, P.BrowserView.on_js_bridge_call

    def on_navigation(self, wv, decision, kind):        # main frames and subframes; never raises into GTK
        try:
            if not getattr(self, "_cb_start", False):   # START before the first document
                self.manager.add_script(P.webkit.UserScript.new(START, P.webkit.UserContentInjectedFrames.ALL_FRAMES,
                                                                P.webkit.UserScriptInjectionTime.START, None, None))
                self._cb_start = True
        except Exception as e:                          # noqa: BLE001
            log.error("start script: %s; no site page loads", type(e).__name__)
        try:
            if type(decision) is P.webkit.NavigationPolicyDecision:
                action = decision.get_navigation_action()
                url = action.get_request().get_uri()
                if not (getattr(self, "_cb_start", False) and frame_ok(url)) or url == "about:srcdoc":   # srcdoc: no sender frame
                    log.info("navigation: refused %s", str(url).split(":", 1)[0][:20])
                    if action.get_navigation_type() == P.webkit.NavigationType.LINK_CLICKED:
                        outside(url)
                    decision.ignore()
                    return True
        except Exception as e:                          # noqa: BLE001
            log.warning("navigation: %s", type(e).__name__)
            try:
                decision.ignore()
            except Exception:                           # noqa: BLE001
                pass
            return True
        return nav(self, wv, decision, kind)

    # WebKitGTK names no sender frame, so this checks the main frame's URI: a frame on_navigation lets in (site pages,
    # about:blank, the site's blob:) or that never asks it (javascript:) posts as the page, sandboxed or not. The site
    # has no frames; README: never untrusted HTML in one.
    def on_js_bridge_call(self, manager, message):
        try:
            if on_site(self.webview.get_uri()):
                return bridge(self, manager, message)
            log.warning("bridge: sender refused")
        except Exception as e:                          # noqa: BLE001
            log.warning("bridge: bad message (%s)", type(e).__name__)

    P.BrowserView.on_navigation, P.BrowserView.on_js_bridge_call = on_navigation, on_js_bridge_call
    PATCHED.extend(["on_navigation", "on_js_bridge_call"])
    return P
