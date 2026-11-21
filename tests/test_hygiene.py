"""What the public repo must never hold, and what the app code must never do (patterns are built by concatenation so
this file never matches itself)."""
import ast
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
APP = ["cardbrowser.py", "guards.py", "actions.py"]


def tracked():
    try:
        out = subprocess.run(["gi" + "t", "-C", str(REPO), "ls-files", "-z"], capture_output=True, check=True).stdout
        files = [REPO / f for f in out.decode().split("\0") if f]
    except (OSError, subprocess.CalledProcessError):
        files = []
    return files or [p for p in REPO.rglob("*") if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts]


SECRETS = [re.compile(p) for p in (
    "/" + "Users/[A-Za-z]", r"C:\\" + r"Users\\[^<]", "gh" + "[pousr]_[A-Za-z0-9]{20}", "github" + "_pat_",
    "discord" + r"(app)?\.com/api/web" + "hooks", "xo" + "x[abprs]-", "AK" + "IA[0-9A-Z]{16}", "-----BEGIN [A-Z ]*PRIV" + "ATE KEY",
    "discord" + r"(app)?\.com/channels/", "co-" + "authored-by", "clau" + "de", "anthro" + "pic")]


@pytest.mark.parametrize("path", tracked(), ids=lambda p: p.relative_to(REPO).as_posix())
def test_no_secrets_paths_or_attribution(path):
    assert path.suffix.lower() not in (".psd", ".psb", ".png", ".avif", ".jpg"), "no card pictures in the repo"
    assert path.stat().st_size < 1 << 20
    text = path.read_text(encoding="utf-8", errors="replace")
    for p in SECRETS:
        assert not p.search(text if "clau" not in p.pattern and "anthro" not in p.pattern else text.lower()), p.pattern


def test_patterns_find():
    mac, win = "/" + "Users/me/x", "C:" + "\\" + "Users" + "\\" + "me" + "\\x"
    assert SECRETS[0].search(mac) and SECRETS[1].search(win)
    assert not SECRETS[1].search(win.replace("me", "<you>")) and not SECRETS[1].search(win.replace("\\", "\\\\"))


def calls(src):
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Call):
            f = n.func
            yield n, (f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""), \
                (f.value.id if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) else "")


@pytest.mark.parametrize("name", APP)
def test_no_shell_and_no_git(name):
    src = (REPO / name).read_text(encoding="utf-8")
    for n, fn, owner in calls(src):
        assert not any(k.arg == "shell" for k in n.keywords), f"{name}: shell="
        assert (owner, fn) not in (("os", "system"), ("os", "popen"), ("os", "execv"), ("subprocess", "getoutput"),
                                   ("subprocess", "getstatusoutput")), f"{name}: {owner}.{fn}"
    consts = {c.value for c in ast.walk(ast.parse(src)) if isinstance(c, ast.Constant) and isinstance(c.value, str)}
    assert "gi" + "t" not in consts, f"{name} runs git"


ANY = {"write_text", "write_bytes", "touch", "symlink_to", "unlink", "rmdir", "mkdir", "rename"}   # Path/os methods
OS_ONLY = {"replace", "remove", "makedirs", "utime", "chmod", "symlink", "link", "truncate", "removedirs"}
ALLOWED = {("cardbrowser.py", "save_settings"): {"mkdir", "write_text", "os.replace"},
           ("cardbrowser.py", "setup_logging"): {"mkdir"}, ("cardbrowser.py", "main"): {"open w"}}


def writes(mod):
    """(innermost function, what) for each call that can change the disk."""
    out = []

    def visit(node, fn):
        for child in ast.iter_child_nodes(node):
            here = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else fn
            if isinstance(child, ast.Call):
                f = child.func
                name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""
                owner = f.value.id if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) else ""
                if owner == "shutil" or (owner == "os" and name in OS_ONLY | ANY):
                    out.append((fn, f"{owner}.{name}"))
                elif name in ANY and owner != "os":
                    out.append((fn, name))
                elif name == "open" and len(child.args) > 1 and isinstance(child.args[1], ast.Constant) \
                        and set(str(child.args[1].value)) & set("wax+"):
                    out.append((fn, "open w"))
            visit(child, here)
    visit(mod, "<module>")
    return out


def test_writes_only_settings_and_log():
    for name in APP:
        for fn, what in writes(ast.parse((REPO / name).read_text(encoding="utf-8"))):
            assert what in ALLOWED.get((name, fn), ()), f"{name}:{fn} {what}"


def test_write_finder_finds():
    src = "import os, shutil\ndef f(p):\n    p.write_bytes(b'')\n    os.replace(a, b)\n    shutil.move(a, b)\n    open(p, 'a')\n    'x'.replace('a', 'b')"
    assert writes(ast.parse(src)) == [("f", "write_bytes"), ("f", "os.replace"), ("f", "shutil.move"), ("f", "open w")]


def test_inject_builds_dom_by_text_only(monkeypatch):
    js = (REPO / "inject.js").read_text(encoding="utf-8")
    assert js.count("%CONFIG%") == 1
    for name in ("inject.js", "selftest.py"):        # GTK: pywebview's script length is in characters, WebKit reads bytes
        assert (REPO / name).read_text(encoding="utf-8").isascii(), f"{name}: write \\u escapes"
    import cardbrowser
    import guards
    monkeypatch.setattr(cardbrowser, "_first", True)
    assert guards.START.isascii() and cardbrowser.inject_script().startswith(guards.NO_KEYS)     # NO_KEYS again after the load
    for bad in ("inner" + "HTML", "outer" + "HTML", "insertAdjacent" + "HTML", "document." + "write", "ev" + "al(", "data-" + "action"):
        assert bad not in js
