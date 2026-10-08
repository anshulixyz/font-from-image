"""Is this lettering a font, or hand/AI-drawn? Repeated letters from a font are pixel-identical
(apart from sub-pixel placement); handwriting and AI lettering vary from instance to instance.

The script takes a small template (the most common letter shape it can find, or a region you
give) and template-matches it across the image, then tiles the best matches side by side so you
can look at them, and prints the correlation scores.

Usage: glyph_consistency.py IMAGE [--region x0 y0 x1 y1] --out build/consistency.png

Read the result like this:
  - many matches above ~0.95 and the tiles look identical  -> a real font: use the identify path
  - matches mostly 0.8-0.93 and tiles differ in shape       -> drawn/AI lettering: create a font
Sub-pixel placement and JPEG/WebP noise alone keep scores around 0.93-0.97, so look at the tiles,
not just the numbers.
"""
import argparse
import os
import numpy as np
from PIL import Image
from numpy.lib.stride_tricks import sliding_window_view
from scipy import ndimage as ndi
from common import load_ink


def auto_region(ink):
    """Pick a small, blob-like connected component of typical size (likely an 'o', 'e', 'a' ...)."""
    lab, n = ndi.label(ink > 0.45)
    objs = ndi.find_objects(lab)
    cands = []
    for i, sl in enumerate(objs, 1):
        h = sl[0].stop - sl[0].start; w = sl[1].stop - sl[1].start
        area = (lab[sl] == i).sum()
        if h < 8 or w < 6:
            continue
        cands.append((h, w, area, sl))
    if not cands:
        raise SystemExit("no components found; is the image prepared (dark ink on white)?")
    hs = np.array([c[0] for c in cands]); med = np.median(hs)
    # prefer components near the median height with a roughly square box (round letters)
    cands.sort(key=lambda c: abs(c[0] - med) / med + abs(c[1] / c[0] - 1.0))
    sl = cands[0][3]
    return sl[1].start - 1, sl[0].start - 1, sl[1].stop + 1, sl[0].stop + 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--region", type=int, nargs=4, metavar=("X0", "Y0", "X1", "Y1"))
    ap.add_argument("--out", default="build/consistency.png")
    ap.add_argument("--top", type=int, default=24)
    a = ap.parse_args()

    ink = load_ink(a.image)
    x0, y0, x1, y1 = a.region if a.region else auto_region(ink)
    # a light blur makes the comparison robust to sub-pixel placement, JPEG noise and resampling,
    # so identical glyphs score near 1 while genuinely different shapes still do not
    ink = ndi.gaussian_filter(ink, sigma=1.0)
    tpl = ink[y0:y1, x0:x1]
    th, tw = tpl.shape
    t = tpl - tpl.mean(); tn = np.sqrt((t * t).sum()) + 1e-6
    win = sliding_window_view(ink, (th, tw))
    w = win - win.mean(axis=(2, 3), keepdims=True)
    res = (w * t).sum(axis=(2, 3)) / (np.sqrt((w * w).sum(axis=(2, 3))) * tn + 1e-6)
    mx = ndi.maximum_filter(res, size=(max(th // 2, 5), max(tw // 2, 5)))
    peaks = np.argwhere((res == mx) & (res > 0.6))
    vals = sorted([(float(res[y, x]), int(x), int(y)) for y, x in peaks], reverse=True)[:a.top]

    S = max(1, 120 // th)
    sheet = Image.new("L", (tw * S * 12, th * S * ((len(vals) + 11) // 12)), 255)
    for i, (v, x, y) in enumerate(vals):
        tile = Image.fromarray((255 - ink[y:y + th, x:x + tw] * 255).astype(np.uint8)).resize((tw * S, th * S), Image.NEAREST)
        sheet.paste(tile, ((i % 12) * tw * S, (i // 12) * th * S))
    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    sheet.save(a.out)
    scores = [round(v, 3) for v, _, _ in vals]
    print(f"template {tw}x{th} at ({x0},{y0}); {len(vals)} matches -> {a.out}")
    print("scores:", scores)
    strong = sum(1 for s in scores[1:] if s >= 0.96)
    print("verdict:", "repeats look identical - consistent with a real font (or very regular AI lettering)" if strong >= 4
          else "repeats vary - hand-drawn or AI lettering; no font to find",
          "- confirm by looking at the tiles. Only a matching candidate in identify.py proves a font exists.")


if __name__ == "__main__":
    main()
