"""File actions per OS: open a PSD in Photoshop, show a file in the file manager, copy a PNG. Argument lists only (no
shell). OS modules are imported inside the functions, so this loads on every OS. Each returns (ok, message)."""
import base64
import ntpath
import os
import subprocess
import sys
import threading
from pathlib import Path

OS = {"darwin": "mac", "win32": "win"}.get(sys.platform, "linux")
TIMEOUT = 15
PS_BUNDLE = "com.adobe.Photoshop"                   # every Photoshop year shares it
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MAX_PNG = 64 << 20
SHOW = {"mac": "Showing it in Finder.", "win": "Showing it in Explorer.", "linux": "Showing it in your file manager."}
NO_PS = "Photoshop not found: opened with your default app."
NOT_PNG = "That file isn't a PNG."


# ---- external effects (the self-test swaps in recorders) ----
def call(argv):
    """Runs argv, waits (15 s at most), returns its exit code."""
    return subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          timeout=TIMEOUT).returncode


def spawn(argv):
    """Starts argv (Windows: also one command line) detached; never waits."""
    if OS == "win":
        kw = {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
    else:
        kw = {"start_new_session": True}
    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
    threading.Thread(target=proc.wait, daemon=True).start()          # no zombie


def startfile(p):
    os.startfile(str(p))                                             # Windows only


def clipboard(data, path):
    """Puts PNG bytes on the system clipboard as a picture."""
    return {"mac": _mac_copy, "win": _win_copy, "linux": _gtk_copy}[OS](data, path)


pasteboard = None                                    # macOS: None = the general pasteboard; the self-test's private one


# ---- the three actions ----
def open_psd(p):
    p = str(p)
    if OS == "mac":
        if call(["/usr/bin/open", "-b", PS_BUNDLE, p]) == 0:
            return True, "Opening in Photoshop…"
        if call(["/usr/bin/open", p]) == 0:
            return True, NO_PS
        return False, "No app on this computer opens PSD files."
    if OS == "win":
        how, exe = win_photoshop()
        if how == "assoc":
            startfile(p)
        elif exe:
            spawn([exe, p])
        else:
            startfile(p)
            return True, NO_PS
        return True, "Opening in Photoshop…"
    spawn(["xdg-open", p])
    return True, "Opening…"


def reveal(p):
    p = Path(p)
    if OS == "mac":
        call(["/usr/bin/open", "-R", str(p)])
    elif OS == "win":
        windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot") or r"C:\Windows"
        spawn(f'"{windir}\\explorer.exe" /select,"{p}"')            # quotes keep commas whole; exit code means nothing
    else:
        try:
            done = call(["gdbus", "call", "--session", "--dest", "org.freedesktop.FileManager1", "--object-path",
                         "/org/freedesktop/FileManager1", "--method", "org.freedesktop.FileManager1.ShowItems",
                         f"['{p.as_uri()}']", ""])
        except (OSError, subprocess.TimeoutExpired):
            done = 1
        if done:
            spawn(["xdg-open", str(p.parent)])
    return True, SHOW[OS]


def copy_png(p):
    with open(p, "rb") as f:
        data = f.read(MAX_PNG + 1)
    if len(data) > MAX_PNG or not data.startswith(PNG_MAGIC):
        return False, NOT_PNG
    if not clipboard(data, Path(p)):
        return False, "The clipboard didn't take it: try again."
    return True, "PNG copied."


# ---- Windows: where Photoshop is ----
def win_photoshop(assoc=None, reg=None, exists=os.path.isfile):
    """('assoc', None) when .psd opens in Photoshop already; ('exe', path) from App Paths or the newest
    Adobe\\Photoshop\\<n>\\ApplicationPath; (None, None) when not found."""
    exe = (assoc or _assoc_exe)(".psd")
    if exe and ntpath.basename(exe).lower() == "photoshop.exe":
        return "assoc", None
    if reg is None:
        import winreg as reg
    for hive in (reg.HKEY_LOCAL_MACHINE, reg.HKEY_CURRENT_USER):
        try:
            with reg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Photoshop.exe") as k:
                path = reg.QueryValueEx(k, "")[0]
            if path and exists(path):
                return "exe", path
        except OSError:
            pass
    found = []
    try:
        with reg.OpenKey(reg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Adobe\Photoshop") as root:
            i = 0
            while True:
                try:
                    name = reg.EnumKey(root, i)
                except OSError:
                    break
                i += 1
                try:
                    with reg.OpenKey(root, name) as k:
                        path = ntpath.join(reg.QueryValueEx(k, "ApplicationPath")[0], "Photoshop.exe")
                    num = float(name)
                except (OSError, ValueError):
                    continue
                if exists(path):
                    found.append((num, path))
    except OSError:
        pass
    return ("exe", max(found)[1]) if found else (None, None)


def _assoc_exe(ext):
    import ctypes
    from ctypes import wintypes
    size = wintypes.DWORD(1024)
    buf = ctypes.create_unicode_buffer(size.value)
    if ctypes.windll.shlwapi.AssocQueryStringW(0, 2, ext, "open", buf, ctypes.byref(size)):   # ASSOCSTR_EXECUTABLE
        return None
    return buf.value


# ---- clipboards ----
def _mac_copy(data, _path):
    from AppKit import NSPasteboard, NSPasteboardTypePNG
    from Foundation import NSData
    from PyObjCTools import AppHelper
    done, out = threading.Event(), {}

    def put():
        try:
            pb = pasteboard or NSPasteboard.generalPasteboard()
            pb.clearContents()
            out["ok"] = bool(pb.setData_forType_(NSData.dataWithBytes_length_(data, len(data)), NSPasteboardTypePNG))
        except Exception as e:                       # noqa: BLE001 (raised again below)
            out["err"] = e
        finally:
            done.set()
    if threading.current_thread() is threading.main_thread():
        put()
    else:
        AppHelper.callAfter(put)
    if not done.wait(5):
        raise TimeoutError("pasteboard")
    if "err" in out:
        raise out["err"]
    return out["ok"]


def _win_copy(data, _path):
    import clr                                       # pythonnet, loaded by pywebview for WebView2
    clr.AddReference("System.Windows.Forms")
    clr.AddReference("System.Drawing")
    from System import Convert
    from System.Drawing import Image
    from System.IO import MemoryStream
    from System.Threading import ApartmentState, Thread, ThreadStart
    from System.Windows.Forms import Clipboard, DataObject
    raw, out = Convert.FromBase64String(base64.b64encode(data).decode("ascii")), {}

    def put():                                       # the clipboard needs an STA thread
        try:
            obj = DataObject()
            obj.SetData("PNG", False, MemoryStream(raw))                 # keeps transparency (Discord, Chrome, Office)
            obj.SetImage(Image.FromStream(MemoryStream(raw)))            # a bitmap for apps that skip "PNG"
            Clipboard.SetDataObject(obj, True, 10, 100)
            out["ok"] = True
        except Exception as e:                       # noqa: BLE001
            out["err"] = e
    t = Thread(ThreadStart(put))
    t.SetApartmentState(ApartmentState.STA)
    t.Start()
    if not t.Join(5000):
        raise TimeoutError("clipboard")
    if "err" in out:
        raise RuntimeError(type(out["err"]).__name__)
    return out.get("ok", False)


def _gtk_copy(_data, path):
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gdk, GdkPixbuf, GLib, Gtk
    done, out = threading.Event(), {}

    def put():
        try:
            cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            cb.set_image(GdkPixbuf.Pixbuf.new_from_file(str(path)))
            cb.store()
            out["ok"] = True
        except Exception as e:                       # noqa: BLE001
            out["err"] = e
        finally:
            done.set()
        return False
    GLib.idle_add(put)
    if not done.wait(5):
        raise TimeoutError("clipboard")
    if "err" in out:
        raise out["err"]
    return out["ok"]
