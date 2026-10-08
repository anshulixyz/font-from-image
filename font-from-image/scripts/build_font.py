"""Trace the chosen glyphs, compose whatever is missing, and write OTF / TTF / WOFF2.

Usage:
  build_font.py --build build --family "My Hand" [--style Regular] [--out fonts]
                [--embolden 0] [--xscale 1.0] [--bearing-factor 1.0] [--space 1.1]
                [--native] [--no-synth] [--synth-chars "..."]

Key choices, and why:
  * Each glyph is scaled so the line's x-height becomes --xheight-units (480 of 1000), and keeps
    its own vertical offset from the baseline - that is what makes the result look like the hand
    instead of a flattened copy of it.
  * Side bearings come from the gaps actually measured between neighbouring letters in the image,
    so the font spaces the way the lettering was spaced. --bearing-factor tightens or loosens.
  * --embolden N thickens strokes by N units per side (bitmap dilation before tracing) and
    --xscale K condenses; together they make a heavier style from the same glyphs when the
    source has no bold lettering. --native uses `selected_native` (see pick_glyphs.py
    --native-lines) as-is for the characters it contains, falling back to embolden/xscale.
  * Characters the image lacks are composed from its strokes (synth_glyphs.py) unless --no-synth.
"""
import argparse
import os
import sys
import numpy as np
from collections import defaultdict
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.reverseContourPen import ReverseContourPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.areaPen import AreaPen
from fontTools.agl import UV2AGL
from common import load_ink, load_json, glyph_gray, upscale_bitmap, trace_bitmap, embolden, UP
from synth_glyphs import Synth, STANDARD


def gname(ch):
    return UV2AGL.get(ord(ch), f"uni{ord(ch):04X}")


def draw(contours, pen):
    for c in contours:
        for kind, v in c:
            if kind == "move": pen.moveTo(v)
            elif kind == "line": pen.lineTo(v)
            else: pen.curveTo(*v)
        pen.closePath()


def bounds(contours):
    if not contours:
        return None
    bp = BoundsPen(None); draw(contours, bp); return bp.bounds


def transform(contours, k=1.0, dx=0.0, dy=0.0):
    out = []
    for c in contours:
        cc = []
        for kind, v in c:
            if kind == "curve": cc.append((kind, tuple((x * k + dx, y + dy) for x, y in v)))
            else: cc.append((kind, (v[0] * k + dx, v[1] + dy)))
        out.append(cc)
    return out


def fix_direction(contours, want_positive):
    """Outer contour counter-clockwise for CFF, clockwise for TrueType."""
    if not contours:
        return contours
    def area(c):
        ap = AreaPen(None); draw([c], ap); return ap.value
    outer = max(contours, key=lambda c: abs(area(c)))
    if (area(outer) > 0) == want_positive:
        return contours
    out = []
    for c in contours:
        class Rec:
            def __init__(s): s.ops = []
            def moveTo(s, p): s.ops.append(("move", p))
            def lineTo(s, p): s.ops.append(("line", p))
            def curveTo(s, *p): s.ops.append(("curve", tuple(p)))
            def closePath(s): pass
            def endPath(s): pass
        r = Rec(); draw([c], ReverseContourPen(r)); out.append(r.ops)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", default="build")
    ap.add_argument("--family", required=True)
    ap.add_argument("--style", default="Regular")
    ap.add_argument("--out", default="fonts")
    ap.add_argument("--xheight-units", type=int, default=480)
    ap.add_argument("--embolden", type=float, default=0.0, help="font units per side added to every stroke")
    ap.add_argument("--xscale", type=float, default=1.0, help="horizontal scale (0.84 = condensed)")
    ap.add_argument("--bearing-factor", type=float, default=1.0)
    ap.add_argument("--space", type=float, default=0.0, help="space width in x-heights (default: measured word gap)")
    ap.add_argument("--native", action="store_true", help="use selected_native glyphs as-is where available")
    ap.add_argument("--no-synth", action="store_true")
    ap.add_argument("--synth-chars", default=STANDARD, help="which characters to compose if missing")
    ap.add_argument("--version", default="1.000")
    ap.add_argument("--copyright", default="")
    ap.add_argument("--license", default="This Font Software is licensed under the SIL Open Font License, Version 1.1.")
    a = ap.parse_args()

    sel = load_json(os.path.join(a.build, "selected.json"))
    S, S0, metrics = sel["selected"], sel.get("selected_native", {}), sel["metrics"]
    ink = load_ink(sel["image"])
    XH = a.xheight_units
    body_xh = sel["body_xheight"]
    body_scale = XH / body_xh
    glyph_data = load_json(os.path.join(a.build, "glyphs.json"))["glyphs"]

    # ---------- side bearings from measured gaps (per character, in image px, body lines only)
    def gap_tables(lines_pred):
        lg, rg = defaultdict(list), defaultdict(list)
        for g in glyph_data:
            if not lines_pred(g["line"]): continue
            if g["lgap"] is not None: lg[g["char"]].append(g["lgap"])
            if g["rgap"] is not None: rg[g["char"]].append(g["rgap"])
        allg = [v for vs in lg.values() for v in vs]
        return lg, rg, (float(np.median(allg)) if allg else 0.1 * body_xh)
    native_lines = {S0[c]["line"] for c in S0}
    lg, rg, gap_med = gap_tables(lambda li: li not in native_lines)
    lg0, rg0, gap0 = gap_tables(lambda li: li in native_lines) if native_lines else (lg, rg, gap_med)

    def bearings(ch, scale, tables):
        l, r, med = tables
        lv = (np.median(l[ch]) if l[ch] else med) * a.bearing_factor
        rv = (np.median(r[ch]) if r[ch] else med) * a.bearing_factor
        return max(0.0, lv / 2) * scale, max(0.0, rv / 2) * scale

    wg = [g / h for li, g, h in sel["word_gaps"] if li not in native_lines]
    word_gap_px = float(np.median([g for li, g, h in sel["word_gaps"] if li not in native_lines])) if wg else body_xh * 1.1
    space_units = (a.space * XH) if a.space else word_gap_px * body_scale

    # ---------- tracing
    glyphs = {}          # name -> (contours, advance)
    def add(name, contours, lsb, rsb, k=1.0):
        contours = transform(contours, k=k)
        b = bounds(contours)
        if b is None:
            return
        contours = transform(contours, dx=-b[0] + lsb * k)
        glyphs[name] = (contours, (b[2] - b[0]) + (lsb + rsb) * k)

    def trace_glyph(g, scale, emb_units):
        gray = glyph_gray(ink, g, a.build)
        bm, pad = upscale_bitmap(gray)
        bm = embolden(bm, emb_units / (scale / UP))
        base, y0, x0 = g["baseline"], g["y0"], g["x0"]
        return trace_bitmap(bm, lambda px, py: ((px / UP - pad) * scale, (base - (py / UP - pad + y0)) * scale))

    scale_of = lambda g: XH / g["xheight"]
    native_used = []
    for ch, g in S.items():
        if a.native and ch in S0:
            g0 = S0[ch]; sc = scale_of(g0)
            add(gname(ch), trace_glyph(g0, sc, 0.0), *bearings(ch, sc, (lg0, rg0, gap0)))
            native_used.append(ch); continue
        sc = scale_of(g)
        add(gname(ch), trace_glyph(g, sc, a.embolden), *bearings(ch, sc, (lg, rg, gap_med)), k=a.xscale)
    if a.native:
        for ch, g0 in S0.items():
            if ch not in S:
                sc = scale_of(g0)
                add(gname(ch), trace_glyph(g0, sc, 0.0), *bearings(ch, sc, (lg0, rg0, gap0))); native_used.append(ch)
    print(f"traced {len(glyphs)} glyphs from the image" + (f" ({len(native_used)} native-style)" if native_used else ""))

    # ---------- composed glyphs for everything the image lacks
    composed = []
    if not a.no_synth:
        missing = [c for c in a.synth_chars if c not in S and gname(c) not in glyphs]
        asc_px = float(np.median([m["asc"] for m in metrics.values()]))
        syn = Synth(ink, S, body_xh, asc_px, a.build)
        for ch, (bm, bl, wpx) in syn.build(missing).items():
            bm = embolden(bm, a.embolden / (body_scale / UP))
            cont = trace_bitmap(bm, lambda px, py: (px / UP * body_scale, (bl - py) / UP * body_scale))
            sb = (1.5 if ch.isupper() or not ch.isalnum() else 1.2) * a.bearing_factor * body_scale
            add(gname(ch), cont, sb, sb, k=a.xscale); composed.append(ch)
        print(f"composed {len(composed)} missing glyphs: {''.join(composed)}")
    glyphs["space"] = ([], space_units)
    glyphs[".notdef"] = ([[("move", (50, 0)), ("line", (50, 700)), ("line", (350, 700)), ("line", (350, 0))],
                          [("move", (90, 40)), ("line", (310, 40)), ("line", (310, 660)), ("line", (90, 660))]], 400)

    # ---------- cmap, metrics
    order = [".notdef", "space"] + sorted(n for n in glyphs if n not in (".notdef", "space"))
    cmap = {0x20: "space", 0xA0: "space"}
    for ch in list(S) + list(S0) + composed:
        if gname(ch) in glyphs:
            cmap[ord(ch)] = gname(ch)
    tops = [bounds(glyphs[gname(c)][0])[3] for c in "ldhbkt" if gname(c) in glyphs] or [bounds(v[0])[3] for v in glyphs.values() if v[0]]
    bots = [bounds(glyphs[gname(c)][0])[1] for c in "gjpqy" if gname(c) in glyphs] or [bounds(v[0])[1] for v in glyphs.values() if v[0]]
    asc = int(round(max(tops) * 1.08)); desc = int(round(min(min(bots), -0.2 * XH) * 1.1))
    bold = a.style.lower().startswith("bold")
    ps = a.family.replace(" ", "") + "-" + a.style.replace(" ", "")

    def build(flavor):
        fb = FontBuilder(1000, isTTF=(flavor == "ttf"))
        fb.setupGlyphOrder(order); fb.setupCharacterMap(cmap)
        adv = {n: int(round(glyphs[n][1])) for n in order}
        if flavor == "ttf":
            pg = {}
            for n in order:
                tp = TTGlyphPen(None); draw(fix_direction(glyphs[n][0], False), Cu2QuPen(tp, 1.0, reverse_direction=False)); pg[n] = tp.glyph()
            fb.setupGlyf(pg)
            fb.setupHorizontalMetrics({n: (adv[n], getattr(pg[n], "xMin", 0)) for n in order})
        else:
            cs = {}
            for n in order:
                p = T2CharStringPen(adv[n], None); draw(fix_direction(glyphs[n][0], True), p); cs[n] = p.getCharString()
            fb.setupCFF(ps, {"FullName": f"{a.family} {a.style}", "FamilyName": a.family, "Weight": a.style}, cs, {})
            fb.setupHorizontalMetrics({n: (adv[n], int(round(bounds(glyphs[n][0])[0])) if glyphs[n][0] else 0) for n in order})
        fb.setupHorizontalHeader(ascent=asc, descent=desc, lineGap=0)
        fb.setupNameTable({"familyName": a.family, "styleName": a.style, "uniqueFontIdentifier": f"{a.family} {a.style} {a.version}",
                           "fullName": f"{a.family} {a.style}", "psName": ps, "version": f"Version {a.version}",
                           "description": "Built with the font-from-image skill: glyphs traced from a lettering image, missing characters composed from its strokes.",
                           "copyright": a.copyright, "licenseDescription": a.license})
        fb.setupOS2(sTypoAscender=asc, sTypoDescender=desc, sTypoLineGap=0, usWinAscent=asc, usWinDescent=-desc, sxHeight=XH,
                    sCapHeight=int(max(tops)), fsSelection=(0x20 if bold else 0x40) | 0x80, fsType=0, usWeightClass=700 if bold else 400)
        fb.setupPost(isFixedPitch=0)
        if bold: fb.font["head"].macStyle |= 1
        return fb.font

    os.makedirs(a.out, exist_ok=True)
    build("otf").save(os.path.join(a.out, f"{ps}.otf"))
    build("ttf").save(os.path.join(a.out, f"{ps}.ttf"))
    w = build("ttf"); w.flavor = "woff2"; w.save(os.path.join(a.out, f"{ps}.woff2"))
    print(f"{len(order)} glyphs; ascender {asc}, descender {desc}, space {space_units:.0f} -> {a.out}/{ps}.{{otf,ttf,woff2}}")


if __name__ == "__main__":
    main()
