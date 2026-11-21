# PyInstaller spec, macOS and Windows: pyinstaller --noconfirm packaging/CardBrowser.spec (after packaging/notices.py).
# Env: CB_TARGET_ARCH (macOS arm64 / x86_64; default this machine's), CARDBROWSER_BUNDLE_ID (a test id; default the real one).
import os
import re
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
VERSION = re.search(r'^VERSION = "([^"]+)"', (ROOT / "cardbrowser.py").read_text(encoding="utf-8"), re.M).group(1)
BUNDLE_ID = os.environ.get("CARDBROWSER_BUNDLE_ID") or "io.github.michaeljsr.cardbrowser"   # the saved web data is keyed on it
assert re.fullmatch(r"io\.github\.michaeljsr\.cardbrowser(\.[a-z0-9]+)?", BUNDLE_ID), BUNDLE_ID
MAC = sys.platform == "darwin"
NOTICES = ROOT / "THIRD-PARTY-NOTICES.txt"
assert NOTICES.is_file(), "run packaging/notices.py THIRD-PARTY-NOTICES.txt first"
ICON = ROOT / "packaging" / "icon" / ("CardBrowser.icns" if MAC else "CardBrowser.ico")   # make_icon.py
WHY = "CardBrowser reads your TTSCardMaker folder to open, show and copy card files."
UNUSED = ["qt", "cef", "mshtml", "android", "gtk"] + (["winforms", "edgechromium", "win32"] if MAC else ["cocoa"])

a = Analysis(
    [str(ROOT / "cardbrowser.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "inject.js"), "."), (str(ROOT / "LICENSE"), "."), (str(NOTICES), ".")],
    hiddenimports=["selftest"],
    excludes=["tkinter", "_tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6", "qtpy", "cefpython3", "gi", "pytest"]
    + ["webview.platforms." + m for m in UNUSED],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CardBrowser",
    console=False,
    upx=False,
    argv_emulation=False,
    target_arch=os.environ.get("CB_TARGET_ARCH") or None,
    codesign_identity=None,
    icon=None if MAC else str(ICON),   # Windows: the exe, its window and the taskbar (pywebview takes the exe's icon)
)
coll = COLLECT(exe, a.binaries, a.datas, upx=False, name="CardBrowser")
if MAC:
    app = BUNDLE(
        coll,
        name="CardBrowser.app",
        bundle_identifier=BUNDLE_ID,
        icon=str(ICON),
        version=VERSION,
        info_plist={
            "CFBundleName": "CardBrowser",
            "CFBundleDisplayName": "CardBrowser",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
            "NSDesktopFolderUsageDescription": WHY,
            "NSDocumentsFolderUsageDescription": WHY,
            "NSDownloadsFolderUsageDescription": WHY,
            "NSRemovableVolumesUsageDescription": WHY,
        },
    )
