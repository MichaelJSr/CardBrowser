"""The rules that keep the page in its lane: which URLs are the site, which paths are card files, which bridge messages
pass, what each OS's actions run (with fakes: no Photoshop, file manager, clipboard or registry is touched)."""
import os
import time
from pathlib import Path

import pytest

import actions
import cardbrowser
import guards


@pytest.fixture(autouse=True)
def live_site():
    guards.SITE = guards.urlsplit(guards.LIVE)
    guards._opened.clear()
    cardbrowser._recent.clear()
    yield


SITE = "https://michaeljsr.github.io/TTSCardMaker/"
ON_SITE = [SITE, SITE + "index.html", SITE + "#/card/a-snack2", SITE + "c/mini-doomer/", SITE + "?q=fire#/cards",
           "https://michaeljsr.github.io/TTSCardMaker", "https://MichaelJSr.github.io/TTSCardMaker/",
           "https://michaeljsr.github.io:443/TTSCardMaker/", SITE + "c/cho-gath/", SITE + "rulebook/"]
OFF_SITE = ["http://michaeljsr.github.io/TTSCardMaker/", "https://michaeljsr.github.io/", "https://michaeljsr.github.io/Other/",
            "https://michaeljsr.github.io/TTSCardMakerX/", "https://michaeljsr.github.io/TTSCardMaker/../Other/",
            "https://michaeljsr.github.io/TTSCardMaker/%2e%2e/Other/", "https://michaeljsr.github.io/TTSCardMaker/a\\..\\b",
            "https://michaeljsr.github.io/TTSCardMaker/%5c..%5cx", "https://evil.example/TTSCardMaker/",
            "https://michaeljsr.github.io.evil.example/TTSCardMaker/", "https://user@michaeljsr.github.io/TTSCardMaker/",
            "https://u:p@michaeljsr.github.io/TTSCardMaker/", "https://michaeljsr.github.io:8443/TTSCardMaker/",
            "file:///TTSCardMaker/", "javascript:alert(1)", "data:text/html,x", "about:blank", "", None,
            "https://[::1/TTSCardMaker/", "https://michaeljsr.github.io:99999/TTSCardMaker/",
            "blob:https://michaeljsr.github.io/1234"]


@pytest.mark.parametrize("url", ON_SITE)
def test_on_site(url):
    assert guards.on_site(url) and guards.frame_ok(url)


@pytest.mark.parametrize("url", OFF_SITE)
def test_off_site(url):
    assert not guards.on_site(url)


@pytest.mark.parametrize("url,ok", [("about:blank", True), ("about:srcdoc", True),
                                    ("blob:https://michaeljsr.github.io/5f1c", True),
                                    ("blob:https://evil.example/5f1c", False), ("blob:http://michaeljsr.github.io/1", False),
                                    ("https://michaeljsr.github.io/Other/", False), ("data:text/html,x", False),
                                    ("about:srcdoc#x", False), ("file:///etc/hosts", False)])
def test_frame_ok(url, ok):
    assert guards.frame_ok(url) is ok


def test_loopback_site_for_tests():
    guards.SITE = guards.urlsplit("http://127.0.0.1:18971/TTSCardMaker/")
    assert guards.on_site("http://127.0.0.1:18971/TTSCardMaker/c/z/")
    assert not guards.on_site("http://127.0.0.1:18972/TTSCardMaker/") and not guards.on_site("http://localhost:18971/TTSCardMaker/")
    assert cardbrowser.LOCAL_SITE.fullmatch("http://127.0.0.1:18971/TTSCardMaker/")
    for bad in ("https://127.0.0.1:1/x/", "http://example.com:80/x/", "http://127.0.0.1:1/x", "http://127.0.0.1:1/x/?a=/"):
        assert not cardbrowser.LOCAL_SITE.fullmatch(bad)


# ---- the path rule ----
ODD = ["Creatures/Everhood/5 Stars/Chris_&_Jordi.psd", "N.M.E/The_Evil,_Fricked_Up_Cursed_Idol.png",
       "Items/Equip/1 Stars/Bone's_Loans.psd", "Creatures/Other/5 Stars/Z!!!!!.png", "Items/Heal/2 Stars/A_Snack.psd",
       "Items/Heal/2 Stars/A_Snack2.png", "MDW/The Morgue/Cho'Gath.psd", "Field/Hollow Knight/Forgotten_Crossroads.png",
       "Auxiliary/Minions/Mini_Doomer.psd", "Creatures/Other/3 Stars/Mr._Grabby_(Something).PNG"]
ATTACKS = ["../x.psd", "/etc/x.psd", "C:/x.psd", "c:x.psd", "Creatures/../../x.psd", "Creatures\\..\\x.psd",
           "Creatures/a/CON.psd", "Creatures/a/con.txt.psd", "Creatures/a/x.psd ", " Creatures/x.psd", "Creatures/a./x.psd",
           "Types/x.png", "MDW/Linked/x.png", "MDW/Templates/x.psd", ".git/x.psd", "site/index.psd", "Creatures/x.exe",
           "Creatures/x.txt", "Creatures/a.psd:s.psd", "Creatures//x.psd", "Creatures/./x.psd", "Creatures/x\x00.psd",
           "Creatures/x?.psd", "Creatures/x*.psd", 'Creatures/"x".psd', "Creatures/<x>.psd", "Creatures/x|y.psd", "",
           "Creatures/" + "a" * 227 + ".psd", 7, None, ["Creatures/x.psd"], "Creatures", "Creatures/"]


@pytest.mark.parametrize("rel", ODD)
def test_card_file_takes_odd_names(tmp_path, rel):
    p = cardbrowser.card_file(tmp_path, rel, (".psd", ".png"))
    assert p == tmp_path.resolve().joinpath(*rel.split("/"))


@pytest.mark.parametrize("rel", ATTACKS)
def test_card_file_refuses(tmp_path, rel):
    assert cardbrowser.card_file(tmp_path, rel, (".psd", ".png")) is None


def test_card_file_extension_per_call(tmp_path):
    assert cardbrowser.card_file(tmp_path, ODD[0], (".png",)) is None
    assert cardbrowser.card_file(tmp_path, ODD[1], (".psd",)) is None


@pytest.mark.skipif(os.name != "posix", reason="symlinks")
def test_card_file_refuses_a_link_out(tmp_path):
    root, out = tmp_path / "TTSCardMaker", tmp_path / "secret.png"
    (root / "Creatures").mkdir(parents=True)
    out.write_bytes(b"x")
    (root / "Creatures" / "Out.png").symlink_to(out)
    (root / "Creatures" / "Dir").symlink_to(tmp_path)
    assert cardbrowser.card_file(root, "Creatures/Out.png", (".png",)) is None
    assert cardbrowser.card_file(root, "Creatures/Dir/secret.png", (".png",)) is None


@pytest.mark.skipif(os.name != "posix", reason="symlinks")
def test_card_file_link_inside_must_land_on_a_card(tmp_path):
    root = tmp_path / "TTSCardMaker"
    for d in ("Creatures/Other/1 Stars", "tools", ".git", "Items/Heal", "Types"):
        (root / d).mkdir(parents=True)
    for f in ("tools/run.command", ".git/config", "Items/Heal/Real.psd", "Items/Heal/Real.png", "Types/x.png"):
        (root / f).write_bytes(b"x")
    links = {"Creatures/Other/1 Stars/Evil.psd": "../../../tools/run.command", "Creatures/Cfg.png": "../.git/config",
             "Creatures/Pic.psd": "../Items/Heal/Real.png", "Creatures/Type.png": "../Types/x.png",
             "Creatures/Same.psd": "../Items/Heal/Real.psd", "Creatures/Dir": ".."}
    for link, target in links.items():
        (root / link).symlink_to(target)
    for rel in ("Creatures/Other/1 Stars/Evil.psd", "Creatures/Cfg.png", "Creatures/Type.png",
                "Creatures/Dir/Types/x.png", "Creatures/Dir/tools/run.psd"):
        assert cardbrowser.card_file(root, rel, (".psd", ".png")) is None, rel
    real = root.resolve() / "Items/Heal/Real.psd"
    assert cardbrowser.card_file(root, "Creatures/Same.psd", (".psd",)) == real                 # another card file
    assert cardbrowser.card_file(root, "Creatures/Dir/Items/Heal/Real.psd", (".psd",)) == real
    assert cardbrowser.card_file(root, "Creatures/Same.psd", (".png",)) is None
    assert cardbrowser.card_file(root, "Creatures/Pic.psd", (".psd",)) is None                 # open_psd: a PNG is no PSD


def test_live_paths_rule_length():
    assert cardbrowser.card_file("/", "Creatures/" + "a" * 226 + ".psd", (".psd",)) is not None   # 240 is fine


def test_page_url_takes_the_escaped_form():
    class Uri:                                        # WebView2's System.Uri: str() unescapes
        AbsoluteUri = "https://michaeljsr.github.io/TTSCardMaker/#/cards?q=mini%20doomer"

        def __str__(self):
            return "https://michaeljsr.github.io/TTSCardMaker/#/cards?q=mini doomer"

    class Win:
        def __init__(self, u):
            self.u = u

        def get_current_url(self):
            return self.u
    assert cardbrowser.page_url(Win(Uri())) == Uri.AbsoluteUri and guards.outside(cardbrowser.page_url(Win(Uri())))
    assert cardbrowser.page_url(Win(SITE)) == SITE and cardbrowser.page_url(Win(None)) == "" == cardbrowser.page_url(None)


def test_windows_never_loads_mshtml(tmp_path, monkeypatch):
    """No WebView2: pywebview's winforms imports mshtml and writes IE mode to the registry; guards stops that import."""
    import sys
    import webview.platforms
    (tmp_path / "winforms.py").write_text("from . import mshtml as IE\nIE._set_ie_mode()\nrenderer = 'mshtml'\n")
    (tmp_path / "mshtml.py").write_text("def _set_ie_mode():\n    raise AssertionError('IE mode written')\n")
    monkeypatch.setattr(webview.platforms, "__path__", [str(tmp_path)])
    monkeypatch.delitem(sys.modules, "webview.platforms.winforms", raising=False)
    monkeypatch.setitem(sys.modules, guards.MSHTML, None)          # removed again after the test
    del sys.modules[guards.MSHTML]                                  # so only guards can block the import

    class Exit(Exception):
        pass
    monkeypatch.setattr(guards, "need_webview2", lambda: (_ for _ in ()).throw(Exit()))
    with pytest.raises(Exit):
        guards._install_win()
    assert "webview.platforms.winforms" not in sys.modules


# ---- the bridge gate ----
@pytest.mark.parametrize("name,params,vid,passes", [
    ("open_psd", ["Items/x.psd"], "123456789", True), ("reveal", [""], "5e-7", True), ("copy_png", ["x" * 1024], "1", True),
    ("open_psd.__globals__.pop", ["VERSION"], "1", False), ("open_psd.__globals__.__setitem__", ["a", "b"], "1", False),
    ("_app.window.gui.os.system", ["x"], "1", False), ("__class__", [], "1", False), ("pywebviewMoveWindow", [1, 2], "move", False),
    ("pywebviewEventHandler", {"event": {}}, "1", False), ("pywebviewAsyncCallback", "1", "1", False),
    ("pywebviewStateUpdate", {"key": "k", "value": 1}, "1", False), ("pywebviewStateDelete", "k", "1", False),
    ("open_psd", ["x"], '"]);x();//', False), ("open_psd", ["x"], "", False), ("open_psd", ["x"], "1" * 33, False),
    ("open_psd", ["x"], 1, False), ("open_psd", [], "1", False), ("open_psd", ["x", "y"], "1", False),
    ("open_psd", [42], "1", False), ("open_psd", [None], "1", False), ("open_psd", "x", "1", False), ("open_psd", None, "1", False),
    ("copy_png", ["x" * 1025], "1", False), ("OPEN_PSD", ["x"], "1", False), ("open_psd ", ["x"], "1", False),
    (["open_psd"], ["x"], "1", False), ({"a": 1}, ["x"], "1", False), (None, ["x"], "1", False)])
def test_gate(name, params, vid, passes):
    seen = []
    guards.gate(lambda *a: seen.append(a))(None, name, params, vid)
    assert bool(seen) is passes


# ---- the system browser opener ----
def test_outside_takes_only_http(monkeypatch):
    opened = []
    monkeypatch.setattr(guards, "_browser", opened.append)
    for bad in ("file:///etc/hosts", "javascript:alert(1)", "ms-settings:display", "smb://host/x", "https://u@x.com/",
                "https:///x", "https://x .com/", "data:text/html,x", "https://" + "a" * 2050, "HTTPS//x.com"):
        assert guards.outside(bad) is False
    assert opened == []
    assert guards.outside("https://github.com/MichaelJSr/CardBrowser/releases/tag/v0.1.0") is True
    assert guards.outside("http://127.0.0.1:1/x") and guards.outside("https://raw.githubusercontent.com/a b") is False
    assert guards.outside("https://example.com") is True
    assert guards.outside("https://example.com/4") is False                              # 3 per 10 s
    assert len(opened) == 3


# ---- settings and the folder ----
def test_settings_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("CARDBROWSER_HOME", str(tmp_path / "home"))
    assert cardbrowser.load_settings() == {}
    cardbrowser.save_settings({"folder": "/x/TTSCardMaker"})
    assert cardbrowser.load_settings() == {"folder": "/x/TTSCardMaker"}
    assert sorted(p.name for p in (tmp_path / "home").iterdir()) == ["settings.json"]
    (tmp_path / "home" / "settings.json").write_text("[1, 2", encoding="utf-8")
    assert cardbrowser.load_settings() == {}


def tc(root):
    for d in ("Types", "MDW/Templates", "MDW/Linked"):
        (root / d).mkdir(parents=True, exist_ok=True)
    return root


def test_folder_is_tc_or_its_subfolder(tmp_path):
    assert cardbrowser.tc_in(tmp_path) is None
    tc(tmp_path / "TTSCardMaker")
    assert cardbrowser.tc_in(tmp_path) == tmp_path / "TTSCardMaker"
    assert cardbrowser.tc_in(tmp_path / "TTSCardMaker") == tmp_path / "TTSCardMaker"
    assert cardbrowser.links_missing(tmp_path / "TTSCardMaker")
    (tmp_path / "TTSCardMaker" / "MDW" / "Linked" / "x.png").write_bytes(b"x")
    assert not cardbrowser.links_missing(tmp_path / "TTSCardMaker")


@pytest.fixture
def clone(tmp_path, monkeypatch):
    root = tc(tmp_path / "TTSCardMaker")
    (root / "MDW/Linked/x.png").write_bytes(b"x")
    card = root / "Items/Heal/2 Stars"
    card.mkdir(parents=True)
    (card / "A_Snack.psd").write_bytes(b"8BPS")
    (card / "A_Snack2.png").write_bytes(actions.PNG_MAGIC + b"rest")
    (card / "Fake.png").write_bytes(b"GIF89a")
    monkeypatch.setenv("CARDBROWSER_HOME", str(tmp_path / "home"))
    cardbrowser.save_settings({"folder": str(root)})
    handler = cardbrowser.setup_logging()
    yield root
    cardbrowser.log.removeHandler(handler)
    handler.close()


def test_act_messages(clone, monkeypatch):
    ran = []
    monkeypatch.setattr(actions, "call", lambda argv: ran.append(argv) or 0)
    monkeypatch.setattr(actions, "OS", "mac")
    api = cardbrowser.Api()
    got = api.open_psd("Items/Heal/2 Stars/A_Snack.psd")
    assert got == {"ok": True, "msg": "Opening in Photoshop…"}
    assert ran == [["/usr/bin/open", "-b", "com.adobe.Photoshop", str(clone.resolve() / "Items/Heal/2 Stars/A_Snack.psd")]]
    assert api.open_psd("Items/Heal/2 Stars/Gone.psd")["msg"] == cardbrowser.NOT_YET
    assert api.open_psd("../x.psd")["msg"] == cardbrowser.NOT_CARD
    assert api.open_psd("Items/Heal/2 Stars/A_Snack2.png")["msg"] == cardbrowser.NOT_CARD
    assert api.reveal("Items/Heal/2 Stars/A_Snack2.png")["msg"] == "Showing it in Finder."
    monkeypatch.setattr(actions, "clipboard", lambda data, p: ran.append(len(data)) or True)
    cardbrowser._recent.clear()                       # 6 clicks per 10 s
    assert api.copy_png("Items/Heal/2 Stars/Fake.png")["msg"] == actions.NOT_PNG
    assert api.copy_png("Items/Heal/2 Stars/A_Snack2.png")["msg"] == "PNG copied."
    assert ran[-1] == 12


def test_act_limits_and_errors(clone, monkeypatch):
    monkeypatch.setattr(actions, "call", lambda argv: 0)
    monkeypatch.setattr(actions, "OS", "mac")
    api, rel = cardbrowser.Api(), "Items/Heal/2 Stars/A_Snack.psd"
    assert [api.open_psd(rel)["ok"] for _ in range(6)] == [True] * 6
    assert api.open_psd(rel)["msg"] == cardbrowser.TOO_MANY
    cardbrowser._recent.clear()
    with cardbrowser._busy:
        assert api.open_psd(rel)["msg"] == cardbrowser.BUSY

    def boom(argv):
        raise OSError(f"no such file: {clone}")
    monkeypatch.setattr(actions, "call", boom)
    cardbrowser._recent.clear()
    got = api.open_psd(rel)
    assert got == {"ok": False, "msg": "That didn't work (OSError)."} and str(clone) not in got["msg"]

    def denied(argv):
        raise PermissionError(str(clone))
    monkeypatch.setattr(actions, "call", denied)
    assert api.open_psd(rel)["msg"] == cardbrowser.NO_ACCESS
    log = (cardbrowser.app_home() / "cardbrowser.log").read_text(encoding="utf-8")
    assert "error: OSError at" in log and "no access: PermissionError at" in log
    assert str(clone) not in log and str(Path.home()) not in log


def test_no_folder_asks(tmp_path, monkeypatch):
    monkeypatch.setenv("CARDBROWSER_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(cardbrowser, "_window", None)
    assert cardbrowser.Api().reveal("Items/x.png")["msg"] == cardbrowser.CHOOSE
    cardbrowser.save_settings({"folder": str(tmp_path / "gone")})
    cardbrowser._recent.clear()
    assert cardbrowser.Api().reveal("Items/x.png")["msg"] == cardbrowser.CHOOSE


def test_picker_takes_the_subfolder(tmp_path, monkeypatch):
    monkeypatch.setenv("CARDBROWSER_HOME", str(tmp_path / "home"))
    tc(tmp_path / "GitHub" / "TTSCardMaker")
    (tmp_path / "GitHub" / "TTSCardMaker" / "MDW/Linked/x.png").write_bytes(b"x")

    class Win:
        def __init__(self, pick):
            self.pick = pick

        def create_file_dialog(self, kind):
            return self.pick
    import types
    import sys
    monkeypatch.setitem(sys.modules, "webview", types.SimpleNamespace(FileDialog=types.SimpleNamespace(FOLDER=20)))
    monkeypatch.setattr(cardbrowser, "_window", Win((str(tmp_path / "GitHub"),)))
    assert cardbrowser.pick_folder() == (tmp_path / "GitHub" / "TTSCardMaker", "")
    assert cardbrowser.load_settings()["folder"] == str(tmp_path / "GitHub" / "TTSCardMaker")
    monkeypatch.setattr(cardbrowser, "_window", Win((str(tmp_path),)))
    assert cardbrowser.pick_folder() == (None, cardbrowser.NOT_TC)
    monkeypatch.setattr(cardbrowser, "_window", Win(None))
    assert cardbrowser.pick_folder() == (None, cardbrowser.CHOOSE)


# ---- what each OS runs (fakes only) ----
@pytest.fixture
def effects(monkeypatch):
    ran = []
    monkeypatch.setattr(actions, "call", lambda argv: ran.append(("call", argv)) or 0)
    monkeypatch.setattr(actions, "spawn", lambda argv: ran.append(("spawn", argv)))
    monkeypatch.setattr(actions, "startfile", lambda p: ran.append(("startfile", str(p))))
    return ran


P = Path("/c/TTSCardMaker/N.M.E/The_Evil,_Fricked_Up_Cursed_Idol.psd")


def test_mac_commands(effects, monkeypatch):
    monkeypatch.setattr(actions, "OS", "mac")
    assert actions.open_psd(P) == (True, "Opening in Photoshop…")
    assert actions.reveal(P.with_suffix(".png")) == (True, "Showing it in Finder.")
    assert effects == [("call", ["/usr/bin/open", "-b", "com.adobe.Photoshop", str(P)]),
                       ("call", ["/usr/bin/open", "-R", str(P.with_suffix(".png"))])]
    effects.clear()
    monkeypatch.setattr(actions, "call", lambda argv: effects.append(argv) or (1 if "-b" in argv else 0))
    assert actions.open_psd(P) == (True, actions.NO_PS)
    assert effects[-1] == ["/usr/bin/open", str(P)]


def test_linux_commands(effects, monkeypatch):
    monkeypatch.setattr(actions, "OS", "linux")
    q = Path("/home/x/TTSCardMaker/Items/Equip/1 Stars/Bone's_Loans.png")
    assert actions.open_psd(P) == (True, "Opening…")
    assert actions.reveal(q)[0]
    assert effects[0] == ("spawn", ["xdg-open", str(P)])
    assert effects[1][1][-2] == "['file:///home/x/TTSCardMaker/Items/Equip/1%20Stars/Bone%27s_Loans.png']"
    effects.clear()
    monkeypatch.setattr(actions, "call", lambda argv: 1)
    actions.reveal(q)
    assert effects == [("spawn", ["xdg-open", str(q.parent)])]


class FakeReg:
    HKEY_LOCAL_MACHINE, HKEY_CURRENT_USER = "HKLM", "HKCU"

    def __init__(self, keys):
        self.keys = keys                                  # {(hive, path): {value name: value}}

    class Key:
        def __init__(self, hive, path):
            self.hive, self.path = hive, path

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def OpenKey(self, hive, path):
        if isinstance(hive, FakeReg.Key):
            hive, path = hive.hive, hive.path + "\\" + path
        if not any(h == hive and (p == path or p.startswith(path + "\\")) for h, p in self.keys):
            raise OSError(path)
        return FakeReg.Key(hive, path)

    def QueryValueEx(self, key, name):
        try:
            return self.keys[(key.hive, key.path)][name], 1
        except KeyError:
            raise OSError(name) from None

    def EnumKey(self, key, i):
        subs = sorted({p[len(key.path) + 1:].split("\\")[0] for h, p in self.keys if h == key.hive and p.startswith(key.path + "\\")})
        if i >= len(subs):
            raise OSError(i)
        return subs[i]


AP = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Photoshop.exe"
AD = r"SOFTWARE\Adobe\Photoshop"


def test_win_photoshop_lookup_order():
    ps = r"C:\Program Files\Adobe\Adobe Photoshop 2023\Photoshop.exe"
    ok = lambda p: p in (ps, r"C:\PS26\Photoshop.exe")
    assert actions.win_photoshop(lambda e: ps, FakeReg({}), ok) == ("assoc", None)
    reg = FakeReg({("HKLM", AP): {"": ps}, ("HKLM", AD + r"\190.0"): {"ApplicationPath": r"C:\PS26"}})
    assert actions.win_photoshop(lambda e: r"C:\Windows\mspaint.exe", reg, ok) == ("exe", ps)
    reg = FakeReg({("HKLM", AD + r"\160.0"): {"ApplicationPath": r"C:\Old"}, ("HKLM", AD + r"\190.0"): {"ApplicationPath": r"C:\PS26"},
                   ("HKLM", AD + r"\x"): {}})
    assert actions.win_photoshop(lambda e: None, reg, ok) == ("exe", r"C:\PS26\Photoshop.exe")
    assert actions.win_photoshop(lambda e: None, FakeReg({}), ok) == (None, None)


def test_windows_commands(effects, monkeypatch):
    monkeypatch.setattr(actions, "OS", "win")
    monkeypatch.setenv("WINDIR", r"C:\Windows")
    w = Path(r"C:\Users\<you>\Documents\GitHub\TTSCardMaker\N.M.E\The_Evil,_Fricked_Up_Cursed_Idol.png")
    monkeypatch.setattr(actions, "win_photoshop", lambda: ("assoc", None))
    assert actions.open_psd(w) == (True, "Opening in Photoshop…")
    monkeypatch.setattr(actions, "win_photoshop", lambda: ("exe", r"C:\PS\Photoshop.exe"))
    actions.open_psd(w)
    monkeypatch.setattr(actions, "win_photoshop", lambda: (None, None))
    assert actions.open_psd(w) == (True, actions.NO_PS)
    assert actions.reveal(w) == (True, "Showing it in Explorer.")
    assert effects == [("startfile", str(w)), ("spawn", [r"C:\PS\Photoshop.exe", str(w)]), ("startfile", str(w)),
                       ("spawn", f'"C:\\Windows\\explorer.exe" /select,"{w}"')]


def test_copy_refuses_big_or_not_png(tmp_path, monkeypatch):
    monkeypatch.setattr(actions, "clipboard", lambda data, p: pytest.fail("clipboard touched"))
    monkeypatch.setattr(actions, "MAX_PNG", 16)
    (tmp_path / "big.png").write_bytes(actions.PNG_MAGIC + b"x" * 9)
    (tmp_path / "gif.png").write_bytes(b"GIF89a")
    assert actions.copy_png(tmp_path / "big.png") == (False, actions.NOT_PNG)
    assert actions.copy_png(tmp_path / "gif.png") == (False, actions.NOT_PNG)


def test_rate_window_slides(clone, monkeypatch):
    monkeypatch.setattr(actions, "call", lambda argv: 0)
    monkeypatch.setattr(actions, "OS", "mac")
    t = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: t[0])
    api = cardbrowser.Api()
    for _ in range(6):
        api.reveal("Items/Heal/2 Stars/A_Snack.psd")
    assert api.reveal("Items/Heal/2 Stars/A_Snack.psd")["msg"] == cardbrowser.TOO_MANY
    t[0] += 10.1
    assert api.reveal("Items/Heal/2 Stars/A_Snack.psd")["ok"]
