"""The pywebview names guards.install() patches, read from the installed source with ast (every backend, on any OS):
a pywebview change fails here before it can open an unguarded bridge."""
import ast
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(importlib.util.find_spec("webview").origin).parent
PIN = "6.2.1"


def tree(rel):
    return ast.parse((ROOT / rel).read_text(encoding="utf-8"))


def classes(node):
    return {n.name: n for n in ast.walk(node) if isinstance(n, ast.ClassDef)}


def methods(cls):
    return {n.name: [a.arg for a in n.args.args] for n in cls.body if isinstance(n, ast.FunctionDef)}


def imported(mod):
    names = set()
    for n in mod.body:
        if isinstance(n, ast.Import):
            names |= {a.asname or a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            names |= {a.asname or a.name for a in n.names}
    return names


def assigned(mod, name):
    for n in mod.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets):
            return ast.literal_eval(n.value) if isinstance(n.value, ast.Constant) else n.value
    return None


def test_version_pinned():
    assert assigned(tree("_version.py"), "__version__") == PIN
    req = (Path(__file__).resolve().parent.parent / "requirements.txt").read_text(encoding="utf-8")
    assert f"pywebview=={PIN}" in req


def test_bridge_call_signature():
    fn = {n.name: n for n in tree("util.py").body if isinstance(n, ast.FunctionDef)}["js_bridge_call"]
    assert [a.arg for a in fn.args.args] == ["window", "func_name", "param", "value_id"]


def test_settings_keys():
    src = (ROOT / "__init__.py").read_text(encoding="utf-8")
    for key in ("ALLOW_DOWNLOADS", "ALLOW_FILE_URLS", "OPEN_EXTERNAL_LINKS_IN_BROWSER"):
        assert f"'{key}'" in src


def test_cocoa_points():
    mod = tree("platforms/cocoa.py")
    assert {"webbrowser", "js_bridge_call"} <= imported(mod) and assigned(mod, "renderer") == "wkwebview"
    c = classes(mod)
    assert "userContentController_didReceiveScriptMessage_" in methods(c["JSBridge"])
    d = methods(c["BrowserDelegate"])
    assert d["webView_decidePolicyForNavigationAction_decisionHandler_"] == ["self", "webview", "action", "handler"]
    assert "webView_createWebViewWithConfiguration_forNavigationAction_windowFeatures_" in d
    assert {"JSBridge", "BrowserDelegate"} <= {n.name for n in c["BrowserView"].body if isinstance(n, ast.ClassDef)}
    src = (ROOT / "platforms/cocoa.py").read_text(encoding="utf-8")
    assert "BrowserView.JSBridge.alloc()" in src and "BrowserView.BrowserDelegate.alloc()" in src   # looked up at use


def test_edgechromium_points():
    mod = tree("platforms/edgechromium.py")
    assert {"webbrowser", "js_bridge_call"} <= imported(mod)
    m = methods(classes(mod)["EdgeChrome"])
    assert m["on_navigation_start"] == ["self", "sender", "args"] and m["on_script_notify"] == ["self", "_", "args"]
    assert m["on_new_window_request"] == ["self", "sender", "args"]
    src = (ROOT / "platforms/edgechromium.py").read_text(encoding="utf-8")
    assert "NavigationStarting += self.on_navigation_start" in src and "WebMessageReceived += self.on_script_notify" in src
    assert "NewWindowRequested += self.on_new_window_request" in src
    assert m["on_webview_ready"] == ["self", "sender", "args"] and {"Action", "Task", "String"} <= imported(mod)   # START
    assert "CoreWebView2InitializationCompleted += self.on_webview_ready" in src
    assert "self.syncContextTaskScheduler = TaskScheduler.FromCurrentSynchronizationContext()" in src
    win = (ROOT / "platforms/winforms.py").read_text(encoding="utf-8")
    assert "renderer = 'edgechromium'" in win
    assert win.index("from . import mshtml as IE") < win.index("IE._set_ie_mode()")   # guards blocks that import first


def test_gtk_points():
    mod = tree("platforms/gtk.py")
    assert {"webbrowser", "js_bridge_call", "webkit"} <= imported(mod)
    m = methods(classes(mod)["BrowserView"])
    assert m["on_navigation"] == ["self", "webview", "decision", "decision_type"]
    assert m["on_js_bridge_call"] == ["self", "manager", "message"]
    src = (ROOT / "platforms/gtk.py").read_text(encoding="utf-8")
    assert "connect('decide-policy', self.on_navigation)" in src
    assert "connect('script-message-received', self.on_js_bridge_call)" in src
    assert "self.manager = webkit.UserContentManager()" in src and "user_content_manager=self.manager" in src   # START


@pytest.mark.parametrize("name", ["pywebviewMoveWindow", "pywebviewEventHandler", "pywebviewAsyncCallback",
                                  "pywebviewStateUpdate", "pywebviewStateDelete"])
def test_internal_names_still_these(name):
    assert f"'{name}'" in (ROOT / "util.py").read_text(encoding="utf-8")       # the gate drops every one


def test_webview2_notice_names_the_bundled_sdk():
    """The Windows notices carry the licence of the WebView2 SDK version pywebview bundles there."""
    spec = importlib.util.spec_from_file_location("notices", Path(__file__).resolve().parent.parent / "packaging/notices.py")
    notices = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(notices)
    assert notices.WEBVIEW2.encode("utf-16-le") in (ROOT / "lib/Microsoft.Web.WebView2.Core.dll").read_bytes()
    title, text = notices.webview2()
    assert notices.WEBVIEW2 in title and "Redistributions in binary form" in text and "NOTICES AND INFORMATION" in text


def test_minos_reads_every_slice(tmp_path):
    """packaging/minos.py (the macOS job): any binary needing a newer macOS than Info.plist's minimum fails the build."""
    import plistlib
    import struct
    spec = importlib.util.spec_from_file_location("minos", Path(__file__).resolve().parent.parent / "packaging/minos.py")
    minos = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(minos)

    def thin(cmd, v):                              # a 64-bit Mach-O header, a 16-byte filler command, then cmd
        body = struct.pack("<II", 0x1, 16) + bytes(8) + (struct.pack("<IIIIII", 0x32, 24, 1, v, v, 0) if cmd == 0x32
                                                          else struct.pack("<IIII", 0x24, 16, v, v))
        return struct.pack("<IiiIIIII", 0xFEEDFACF, 0, 0, 2, 2, len(body), 0, 0) + body
    a, b = thin(0x24, 0x0A0D00), thin(0x32, 0x0B0000)                  # 10.13 (old command), 11.0
    fat = struct.pack(">II", 0xCAFEBABE, 2) + struct.pack(">iiIII", 7, 3, 48, len(a), 0) + struct.pack(">iiIII", 12, 0, 48 + len(a), len(b), 0)
    assert minos.minos_of(fat + bytes(48 - len(fat)) + a + b) == [(10, 13, 0), (11, 0, 0)]
    app = tmp_path / "CardBrowser.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"LSMinimumSystemVersion": "11.0"}))
    (app / "Contents" / "MacOS" / "CardBrowser").write_bytes(fat + bytes(48 - len(fat)) + a + b)
    assert minos.main(app) == 0
    (app / "Contents" / "lib.so").write_bytes(thin(0x32, 0x1A0000))     # 26.0
    assert minos.main(app) == 1
