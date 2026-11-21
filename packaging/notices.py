"""Writes THIRD-PARTY-NOTICES.txt: every distribution installed in this Python (or in --path DIR) with its licence
text, then the licences of Python and OpenSSL (skipped with --no-runtime: the Linux build uses the system Python), and
on Windows those of Microsoft's WebView2 SDK files that pywebview bundles there.
Exits 1 if any licence text is not found. Usage: python packaging/notices.py [--path DIR] [--no-runtime] OUT"""
import argparse
import importlib.metadata as md
import re
import ssl
import sys
import sysconfig
from pathlib import Path

NAME = re.compile(r"(LICEN[CS]E|COPYING|NOTICE)", re.I)
RULE = "=" * 78
WEBVIEW2 = "1.0.3856.49"                             # the SDK version of pywebview 6.2.1's DLLs (tests/test_pins.py)
MIT = """Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE."""


def name_of(d):
    return d.metadata["Name"]


def shipped(d):
    """The licence files in the distribution's metadata folder."""
    out = []
    for f in d.files or ():
        if f.parts and f.parts[0].endswith((".dist-info", ".egg-info")) and NAME.search(f.name):
            text = f.read_text(encoding="utf-8").strip()
            if text and text not in out:
                out.append(text)
    return out


def copyright_lines(d):
    """Copyright lines from the top of the package's own source (for packages that ship no licence file)."""
    lines = []
    for f in d.files or ():
        if f.name == "__init__.py" and len(f.parts) == 2:
            head = f.read_text(encoding="utf-8")[:2000]
            lines += [ln.strip(" :") for ln in head.splitlines() if "copyright" in ln.lower()]
    return lines


def texts(d, every):
    """(how found, licence texts) for distribution d; every: all distributions, for a sibling of the same project."""
    found = shipped(d)
    if found:
        return "shipped", found
    lic = (d.metadata.get("License") or "").strip()
    if len(lic) > 300:                               # the full text in the metadata
        return "metadata", [lic]
    if name_of(d).lower().startswith("pyobjc"):      # one project, one licence; some parts ship no file
        for o in every:
            if name_of(o).lower().startswith("pyobjc") and shipped(o):
                return f"the PyObjC project's licence, as shipped with {name_of(o)}", shipped(o)
    if lic.upper() == "MIT" and copyright_lines(d):
        return "metadata: MIT; no licence file shipped", ["\n".join(copyright_lines(d)) + "\n\n" + MIT]
    return None, []


def runtime():
    """Python's licence (with the bundled libraries it lists) and OpenSSL's (Apache 2.0, the text packaging ships)."""
    out = []
    stdlib = Path(sysconfig.get_paths()["stdlib"])
    for p in (stdlib / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE"):
        if p.is_file():
            out.append((f"Python {sys.version.split()[0]}", p.read_text(encoding="utf-8", errors="replace").strip()))
            break
    else:
        out.append((f"Python {sys.version.split()[0]}", None))
    apache = None
    try:
        for f in md.distribution("packaging").files or ():
            if f.name == "LICENSE.APACHE":
                apache = f.read_text(encoding="utf-8").strip()
    except md.PackageNotFoundError:
        pass
    ok = apache and "Apache License" in apache and "Version 2.0, January 2004" in apache
    out.append((f"{ssl.OPENSSL_VERSION} (Apache License 2.0)", apache if ok else None))
    return out


def webview2():
    """pywebview's PyInstaller hook bundles these on Windows only: the SDK's LICENSE.txt and NOTICE.txt, as shipped in
    its NuGet package (packaging/webview2/)."""
    folder = Path(__file__).resolve().parent / "webview2"
    text = "\n\n----\n\n".join((folder / n).read_text(encoding="utf-8").strip() for n in ("LICENSE.txt", "NOTICE.txt"))
    return (f"Microsoft WebView2 SDK {WEBVIEW2} (Microsoft.Web.WebView2.Core.dll, Microsoft.Web.WebView2.WinForms.dll, "
            "WebView2Loader.dll; bundled by pywebview)", text)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--path", help="list the distributions in this folder only")
    ap.add_argument("--no-runtime", action="store_true")
    a = ap.parse_args(argv)
    dists = md.distributions(path=[a.path]) if a.path else md.distributions()
    every = sorted({name_of(d).lower(): d for d in dists}.values(), key=lambda d: name_of(d).lower())
    parts, missing = ["CardBrowser includes the software below. Each part keeps its own licence, given here in full.\n"], []
    for d in every:
        how, found = texts(d, every)
        if not found:
            missing.append(name_of(d))
            continue
        parts.append(f"{RULE}\n{name_of(d)} {d.version}" + ("" if how == "shipped" else f" ({how})") + f"\n{RULE}\n\n"
                     + "\n\n----\n\n".join(found) + "\n")
    win = sys.platform == "win32"
    for title, text in ([] if a.no_runtime else runtime()) + ([webview2()] if win else []):
        if text is None:
            missing.append(title)
        else:
            parts.append(f"{RULE}\n{title}\n{RULE}\n\n{text}\n")
    Path(a.out).write_text("\n".join(parts), encoding="utf-8", newline="\n")
    print(f"{a.out}: {len(every)} distributions" + ("" if a.no_runtime else " + Python + OpenSSL")
          + (" + WebView2 SDK" if win else "")
          + (f"; NO LICENCE TEXT FOR: {', '.join(missing)}" if missing else "; every licence text found"))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
