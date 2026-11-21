"""CardBrowser's icons from the game's logo (TTSCardMaker MDW/Assets/Holders/Half_Holder.jpg: white on black, 671 px).

    python packaging/icon/make_icon.py <Half_Holder.jpg> [--web <dir>]

Writes CardBrowser.ico (Windows) and CardBrowser.icns (macOS, needs iconutil) beside this file; --web also writes the
website's favicon-16.png, favicon-32.png and apple-touch-icon.png. The look is the rulebook cover's: the white logo and
its ring on black. At 16 px the ring blurs into a grey disc, so 16 and 24 px show the logo alone, larger.
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
W = 2048                                # drawn at 2048, then scaled down (smooth edges)
SRC_PX, SRC_C, RING_IN = 671, 335, 262  # the source's size, centre, and the radius between the logo and its ring


def logo_masks(src, d):
    """(logo, ring) masks d x d: the white logo inside the ring, and the ring."""
    a = np.array(Image.open(src).convert("L").resize((d, d), Image.LANCZOS)) > 128
    s = d / SRC_PX
    y, x = np.mgrid[0:d, 0:d]
    r = np.hypot(x - SRC_C * s, y - SRC_C * s)
    out = []
    for part in (a & (r < RING_IN * s), a & (r >= RING_IN * s)):
        m = Image.fromarray(part.astype(np.uint8) * 255).filter(ImageFilter.GaussianBlur(s * 0.6))
        out.append(m.point(lambda v: 255 if v >= 128 else 0))
    return out


def tile(src, inset, ring=True, radius=0.2237, shadow=False, square=False):
    """The icon at W px: a black tile (inset from the edge, rounded unless square) with the white logo."""
    im = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    a, b = round(W * inset), round(W * (1 - inset))
    shape = Image.new("L", (W, W), 0)
    ImageDraw.Draw(shape).rounded_rectangle((a, a, b - 1, b - 1), radius=0 if square else round((b - a) * radius), fill=255)
    if shadow:                                                      # macOS icons carry a soft shadow in their margin
        sh = shape.filter(ImageFilter.GaussianBlur(W * 0.01)).point(lambda v: v * 110 // 255)
        im.paste(Image.new("RGBA", (W, W), (0, 0, 0, 255)), (0, round(W * 0.006)), sh)
    g = np.array(Image.radial_gradient("L").resize((W, W))).astype(float)       # 0 at the centre, 255 at the corners
    v = np.clip(34 - g * 0.09, 0, 255).astype(np.uint8)
    im.paste(Image.merge("RGBA", [Image.fromarray(v)] * 3 + [Image.new("L", (W, W), 255)]), (0, 0), shape)
    side = b - a
    d = round(side * (0.825 if ring else 1.07))                    # without the ring the logo fills the tile
    logo, rim = logo_masks(src, d)
    at = ((W - d) // 2, (W - d) // 2)
    white = Image.new("RGBA", (d, d), (255, 255, 255, 255))
    if not ring:
        keep = Image.new("L", (W, W), 0)
        keep.paste(logo, at)
        logo = Image.composite(keep, Image.new("L", (W, W), 0), shape).crop((at[0], at[1], at[0] + d, at[1] + d))
    im.paste(white, at, logo)
    if ring:
        im.paste(white, at, rim)
    return im


def sized(im, px):
    return im.resize((px, px), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src", type=Path, help="Half_Holder.jpg")
    ap.add_argument("--web", type=Path, help="also write the website's favicons here")
    args = ap.parse_args()

    mac, mac_small = tile(args.src, 0.1, shadow=True), tile(args.src, 0.06, ring=False)    # Apple's grid: 824 of 1024
    win, win_small = tile(args.src, 0.03), tile(args.src, 0.0, ring=False, radius=0.18)

    small = [sized(win_small, p) for p in (16, 24)]
    big = [sized(win, p) for p in (32, 48, 64, 128, 256)]
    big[-1].save(HERE / "CardBrowser.ico", sizes=[(i.width, i.height) for i in small + big], append_images=small + big[:-1])

    if shutil.which("iconutil"):
        with tempfile.TemporaryDirectory() as tmp:
            iconset = Path(tmp) / "CardBrowser.iconset"
            iconset.mkdir()
            for pt in (16, 32, 128, 256, 512):
                for scale in (1, 2):
                    px = pt * scale
                    art = mac_small if px < 32 else mac
                    sized(art, px).save(iconset / f"icon_{pt}x{pt}{'@2x' if scale == 2 else ''}.png")
            subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(HERE / "CardBrowser.icns")], check=True)
    else:
        print("no iconutil (macOS only): CardBrowser.icns not rebuilt", file=sys.stderr)

    if args.web:
        args.web.mkdir(parents=True, exist_ok=True)
        sized(win_small, 16).save(args.web / "favicon-16.png", optimize=True)
        sized(tile(args.src, 0.0, radius=0.18), 32).save(args.web / "favicon-32.png", optimize=True)
        sized(tile(args.src, 0.0, square=True), 180).convert("RGB").save(args.web / "apple-touch-icon.png", optimize=True)
    print("ok")


if __name__ == "__main__":
    main()
