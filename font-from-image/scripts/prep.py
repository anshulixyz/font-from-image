"""Normalise a photo / scan / screenshot of lettering into a clean ink map.

Handles uneven lighting (background division), light ruled lines on notebook paper,
small skew, and inverted (light-on-dark) images. Writes a PNG with dark ink on white that
every later script reads.

Usage:
  prep.py IMAGE --out build/prepared.png [--remove-rules] [--deskew] [--invert] [--scale 2]

Look at the output before continuing: if strokes are broken, lower --thresh; if letters bleed
together, raise it. --scale upsamples small images so the letters are at least ~25 px tall.
"""
import argparse
import os
import numpy as np
from PIL import Image
from scipy import ndimage as ndi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--out", required=True)
    ap.add_argument("--invert", action="store_true", help="light lettering on a dark background")
    ap.add_argument("--remove-rules", action="store_true", help="erase long horizontal lines (ruled paper)")
    ap.add_argument("--deskew", action="store_true", help="rotate by up to +-5 degrees to level the lines")
    ap.add_argument("--scale", type=float, default=1.0, help="resample factor before processing (use 2 for small images)")
    ap.add_argument("--thresh", type=float, default=0.25, help="ink threshold after normalisation (0-1)")
    ap.add_argument("--soft", action="store_true", help="keep antialiased grey values instead of a hard threshold")
    a = ap.parse_args()

    im = Image.open(a.image).convert("L")
    if a.scale != 1.0:
        im = im.resize((int(im.width * a.scale), int(im.height * a.scale)), Image.LANCZOS)
    g = np.asarray(im).astype(np.float32) / 255.0
    if a.invert:
        g = 1.0 - g

    # background normalisation: divide by a heavily blurred version so lighting gradients vanish
    bg = ndi.median_filter(g, size=max(15, int(min(g.shape) * 0.03) | 1))
    bg = ndi.gaussian_filter(bg, sigma=max(5, min(g.shape) * 0.01))
    norm = np.clip(g / np.maximum(bg, 1e-3), 0, 1.2)
    ink = np.clip(1.0 - norm, 0, 1)                       # 1 = ink
    # stretch contrast so the darkest 1% of ink becomes 1
    hi = np.percentile(ink, 99.5)
    ink = np.clip(ink / max(hi, 1e-3), 0, 1)

    if a.remove_rules:
        mask = ink > a.thresh
        # a ruled line is a horizontal run far longer than any letter
        long_h = ndi.binary_opening(mask, structure=np.ones((1, int(mask.shape[1] * 0.25))))
        long_h = ndi.binary_dilation(long_h, iterations=2)
        ink[long_h] = 0

    if a.deskew:
        best, best_score = 0.0, -1
        for ang in np.arange(-5, 5.01, 0.25):
            rot = ndi.rotate(ink, ang, reshape=False, order=1)
            prof = (rot > a.thresh).sum(1).astype(float)
            score = prof.var()
            if score > best_score:
                best, best_score = ang, score
        if abs(best) > 0.1:
            ink = np.clip(ndi.rotate(ink, best, reshape=False, order=1), 0, 1)
        print(f"deskew: rotated {best:+.2f} deg")

    # photo edges (table, shadow, rotation fill) are not lettering: clear a thin border
    b = max(3, int(0.01 * min(ink.shape)))
    ink[:b, :] = 0; ink[-b:, :] = 0; ink[:, :b] = 0; ink[:, -b:] = 0

    if a.soft:
        out = ink
    else:
        # hard-ish threshold with a little antialiasing kept around the edge
        out = np.clip((ink - a.thresh) / (1 - a.thresh) * 1.6, 0, 1)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    Image.fromarray((255 - out * 255).astype(np.uint8)).save(a.out)
    rows = (out > 0.45).sum(1)
    print(f"wrote {a.out} ({out.shape[1]}x{out.shape[0]}), {int((rows > 2).sum())} rows with ink")


if __name__ == "__main__":
    main()
