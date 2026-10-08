"""Compose characters that the image does not contain, out of the strokes it does contain.

Every missing character is assembled on a canvas from pieces: real strokes lifted from the
letters that were found (skeletonised so they can be scaled, flipped and rotated without
changing the pen width) plus short procedural lines and arcs. The result is re-inked with a
round pen whose radius is measured from the real letters, so the new glyphs share the pen.
When a lifted piece is unavailable (the image has no 'o', say) a procedural stand-in is drawn.

Used by build_font.py; run directly to preview:  synth_glyphs.py --build build --chars "ABC123?"
"""
import argparse
import math
import os
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
from skimage.morphology import skeletonize
from common import load_ink, load_json, glyph_gray, upscale_bitmap, disk, UP

CORE_R = 2
LIFTABLE = "locunvwxzs."


class Synth:
    def __init__(self, ink, selected, body_xh, asc_px, build):
        self.ink, self.S, self.build_dir = ink, selected, build
        self.X = body_xh * UP                       # x-height, canvas px
        self.C = asc_px * UP * 0.98                 # cap height (= ascender height of the hand)
        self.D = self.C * 0.95                      # digit height
        self.DESC = 0.5 * self.C
        self.TOP = int(0.3 * self.C)
        self.BL = self.TOP + int(self.C)            # baseline row on every canvas
        self.H = self.BL + int(self.DESC)
        self.pieces = {}
        for ch in LIFTABLE:
            if ch in selected:
                try:
                    self.pieces[ch] = self._core_of(ch)
                except Exception:
                    pass
        self.pen_r = self._measure_pen()
        self.ST = 2 * self.pen_r

    # ---------- stroke pieces ----------
    def _bitmap(self, ch):
        g = self.S[ch]
        bm, _ = upscale_bitmap(glyph_gray(self.ink, g, self.build_dir))
        return bm

    def _core_of(self, ch):
        """The full stroke bitmap, cropped. It is skeletonised after scaling (in shape()) so that
        skeleton jaggies are not magnified when a piece is enlarged."""
        bm = self._bitmap(ch)
        ys, xs = np.where(bm)
        return bm[ys.min():ys.max() + 1, xs.min():xs.max() + 1]

    def _measure_pen(self):
        """Half the stroke width, from the distance transform along the skeleton of real letters."""
        rs = []
        for ch in list(self.S)[:40]:
            try:
                bm = self._bitmap(ch)
            except Exception:
                continue
            sk = skeletonize(bm)
            if sk.sum() < 10:
                continue
            dt = ndi.distance_transform_edt(bm)
            rs.append(float(np.median(dt[sk])))
        return max(float(np.median(rs)) if rs else 0.08 * self.X, CORE_R + 1)

    # ---------- canvas ----------
    def canvas(self, width):
        return _Canvas(self, width)

    def build(self, chars):
        """chars: iterable of characters to compose. Returns {char: (bitmap, baseline_row, width_px)}."""
        out = {}
        for ch in chars:
            fn = RECIPES.get(ch)
            if fn is None:
                continue
            cv = fn(self)
            if cv is not None:
                out[ch] = (cv.ink(), self.BL, cv.w)
        return out


class _Canvas:
    def __init__(self, s, width):
        self.s = s; self.w = int(width)
        self.core = np.zeros((s.H, self.w + int(s.C)), bool)

    def _paste(self, piece, x, y_bottom):
        h, w = piece.shape; x = int(round(x)); row1 = self.s.BL - int(round(y_bottom)); row0 = row1 - h
        H, W = self.core.shape
        r0, r1, c0, c1 = max(row0, 0), min(row1, H), max(x, 0), min(x + w, W)
        if r1 <= r0 or c1 <= c0:
            return
        self.core[r0:r1, c0:c1] |= piece[r0 - row0:r1 - row0, c0 - x:c1 - x]

    def shape(self, name, x, y, w, h, flipx=False, flipy=False, rot=0.0):
        """A lifted stroke (or its procedural stand-in) scaled to w x h, bottom-left at (x, y)."""
        w, h = max(int(w), 3), max(int(h), 3)
        p = self.s.pieces.get(name)
        if p is not None:
            img = Image.fromarray((p.astype(np.float32) * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR)
            full = ndi.gaussian_filter(np.asarray(img).astype(np.float32) / 255, sigma=1.5) > 0.5
            arr = ndi.binary_dilation(skeletonize(full), structure=disk(CORE_R))
        else:
            arr = _procedural(name, w, h)
        if flipx: arr = arr[:, ::-1]
        if flipy: arr = arr[::-1]
        if rot: arr = ndi.rotate(arr.astype(np.float32), rot, order=1, reshape=True) > 0.5
        self._paste(arr, x, y)

    def dot(self, x, y, size=None):
        r = size or self.s.pen_r * 1.15
        self._paste(disk(r - CORE_R + 1), x - r, y)

    def poly(self, pts, bow=0.0):
        if bow and len(pts) == 2:
            (x0, y0), (x1, y1) = pts; dx, dy = x1 - x0, y1 - y0; L = math.hypot(dx, dy) or 1
            nx, ny = -dy / L, dx / L
            pts = bezier((x0, y0), ((x0 + x1) / 2 + nx * bow * L, (y0 + y1) / 2 + ny * bow * L), (x1, y1))
        layer = Image.new("L", (self.core.shape[1], self.core.shape[0]), 0)
        ImageDraw.Draw(layer).line([(x, self.s.BL - y) for x, y in pts], fill=255, width=2 * CORE_R + 1, joint="curve")
        self.core |= np.asarray(layer) > 0

    def line(self, p0, p1, bow=0.012): self.poly([p0, p1], bow=bow)

    def arc(self, cx, cy, r, a0, a1, ry=None):
        ry = r if ry is None else ry; n = max(8, int(abs(a1 - a0) / 6))
        self.poly([(cx + r * math.cos(math.radians(a0 + (a1 - a0) * t / n)),
                    cy + ry * math.sin(math.radians(a0 + (a1 - a0) * t / n))) for t in range(n + 1)])

    def curve(self, p0, p1, p2): self.poly(bezier(p0, p1, p2))

    def stem(self, x, y0, y1):
        self.shape("l", x - self.s.ST / 2 + 1, y0, self.s.ST * 0.9, y1 - y0)

    def ink(self):
        return ndi.binary_dilation(self.core, structure=disk(self.s.pen_r - CORE_R))


def bezier(p0, p1, p2, n=24):
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]) for t in (i / n for i in range(n + 1))]


def _procedural(name, w, h):
    """Stand-ins for lifted strokes, drawn as thin cores in a w x h box (row 0 = top)."""
    layer = Image.new("L", (w, h), 0); d = ImageDraw.Draw(layer); W = 2 * CORE_R + 1
    m = CORE_R + 1
    def L(pts): d.line(pts, fill=255, width=W, joint="curve")
    def A(cx, cy, rx, ry, a0, a1):
        n = max(8, int(abs(a1 - a0) / 6))
        L([(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * t / n)), cy - ry * math.sin(math.radians(a0 + (a1 - a0) * t / n))) for t in range(n + 1)])
    cx, cy, rx, ry = w / 2, h / 2, w / 2 - m, h / 2 - m
    if name == "o": A(cx, cy, rx, ry, 0, 360)
    elif name == "c": A(cx, cy, rx, ry, 40, 320)
    elif name == "u": A(cx, h - ry - m, rx, ry * 0.9, 180, 360); L([(m, m), (m, cy)]); L([(w - m, m), (w - m, h - m)])
    elif name == "n": A(cx, ry + m, rx, ry * 0.9, 0, 180); L([(m, cy), (m, h - m)]); L([(w - m, cy), (w - m, h - m)])
    elif name == "v": L([(m, m), (cx, h - m), (w - m, m)])
    elif name == "w": L([(m, m), (w * 0.3, h - m), (cx, h * 0.35), (w * 0.7, h - m), (w - m, m)])
    elif name == "x": L([(m, m), (w - m, h - m)]); L([(w - m, m), (m, h - m)])
    elif name == "z": L([(m, m), (w - m, m), (m, h - m), (w - m, h - m)])
    elif name == "s": A(cx, h * 0.27, rx, h * 0.25, 30, 270); A(cx, h * 0.73, rx, h * 0.25, 90, -150)
    elif name == "l": L([(cx, m), (cx, h - m)])
    elif name == ".": d.ellipse([m, m, w - m, h - m], fill=255)
    else: L([(cx, m), (cx, h - m)])
    return np.asarray(layer) > 0


# ---------------------------------------------------------------- recipes
# Each recipe draws one character on a fresh canvas. X = x-height, C = cap height, D = digit height.
def R(fn):
    RECIPES[fn.__name__.split("_", 1)[1] if "_" in fn.__name__ else fn.__name__] = fn
    return fn
RECIPES = {}

def _cv(s, w): return s.canvas(w)

# ---- lowercase (x-height forms; ascenders reach C, descenders reach -0.45 X)
def rec_a(s): X = s.X; w = 0.8 * X; cv = _cv(s, w); cv.shape("o", 0, 0, 0.88 * w, X); cv.stem(w - s.ST / 2, 0, X); return cv
def rec_b(s): X, C = s.X, s.C; w = 0.8 * X; cv = _cv(s, w); cv.stem(s.ST / 2, 0, C); cv.shape("o", 0.08 * w, 0, 0.92 * w, X); return cv
def rec_c(s): X = s.X; w = 0.75 * X; cv = _cv(s, w); cv.shape("c", 0, 0, w, X); return cv
def rec_d(s): X, C = s.X, s.C; w = 0.8 * X; cv = _cv(s, w); cv.shape("o", 0, 0, 0.9 * w, X); cv.stem(w - s.ST / 2, 0, C); return cv
def rec_e(s): X = s.X; w = 0.8 * X; cv = _cv(s, w); cv.arc(0.5 * w, 0.5 * X, 0.5 * w, 0, 305, ry=0.5 * X); cv.line((0.02 * w, 0.52 * X), (0.98 * w, 0.52 * X), bow=0); return cv
def rec_f(s): X, C = s.X, s.C; w = 0.55 * X; cv = _cv(s, w); cv.line((0.45 * w, 0), (0.45 * w, 0.8 * C), bow=0.01); cv.arc(0.45 * w + 0.35 * w, 0.8 * C, 0.35 * w, 180, 60, ry=0.2 * C); cv.line((0, X), (0.95 * w, X), bow=0); return cv
def rec_g(s): X = s.X; w = 0.8 * X; cv = _cv(s, w); cv.shape("o", 0, 0, 0.9 * w, X); cv.line((0.95 * w, X), (0.95 * w, -0.25 * X), bow=0); cv.arc(0.5 * w, -0.25 * X, 0.45 * w, 0, -180, ry=0.2 * X); return cv
def rec_h(s): X, C = s.X, s.C; w = 0.8 * X; cv = _cv(s, w); cv.stem(s.ST / 2, 0, C); cv.shape("n", 0, 0, w, X); return cv
def rec_i(s): X = s.X; w = s.ST; cv = _cv(s, w); cv.stem(w / 2, 0, X); cv.dot(w / 2, 1.3 * X); return cv
def rec_j(s): X = s.X; w = 0.55 * X; cv = _cv(s, w); cv.line((0.7 * w, X), (0.7 * w, -0.25 * X), bow=0); cv.arc(0.4 * w, -0.25 * X, 0.3 * w, 0, -180, ry=0.2 * X); cv.dot(0.7 * w, 1.3 * X); return cv
def rec_k(s): X, C = s.X, s.C; w = 0.75 * X; cv = _cv(s, w); cv.stem(s.ST / 2, 0, C); cv.line((0.95 * w, X), (0.1 * w, 0.35 * X)); cv.line((0.35 * w, 0.55 * X), (w, 0)); return cv
def rec_l(s): C = s.C; w = s.ST; cv = _cv(s, w); cv.stem(w / 2, 0, C); return cv
def rec_m(s): X = s.X; w = 1.35 * X; cv = _cv(s, w); cv.shape("n", 0, 0, 0.55 * w, X); cv.shape("n", 0.45 * w, 0, 0.55 * w, X); return cv
def rec_n(s): X = s.X; w = 0.8 * X; cv = _cv(s, w); cv.shape("n", 0, 0, w, X); return cv
def rec_o(s): X = s.X; w = 0.8 * X; cv = _cv(s, w); cv.shape("o", 0, 0, w, X); return cv
def rec_p(s): X = s.X; w = 0.8 * X; cv = _cv(s, w); cv.stem(s.ST / 2, -0.45 * X, X); cv.shape("o", 0.08 * w, 0, 0.92 * w, X); return cv
def rec_q(s): X = s.X; w = 0.8 * X; cv = _cv(s, w); cv.shape("o", 0, 0, 0.9 * w, X); cv.stem(w - s.ST / 2, -0.45 * X, X); return cv
def rec_r(s): X = s.X; w = 0.55 * X; cv = _cv(s, w); cv.stem(s.ST / 2, 0, X); cv.arc(0.55 * w, 0.6 * X, 0.45 * w, 180, 20, ry=0.4 * X); return cv
def rec_s(s): X = s.X; w = 0.65 * X; cv = _cv(s, w); cv.shape("s", 0, 0, w, X); return cv
def rec_t(s): X, C = s.X, s.C; w = 0.6 * X; cv = _cv(s, w); cv.line((0.4 * w, 0.12 * X), (0.4 * w, 0.78 * C), bow=0.01); cv.arc(0.4 * w + 0.3 * w, 0.12 * X, 0.3 * w, 180, 300, ry=0.12 * X); cv.line((0, X), (w, X), bow=0); return cv
def rec_u(s): X = s.X; w = 0.8 * X; cv = _cv(s, w); cv.shape("u", 0, 0, w, X); return cv
def rec_v(s): X = s.X; w = 0.8 * X; cv = _cv(s, w); cv.shape("v", 0, 0, w, X); return cv
def rec_w(s): X = s.X; w = 1.2 * X; cv = _cv(s, w); cv.shape("w", 0, 0, w, X); return cv
def rec_x(s): X = s.X; w = 0.8 * X; cv = _cv(s, w); cv.shape("x", 0, 0, w, X); return cv
def rec_y(s): X = s.X; w = 0.8 * X; cv = _cv(s, w); cv.line((0.02 * w, X), (0.5 * w, 0)); cv.line((0.98 * w, X), (0.15 * w, -0.45 * X)); return cv
def rec_z(s): X = s.X; w = 0.75 * X; cv = _cv(s, w); cv.shape("z", 0, 0, w, X); return cv
for _f in list(globals().values()):
    if callable(_f) and getattr(_f, "__name__", "").startswith("rec_"):
        RECIPES[_f.__name__[4:]] = _f

# ---- uppercase
def U(ch):
    def deco(fn): RECIPES[ch] = fn; return fn
    return deco

@U("A")
def _(s): C = s.C; w = 0.85 * C; cv = _cv(s, w); cv.shape("v", 0, 0, w, C, flipy=True); cv.line((0.2 * w, 0.36 * C), (0.8 * w, 0.36 * C)); return cv
@U("B")
def _(s): C = s.C; w = 0.62 * C; cv = _cv(s, w); cv.stem(s.ST / 2, 0, C); cv.arc(0.1 * w, 0.75 * C, 0.78 * w, 90, -90, ry=0.25 * C); cv.arc(0.1 * w, 0.26 * C, 0.88 * w, 90, -90, ry=0.27 * C); return cv
@U("C")
def _(s): C = s.C; w = 0.78 * C; cv = _cv(s, w); cv.shape("c", 0, 0, w, C); return cv
@U("D")
def _(s): C = s.C; w = 0.75 * C; cv = _cv(s, w); cv.stem(s.ST / 2, 0, C); cv.arc(0.08 * w, 0.5 * C, 0.9 * w, 90, -90, ry=0.5 * C); return cv
@U("E")
def _(s): C = s.C; w = 0.6 * C; cv = _cv(s, w); cv.stem(s.ST / 2, 0, C); cv.line((0, C), (w, C)); cv.line((0, 0.5 * C), (0.8 * w, 0.5 * C)); cv.line((0, 0), (w, 0)); return cv
@U("F")
def _(s): C = s.C; w = 0.6 * C; cv = _cv(s, w); cv.stem(s.ST / 2, 0, C); cv.line((0, C), (w, C)); cv.line((0, 0.5 * C), (0.78 * w, 0.5 * C)); return cv
@U("G")
def _(s): C = s.C; w = 0.8 * C; cv = _cv(s, w); cv.shape("c", 0, 0, w, C); cv.line((0.5 * w, 0.42 * C), (0.98 * w, 0.42 * C)); cv.line((0.98 * w, 0.42 * C), (0.98 * w, 0.12 * C)); return cv
@U("H")
def _(s): C = s.C; w = 0.72 * C; cv = _cv(s, w); cv.stem(s.ST / 2, 0, C); cv.stem(w - s.ST / 2, 0, C); cv.line((0, 0.5 * C), (w, 0.5 * C)); return cv
@U("I")
def _(s): C = s.C; w = s.ST; cv = _cv(s, w); cv.stem(s.ST / 2, 0, C); return cv
@U("J")
def _(s): C = s.C; w = 0.6 * C; cv = _cv(s, w); cv.line((0.72 * w, C), (0.72 * w, 0.3 * C), bow=0.005); cv.arc(0.42 * w, 0.3 * C, 0.3 * w, 0, -180); return cv
@U("K")
def _(s): C = s.C; w = 0.7 * C; cv = _cv(s, w); cv.stem(s.ST / 2, 0, C); cv.line((0.95 * w, C), (0.12 * w, 0.42 * C)); cv.line((0.3 * w, 0.55 * C), (w, 0)); return cv
@U("L")
def _(s): C = s.C; w = 0.58 * C; cv = _cv(s, w); cv.stem(s.ST / 2, 0, C); cv.line((0, 0), (w, 0)); return cv
@U("M")
def _(s): C = s.C; w = 1.0 * C; cv = _cv(s, w); cv.stem(s.ST / 2, 0, C); cv.stem(w - s.ST / 2, 0, C); cv.shape("v", 0.08 * w, 0.28 * C, 0.84 * w, 0.72 * C); return cv
@U("N")
def _(s): C = s.C; w = 0.75 * C; cv = _cv(s, w); cv.stem(s.ST / 2, 0, C); cv.stem(w - s.ST / 2, 0, C); cv.line((0.08 * w, C), (0.92 * w, 0)); return cv
@U("O")
def _(s): C = s.C; w = 0.85 * C; cv = _cv(s, w); cv.shape("o", 0, 0, w, C); return cv
@U("P")
def _(s): C = s.C; w = 0.62 * C; cv = _cv(s, w); cv.stem(s.ST / 2, 0, C); cv.arc(0.1 * w, 0.73 * C, 0.88 * w, 90, -90, ry=0.27 * C); return cv
@U("Q")
def _(s): C = s.C; w = 0.85 * C; cv = _cv(s, w); cv.shape("o", 0, 0, w, C); cv.line((0.6 * w, 0.22 * C), (1.02 * w, -0.1 * C)); return cv
@U("R")
def _(s): C = s.C; w = 0.66 * C; cv = _cv(s, w); cv.stem(s.ST / 2, 0, C); cv.arc(0.1 * w, 0.73 * C, 0.84 * w, 90, -90, ry=0.27 * C); cv.line((0.4 * w, 0.47 * C), (w, 0)); return cv
@U("S")
def _(s): C = s.C; w = 0.66 * C; cv = _cv(s, w); cv.shape("s", 0, 0, w, C); return cv
@U("T")
def _(s): C = s.C; w = 0.75 * C; cv = _cv(s, w); cv.line((0, C), (w, C)); cv.stem(w / 2, 0, C); return cv
@U("U")
def _(s): C = s.C; w = 0.75 * C; cv = _cv(s, w); cv.shape("u", 0, 0, w, C); return cv
@U("V")
def _(s): C = s.C; w = 0.8 * C; cv = _cv(s, w); cv.shape("v", 0, 0, w, C); return cv
@U("W")
def _(s): C = s.C; w = 1.1 * C; cv = _cv(s, w); cv.shape("w", 0, 0, w, C); return cv
@U("X")
def _(s): C = s.C; w = 0.75 * C; cv = _cv(s, w); cv.shape("x", 0, 0, w, C); return cv
@U("Y")
def _(s): C = s.C; w = 0.78 * C; cv = _cv(s, w); cv.shape("v", 0, 0.48 * C, w, 0.54 * C); cv.stem(w / 2, 0, 0.52 * C); return cv
@U("Z")
def _(s): C = s.C; w = 0.75 * C; cv = _cv(s, w); cv.shape("z", 0, 0, w, C); return cv

# ---- digits
@U("0")
def _(s): C, D = s.C, s.D; w = 0.62 * C; cv = _cv(s, w); cv.shape("o", 0, 0, w, D); return cv
@U("1")
def _(s): C, D = s.C, s.D; w = 0.45 * C; cv = _cv(s, w); cv.stem(0.62 * w, 0, D); cv.line((0.05 * w, 0.72 * D), (0.62 * w, D)); return cv
@U("2")
def _(s):
    C, D = s.C, s.D; w = 0.62 * C; cv = _cv(s, w); cv.arc(0.5 * w, 0.73 * D, 0.47 * w, 185, -35, ry=0.27 * D)
    cv.line((0.5 * w + 0.47 * w * math.cos(math.radians(-35)), 0.73 * D + 0.27 * D * math.sin(math.radians(-35))), (0.02 * w, 0)); cv.line((0, 0), (w, 0)); return cv
@U("3")
def _(s): C, D = s.C, s.D; w = 0.6 * C; cv = _cv(s, w); cv.arc(0.46 * w, 0.75 * D, 0.26 * D, 150, -90); cv.arc(0.46 * w, 0.25 * D, 0.26 * D, 90, -150); return cv
@U("4")
def _(s): C, D = s.C, s.D; w = 0.72 * C; cv = _cv(s, w); cv.line((0.7 * w, D), (0.02 * w, 0.3 * D)); cv.line((0, 0.3 * D), (w, 0.3 * D)); cv.stem(0.7 * w, 0, D); return cv
@U("5")
def _(s):
    C, D = s.C, s.D; w = 0.62 * C; cv = _cv(s, w); cv.line((0.12 * w, D), (0.95 * w, D)); cv.line((0.12 * w, D), (0.06 * w, 0.55 * D)); cv.arc(0.48 * w, 0.3 * D, 0.31 * D, 140, -130)
    cv.line((0.06 * w, 0.55 * D), (0.48 * w + 0.31 * D * math.cos(math.radians(140)), 0.3 * D + 0.31 * D * math.sin(math.radians(140)))); return cv
@U("6")
def _(s): C, D = s.C, s.D; w = 0.62 * C; cv = _cv(s, w); cv.curve((0.82 * w, D), (0.08 * w, 0.95 * D), (0.03 * w, 0.32 * D)); cv.arc(0.5 * w, 0.3 * D, 0.31 * D, 180, -180, ry=0.3 * D); return cv
@U("7")
def _(s): C, D = s.C, s.D; w = 0.62 * C; cv = _cv(s, w); cv.line((0.02 * w, D), (w, D)); cv.line((w, D), (0.3 * w, 0)); return cv
@U("8")
def _(s): C, D = s.C, s.D; w = 0.6 * C; cv = _cv(s, w); cv.arc(0.5 * w, 0.72 * D, 0.26 * D, 0, 360, ry=0.27 * D); cv.arc(0.5 * w, 0.29 * D, 0.3 * D, 0, 360, ry=0.29 * D); return cv
@U("9")
def _(s): C, D = s.C, s.D; w = 0.62 * C; cv = _cv(s, w); cv.curve((0.18 * w, 0), (0.92 * w, 0.05 * D), (0.97 * w, 0.68 * D)); cv.arc(0.5 * w, 0.7 * D, 0.31 * D, 0, 360, ry=0.3 * D); return cv

# ---- punctuation and symbols
@U(".")
def _(s): w = s.ST * 1.1; cv = _cv(s, w); cv.dot(w / 2, 0); return cv
@U(",")
def _(s): X = s.X; w = s.ST * 1.1; cv = _cv(s, w); cv.dot(w / 2, 0.05 * X); cv.line((w / 2, 0.05 * X), (0.3 * w, -0.3 * X), bow=0.1); return cv
@U(":")
def _(s): X = s.X; w = s.ST * 1.1; cv = _cv(s, w); cv.dot(w / 2, 0); cv.dot(w / 2, X - s.ST); return cv
@U(";")
def _(s): X = s.X; w = s.ST * 1.1; cv = _cv(s, w); cv.dot(w / 2, 0.05 * X); cv.line((w / 2, 0.05 * X), (0.3 * w, -0.3 * X), bow=0.1); cv.dot(w / 2, X - s.ST); return cv
@U("!")
def _(s): C = s.C; w = s.ST * 1.1; cv = _cv(s, w); cv.line((w / 2, C), (w / 2, 0.3 * C), bow=0.01); cv.dot(w / 2, 0); return cv
@U("?")
def _(s): C = s.C; w = 0.6 * C; cv = _cv(s, w); cv.arc(0.5 * w, 0.72 * C, 0.26 * C, 165, -90); cv.line((0.5 * w, 0.46 * C), (0.5 * w, 0.3 * C), bow=0); cv.dot(0.5 * w, 0); return cv
@U("'")
def _(s): C = s.C; w = s.ST; cv = _cv(s, w); cv.line((w / 2, C), (0.4 * w, 0.78 * C), bow=0.05); return cv
@U('"')
def _(s): C = s.C; w = 2.2 * s.ST; cv = _cv(s, w); cv.line((0.3 * w, C), (0.25 * w, 0.78 * C), bow=0.05); cv.line((0.75 * w, C), (0.7 * w, 0.78 * C), bow=0.05); return cv
@U("’")
def _(s): return RECIPES["'"](s)
@U("‘")
def _(s): C = s.C; w = s.ST; cv = _cv(s, w); cv.line((0.4 * w, C), (w / 2, 0.78 * C), bow=0.05); return cv
@U("“")
def _(s): C = s.C; w = 2.2 * s.ST; cv = _cv(s, w); cv.line((0.25 * w, C), (0.3 * w, 0.78 * C), bow=0.05); cv.line((0.7 * w, C), (0.75 * w, 0.78 * C), bow=0.05); return cv
@U("”")
def _(s): return RECIPES['"'](s)
@U("-")
def _(s): X = s.X; w = 0.5 * X; cv = _cv(s, w); cv.line((0, 0.45 * X), (w, 0.45 * X)); return cv
@U("–")
def _(s): X = s.X; w = 1.0 * X; cv = _cv(s, w); cv.line((0, 0.45 * X), (w, 0.45 * X)); return cv
@U("—")
def _(s): X = s.X; w = 1.7 * X; cv = _cv(s, w); cv.line((0, 0.45 * X), (w, 0.45 * X)); return cv
@U("(")
def _(s): C = s.C; w = 0.38 * C; cv = _cv(s, w); cv.curve((w, 1.05 * C), (-0.55 * w, 0.42 * C), (w, -0.22 * C)); return cv
@U(")")
def _(s): C = s.C; w = 0.38 * C; cv = _cv(s, w); cv.curve((0, 1.05 * C), (1.55 * w, 0.42 * C), (0, -0.22 * C)); return cv
@U("[")
def _(s): C = s.C; w = 0.36 * C; cv = _cv(s, w); cv.line((0.1 * w, 1.05 * C), (0.1 * w, -0.2 * C), bow=0); cv.line((0.1 * w, 1.05 * C), (w, 1.05 * C), bow=0); cv.line((0.1 * w, -0.2 * C), (w, -0.2 * C), bow=0); return cv
@U("]")
def _(s): C = s.C; w = 0.36 * C; cv = _cv(s, w); cv.line((0.9 * w, 1.05 * C), (0.9 * w, -0.2 * C), bow=0); cv.line((0, 1.05 * C), (0.9 * w, 1.05 * C), bow=0); cv.line((0, -0.2 * C), (0.9 * w, -0.2 * C), bow=0); return cv
@U("/")
def _(s): C = s.C; w = 0.5 * C; cv = _cv(s, w); cv.line((0, -0.15 * C), (w, 1.02 * C)); return cv
@U("\\")
def _(s): C = s.C; w = 0.5 * C; cv = _cv(s, w); cv.line((0, 1.02 * C), (w, -0.15 * C)); return cv
@U("+")
def _(s): C = s.C; w = 0.55 * C; cv = _cv(s, w); cv.line((0, 0.4 * C), (w, 0.4 * C)); cv.line((w / 2, 0.1 * C), (w / 2, 0.7 * C)); return cv
@U("=")
def _(s): C = s.C; w = 0.55 * C; cv = _cv(s, w); cv.line((0, 0.28 * C), (w, 0.28 * C)); cv.line((0, 0.52 * C), (w, 0.52 * C)); return cv
@U("*")
def _(s):
    C = s.C; w = 0.5 * C; cv = _cv(s, w); cy = 0.78 * C; r = 0.2 * C
    for a in (90, 18, 162, 234, 306): cv.line((w / 2, cy), (w / 2 + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))), bow=0)
    return cv
@U("#")
def _(s): C = s.C; w = 0.7 * C; cv = _cv(s, w); cv.line((0.3 * w, 0), (0.42 * w, C)); cv.line((0.62 * w, 0), (0.74 * w, C)); cv.line((0.05 * w, 0.64 * C), (w, 0.64 * C)); cv.line((0, 0.3 * C), (0.95 * w, 0.3 * C)); return cv
@U("%")
def _(s): C = s.C; w = 0.9 * C; cv = _cv(s, w); cv.line((0.05 * w, -0.05 * C), (0.95 * w, C)); cv.shape("o", 0, 0.58 * C, 0.36 * w, 0.42 * C); cv.shape("o", 0.64 * w, 0, 0.36 * w, 0.42 * C); return cv
@U("@")
def _(s): X = s.X; w = 1.2 * X; cv = _cv(s, w); cv.shape("o", 0.3 * w, 0.22 * X, 0.42 * w, 0.62 * X); cv.line((0.72 * w, 0.84 * X), (0.72 * w, 0.22 * X), bow=0); cv.arc(0.5 * w, 0.5 * X, 0.5 * w, -40, 270, ry=0.62 * X); return cv
@U("_")
def _(s): C = s.C; w = 0.7 * C; cv = _cv(s, w); cv.line((0, -0.12 * C), (w, -0.12 * C)); return cv
@U("|")
def _(s): C = s.C; w = s.ST; cv = _cv(s, w); cv.line((w / 2, 1.05 * C), (w / 2, -0.25 * C), bow=0); return cv
@U("<")
def _(s): C = s.C; w = 0.5 * C; cv = _cv(s, w); cv.line((w, 0.75 * C), (0, 0.42 * C)); cv.line((0, 0.42 * C), (w, 0.1 * C)); return cv
@U(">")
def _(s): C = s.C; w = 0.5 * C; cv = _cv(s, w); cv.line((0, 0.75 * C), (w, 0.42 * C)); cv.line((w, 0.42 * C), (0, 0.1 * C)); return cv
@U("^")
def _(s): C = s.C; w = 0.5 * C; cv = _cv(s, w); cv.shape("v", 0, 0.7 * C, w, 0.32 * C, flipy=True); return cv
@U("~")
def _(s): C = s.C; w = 0.6 * C; cv = _cv(s, w); cv.arc(0.25 * w, 0.42 * C, 0.25 * w, 180, 0, ry=0.1 * C); cv.arc(0.75 * w, 0.42 * C, 0.25 * w, 180, 360, ry=0.1 * C); return cv
@U("&")
def _(s): C = s.C; w = 0.7 * C; cv = _cv(s, w); cv.arc(0.45 * w, 0.74 * C, 0.24 * C, 60, 300); cv.arc(0.45 * w, 0.27 * C, 0.28 * C, 60, 330); cv.line((0.42 * w, 0.52 * C), (w, 0.02 * C)); return cv
@U("$")
def _(s): C = s.C; w = 0.62 * C; cv = _cv(s, w); cv.shape("s", 0.05 * w, 0.05 * C, 0.9 * w, 0.9 * C); cv.line((0.5 * w, 1.08 * C), (0.5 * w, -0.08 * C), bow=0); return cv
@U("€")
def _(s): C = s.C; w = 0.75 * C; cv = _cv(s, w); cv.shape("c", 0.1 * w, 0.05 * C, 0.8 * w, 0.9 * C); cv.line((0, 0.45 * C), (w * 0.8, 0.45 * C), bow=0); cv.line((0, 0.62 * C), (w * 0.8, 0.62 * C), bow=0); return cv
@U("₹")
def _(s):
    C = s.C; w = 0.7 * C; cv = _cv(s, w); cv.line((0.05 * w, C), (0.95 * w, C), bow=0); cv.line((0.05 * w, 0.76 * C), (0.95 * w, 0.76 * C), bow=0)
    cv.arc(0.4 * w, 0.76 * C, 0.5 * w, 90, -90, ry=0.24 * C); cv.line((0.05 * w, 0.52 * C), (0.4 * w, 0.52 * C), bow=0); cv.line((0.4 * w, 0.52 * C), (0.9 * w, 0), bow=0); return cv
@U("£")
def _(s): C = s.C; w = 0.65 * C; cv = _cv(s, w); cv.arc(0.6 * w, 0.75 * C, 0.3 * w, 0, 180, ry=0.22 * C); cv.line((0.3 * w, 0.75 * C), (0.3 * w, 0.05 * C), bow=0.01); cv.line((0.05 * w, 0), (w, 0)); cv.line((0.05 * w, 0.42 * C), (0.6 * w, 0.42 * C), bow=0); return cv

STANDARD = ("abcdefghijklmnopqrstuvwxyz" "ABCDEFGHIJKLMNOPQRSTUVWXYZ" "0123456789"
            ".,:;!?'\"’‘“”-–—()[]/\\+=*#%@_|<>^~&$€₹£")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", default="build")
    ap.add_argument("--chars", default=STANDARD, help="characters to compose (default: everything the recipes know)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    sel = load_json(os.path.join(a.build, "selected.json"))
    ink = load_ink(sel["image"])
    asc = float(np.median([m["asc"] for m in sel["metrics"].values()]))
    s = Synth(ink, sel["selected"], sel["body_xheight"], asc, a.build)
    glyphs = s.build(a.chars)
    print(f"pen radius {s.pen_r:.1f} canvas px; lifted pieces: {''.join(sorted(s.pieces))}; composed {len(glyphs)} glyphs")
    names = list(glyphs); cols = 13; cw = int(1.3 * s.C); chh = s.H + 10
    sheet = Image.new("L", (cols * cw, ((len(names) + cols - 1) // cols) * chh), 255)
    for i, n in enumerate(names):
        bm, bl, w = glyphs[n]
        sheet.paste(Image.fromarray((255 - bm * 255).astype(np.uint8)), ((i % cols) * cw, (i // cols) * chh))
    sheet = sheet.resize((sheet.width // 2, sheet.height // 2), Image.LANCZOS)
    out = a.out or os.path.join(a.build, "synth_sheet.png"); sheet.save(out); print("->", out)


if __name__ == "__main__":
    main()
