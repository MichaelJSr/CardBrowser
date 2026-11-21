"""The oldest macOS each binary in a built .app runs on (its Mach-O minos) must not be newer than the app's
LSMinimumSystemVersion (the README's "macOS 11 or newer"). Usage: python packaging/minos.py dist/CardBrowser.app"""
import plistlib
import struct
import sys
from pathlib import Path

BUILD_VERSION, VERSION_MIN_MACOSX, MACOS = 0x32, 0x24, 1


def version(v):
    return (v >> 16, (v >> 8) & 0xFF, v & 0xFF)


def thin(b, at=0):
    """The macOS minos of the Mach-O at b[at:], or None (no version load command)."""
    magic = struct.unpack_from("<I", b, at)[0]
    if magic not in (0xFEEDFACE, 0xFEEDFACF):
        return None
    ncmds = struct.unpack_from("<I", b, at + 16)[0]
    p = at + (32 if magic == 0xFEEDFACF else 28)
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", b, p)
        if cmd == BUILD_VERSION and struct.unpack_from("<I", b, p + 8)[0] == MACOS:
            return version(struct.unpack_from("<I", b, p + 12)[0])
        if cmd == VERSION_MIN_MACOSX:
            return version(struct.unpack_from("<I", b, p + 8)[0])
        p += size
    return None


def minos(path):
    """[minos of each architecture] of a Mach-O file (thin or universal); [] for any other file."""
    return minos_of(Path(path).read_bytes())


def minos_of(b):
    if len(b) < 32:
        return []
    magic, n = struct.unpack_from(">II", b, 0)
    if magic in (0xCAFEBABE, 0xCAFEBABF) and n < 20:          # universal; a Java class file has n >= 45
        size, fmt = (20, ">iiIII") if magic == 0xCAFEBABE else (32, ">iiQQII")
        return [thin(b, struct.unpack_from(fmt, b, 8 + i * size)[2]) for i in range(n)]
    return [thin(b)] if struct.unpack_from("<I", b, 0)[0] in (0xFEEDFACE, 0xFEEDFACF) else []


def main(app):
    app = Path(app)
    floor = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())["LSMinimumSystemVersion"]
    want = tuple(int(x) for x in (floor.split(".") + ["0", "0"])[:3])
    seen, bad = [], []
    for f in sorted(p for p in app.rglob("*") if p.is_file() and not p.is_symlink()):
        for v in filter(None, minos(f)):
            seen.append(v)
            if v > want:
                bad.append((v, f.relative_to(app).as_posix()))
    show = lambda v: ".".join(map(str, v))                                       # noqa: E731
    print(f"{len(seen)} Mach-O slices, oldest macOS {show(min(seen, default=(0,)))} to {show(max(seen, default=(0,)))}; "
          f"LSMinimumSystemVersion {floor}; newer than that: {len(bad)}")
    for v, f in sorted(bad, reverse=True)[:20]:
        print(f"  {show(v)}  {f}")
    return 1 if bad or not all(minos(app / "Contents" / "MacOS" / app.stem) or [None]) else 0   # its own binary is read


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
