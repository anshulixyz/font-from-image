"""Compare candidate free fonts (Google Fonts) against a line from the image.

Downloads the TTFs of the named families straight from the google/fonts GitHub repository
(all open-licensed), renders the sample text in each, and writes a comparison sheet with the
image crop at the top so the candidates can be judged side by side.

Usage:
  identify.py --image IMG --crop x0 y0 x1 y1 --text "the sample line" \
              --families kalam,caveat,patrickhand --out build/identify

Families are the directory names used in github.com/google/fonts (lower case, no spaces:
"Patrick Hand" -> patrickhand). See references/free-handwriting-fonts.md for a curated list.
Downloaded fonts are cached in <out>/fonts so repeated runs are quick.
"""
import argparse
import json
import os
import subprocess
import urllib.request
from PIL import Image, ImageDraw, ImageFont
from common import load_ink
import numpy as np

API = "https://api.github.com/repos/google/fonts/contents/{lic}/{fam}"


def fetch_family(fam, dest):
    os.makedirs(dest, exist_ok=True)
    have = [f for f in os.listdir(dest) if f.lower().startswith(fam.lower().replace(" ", "")[:4]) and f.endswith(".ttf")]
    if have:
        return [os.path.join(dest, f) for f in have]
    got = []
    for lic in ("ofl", "apache", "ufl"):
        try:
            with urllib.request.urlopen(API.format(lic=lic, fam=fam), timeout=30) as r:
                entries = json.load(r)
        except Exception:
            continue
        for e in entries:
            if e["name"].endswith(".ttf"):
                path = os.path.join(dest, e["name"].replace("%5B", "[").replace("%5D", "]").replace("%2C", ","))
                urllib.request.urlretrieve(e["download_url"], path)
                got.append(path)
        if got:
            break
    if not got:
        print(f"  !! {fam}: not found in google/fonts (check the directory name)")
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--crop", type=int, nargs=4, metavar=("X0", "Y0", "X1", "Y1"), help="image region holding the sample text")
    ap.add_argument("--text", required=True, help="the text visible in the crop")
    ap.add_argument("--families", required=True, help="comma-separated google/fonts directory names")
    ap.add_argument("--out", default="build/identify")
    ap.add_argument("--size", type=int, default=0, help="render size in px (default: match the crop's letter height)")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    img = Image.open(a.image).convert("RGB")
    crop = img.crop(tuple(a.crop)) if a.crop else img
    # scale the crop to a 1200px-wide strip
    k = 1200 / crop.width
    crop = crop.resize((1200, max(1, int(crop.height * k))), Image.LANCZOS)
    size = a.size or max(14, int(crop.height * 0.55))

    fonts = []
    for fam in [f.strip() for f in a.families.split(",") if f.strip()]:
        for p in fetch_family(fam, os.path.join(a.out, "fonts")):
            fonts.append((fam, p))
    if not fonts:
        raise SystemExit("no fonts downloaded")

    rows = []
    for fam, p in fonts:
        try:
            ft = ImageFont.truetype(p, size)
        except Exception as e:
            print("skip", p, e); continue
        name = os.path.basename(p)
        rows.append((name, ft))

    row_h = int(size * 1.9)
    sheet = Image.new("RGB", (1240, crop.height + 30 + row_h * len(rows)), (255, 255, 255))
    sheet.paste(crop, (20, 10))
    d = ImageDraw.Draw(sheet)
    lab = ImageFont.load_default()
    y = crop.height + 30
    for name, ft in rows:
        d.text((20, y), name, font=lab, fill=(150, 60, 60))
        d.text((20, y + 14), a.text, font=ft, fill=(30, 20, 15))
        y += row_h
    out = os.path.join(a.out, "comparison.png")
    sheet.save(out)
    print(f"{len(rows)} fonts rendered -> {out}")
    print("Look at the sheet and compare letter by letter: a/g/y/f/t shapes, slant, stroke contrast, bounce, width.")


if __name__ == "__main__":
    main()
