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
_browser = webbrowser.open                  # the self-test swaps in a recorder


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
        if (name in ALLOWED and isinstance(value_id, str) and ID_OK(value_id) and isinstance(params, list)
                and len(params) == 1 and isinstance(params[0], str) and len(params[0]) <= ARG_MAX):
            return base(window, name, params, value_id)
        log.warning("bridge: dropped %.40r", name)
    js_bridge_call.gated = True
    return js_bridge_call


def install(site=LIVE):
    """Checks the engine and patches pywebview for this OS. A missing name raises: the app does not start unguarded."""
    global SITE
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
    return PATCHED


def _install_mac():
    import objc
    from webview.platforms import cocoa as P

    class CBBridge(P.BrowserView.JSBridge):            # ObjC class names are global: unique, defined once
        def userContentController_didReceiveScriptMessage_(self, ctl, msg):   # main thread
            if msg.frameInfo().isMainFrame() and on_site(msg.webView().URL().absoluteString()):
                return objc.super(CBBridge, self).userContentController_didReceiveScriptMessage_(ctl, msg)
            log.warning("bridge: sender refused")

    class CBDelegate(P.BrowserView.BrowserDelegate):
        def webView_decidePolicyForNavigationAction_decisionHandler_(self, wv, action, handler):
            url, frame = str(action.request().URL().absoluteString()), action.targetFrame()
            if frame_ok(url) or (frame is None and not action.shouldPerformDownload()):
                return objc.super(CBDelegate, self).webView_decidePolicyForNavigationAction_decisionHandler_(
                    wv, action, handler)
            if frame is not None and frame.isMainFrame() and action.navigationType() == 0:   # a link click
                outside(url)
            handler(0)                                  # cancel, any frame

    P.BrowserView.JSBridge, P.BrowserView.BrowserDelegate = CBBridge, CBDelegate
    PATCHED.extend(["JSBridge", "BrowserDelegate"])
    return P


def _install_win():
    from webview.platforms import winforms
    if winforms.renderer != "edgechromium":           # pywebview would silently use IE
        need_webview2()
    from webview.platforms import edgechromium as P
    nav, notify = P.EdgeChrome.on_navigation_start, P.EdgeChrome.on_script_notify

    def on_navigation_start(self, sender, args):       # main frame only
        url = str(args.Uri)
        if frame_ok(url):
            return nav(self, sender, args)
        args.Cancel = True
        if args.IsUserInitiated:
            outside(url)

    def on_script_notify(self, sender, args):
        if on_site(str(args.Source)):
            return notify(self, sender, args)
        log.warning("bridge: sender refused")

    P.EdgeChrome.on_navigation_start, P.EdgeChrome.on_script_notify = on_navigation_start, on_script_notify
    PATCHED.extend(["on_navigation_start", "on_script_notify"])
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

    def on_navigation(self, wv, decision, kind):        # main frames and subframes
        if type(decision) is P.webkit.NavigationPolicyDecision:
            action = decision.get_navigation_action()
            url = action.get_request().get_uri()
            if not frame_ok(url):
                if action.get_navigation_type() == P.webkit.NavigationType.LINK_CLICKED:
                    outside(url)
                decision.ignore()
                return True
        return nav(self, wv, decision, kind)

    def on_js_bridge_call(self, manager, message):      # WebKitGTK gives no sender: the main frame's URI
        if on_site(self.webview.get_uri()):
            return bridge(self, manager, message)
        log.warning("bridge: sender refused")

    P.BrowserView.on_navigation, P.BrowserView.on_js_bridge_call = on_navigation, on_js_bridge_call
    PATCHED.extend(["on_navigation", "on_js_bridge_call"])
    return P
