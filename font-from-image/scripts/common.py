"""Shared helpers for the font-from-image scripts."""
import json
import os
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

UP = 8          # upscale factor used before tracing / composing
THR = 0.45      # ink threshold on the normalised ink map (0 = paper, 1 = solid ink)


def load_ink(path):
    """Return the image as a float ink map in [0, 1] (1 = ink). Accepts a prepared PNG or any image."""
    im = Image.open(path).convert("L")
    return 1.0 - np.asarray(im).astype(np.float32) / 255.0


def disk(r):
    r = max(int(round(r)), 0)
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    return (xx * xx + yy * yy) <= r * r + 0.5


def glyph_gray(ink, g, build):
    """Antialiased crop of one glyph, masked to its own connected component (stored in build/masks)."""
    mask = np.asarray(Image.open(os.path.join(build, "masks", f"{g['id']}.png"))) > 0
    big = ndi.binary_dilation(mask, iterations=1)
    return ink[g["y0"]:g["y1"], g["x0"]:g["x1"]] * big


def upscale_bitmap(gray, pad=2, thr=0.5):
    """Bicubic-upscale a grayscale crop UP x and threshold it: a smooth binary bitmap for tracing."""
    h, w = gray.shape
    gg = np.zeros((h + 2 * pad, w + 2 * pad), np.float32)
    gg[pad:-pad, pad:-pad] = gray
    up = Image.fromarray((gg * 255).astype(np.uint8)).resize((gg.shape[1] * UP, gg.shape[0] * UP), Image.BICUBIC)
    bm = np.asarray(up).astype(np.float32) / 255 > thr
    return ndi.binary_opening(bm, iterations=1), pad


def trace_bitmap(bm, to_font):
    """Trace a binary bitmap with potrace. to_font maps (px, py) in bitmap pixels -> font units.
    Returns a list of contours; each contour is a list of ("move"|"line", (x, y)) or ("curve", (c1, c2, p))."""
    import potrace
    # potracer treats 0 as ink, so invert
    path = potrace.Bitmap(~bm).trace(turdsize=UP * UP, turnpolicy=potrace.POTRACE_TURNPOLICY_MINORITY,
                                     alphamax=1.0, opticurve=1, opttolerance=0.25)
    contours = []
    for curve in path:
        pts = [("move", to_font(curve.start_point.x, curve.start_point.y))]
        for s in curve.segments:
            if s.is_corner:
                pts.append(("line", to_font(s.c.x, s.c.y)))
                pts.append(("line", to_font(s.end_point.x, s.end_point.y)))
            else:
                pts.append(("curve", (to_font(s.c1.x, s.c1.y), to_font(s.c2.x, s.c2.y), to_font(s.end_point.x, s.end_point.y))))
        contours.append(pts)
    return contours


def embolden(bm, radius_px):
    """Dilate a bitmap by a circular pen (radius in bitmap pixels)."""
    if radius_px <= 0:
        return bm
    return ndi.binary_dilation(bm, structure=disk(radius_px))


def read_transcript(path):
    """One text line per image line. Blank lines are ignored; a line that is just '-' marks an image line to skip."""
    lines = []
    for raw in open(path, encoding="utf-8").read().splitlines():
        t = raw.rstrip()
        if not t:
            continue
        lines.append(t)
    return lines


def save_json(obj, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    json.dump(obj, open(path, "w"), indent=1)


def load_json(path):
    return json.load(open(path))
