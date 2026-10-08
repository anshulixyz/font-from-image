"""Re-typeset the transcript with the built font, laid out like the source, for a side-by-side check.

Usage:
  specimen.py --build build --font fonts/MyHand-Regular.ttf [--native-font fonts/MyHand-Bold.ttf]
              [--compare original.png] [--out build/specimen.png] [--xheight-units 480]

Each line is drawn at its own baseline and size (from the measured line metrics), so the output
should overlay the source almost exactly if the segmentation and metrics are right. --compare
puts the original on the left and the specimen on the right. Lines whose glyphs were marked as a
separate style (pick_glyphs.py --native-lines) are drawn with --native-font when given.
"""
import argparse
import os
from PIL import Image, ImageDraw, ImageFont
from common import load_json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", default="build")
    ap.add_argument("--font", required=True)
    ap.add_argument("--native-font", default=None)
    ap.add_argument("--compare", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--xheight-units", type=int, default=480)
    ap.add_argument("--bg", default="245,240,232")
    ap.add_argument("--fg", default="40,25,20")
    a = ap.parse_args()

    sel = load_json(os.path.join(a.build, "selected.json"))
    src = Image.open(sel["image"])
    W, H = src.size
    bg = tuple(int(x) for x in a.bg.split(",")); fg = tuple(int(x) for x in a.fg.split(","))
    img = Image.new("RGB", (W, H), bg); d = ImageDraw.Draw(img)
    native_lines = {g["line"] for g in sel.get("selected_native", {}).values()}
    glyphs = load_json(os.path.join(a.build, "glyphs.json"))["glyphs"]
    left = {}
    for g in glyphs:
        left[g["line"]] = min(left.get(g["line"], 10 ** 9), g["x0"])
    for li, text in enumerate(sel["lines"]):
        m = sel["metrics"].get(str(li))
        if m is None:
            continue
        size = max(6, int(round(m["xheight"] / a.xheight_units * 1000)))
        path = a.native_font if (li in native_lines and a.native_font) else a.font
        ft = ImageFont.truetype(path, size)
        d.text((left.get(li, 20), m["baseline"]), text, font=ft, fill=fg, anchor="ls")
    out = a.out or os.path.join(a.build, "specimen.png")
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    img.save(out)
    if a.compare:
        orig = Image.open(a.compare).convert("RGB").resize((W, H))
        both = Image.new("RGB", (W * 2 + 20, H), (255, 255, 255)); both.paste(orig, (0, 0)); both.paste(img, (W + 20, 0))
        cmp_path = os.path.splitext(out)[0] + "_compare.png"; both.save(cmp_path); print("->", cmp_path)
    print("->", out)


if __name__ == "__main__":
    main()
