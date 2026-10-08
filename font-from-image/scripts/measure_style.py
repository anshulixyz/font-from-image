"""Measure the typography of the lettering so it can be reproduced in any tool.

Usage:
  measure_style.py --build build --image original.jpg [--design-width 1080] [--out build/style]
                   [--matched-font path.ttf --matched-name "Caveat"]

Reads the segmentation (build/glyphs.json, build/selected.json) and the original image and
writes style.json plus STYLE.md with:
  - size: x-height, cap height and font size in px of the image, as % of image width, and at
    a chosen design width (default 1080 px, an Instagram post)
  - line height (baseline pitch / font size), letter spacing and word spacing in em
  - alignment and margins of the text block, ink and paper colours, slant, stroke weight
  - the same numbers translated for CSS, Figma, Canva, Google Docs / Word
  - per text style when the image has more than one size (heading / body)

--matched-font: when an existing font was identified, give its file so the settings are
re-expressed for that font (its x-height differs, so the point size and tracking change).
"""
import argparse
import json
import math
import os
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from collections import defaultdict
from common import load_json, load_ink, THR


def hexcol(rgb):
    return "#%02x%02x%02x" % tuple(int(round(v)) for v in rgb)


def colours(image_path):
    im = Image.open(image_path).convert("RGB")
    arr = np.asarray(im).astype(np.float32)
    lum = arr.mean(2)
    bg = ndi.gaussian_filter(ndi.median_filter(lum, size=15), 8)
    dark = np.clip(1 - lum / np.maximum(bg, 1), 0, 1)
    ink_mask = dark > max(0.25, np.percentile(dark, 97) * 0.6)
    paper_mask = dark < 0.05
    ink = np.median(arr[ink_mask], axis=0) if ink_mask.sum() > 50 else np.array([0, 0, 0])
    paper = np.median(arr[paper_mask], axis=0) if paper_mask.sum() > 50 else np.array([255, 255, 255])
    return hexcol(ink), hexcol(paper)


def slant_deg(ink, glyphs, chars="lIi|1"):
    angles = []
    for g in glyphs:
        if g["char"] not in chars:
            continue
        m = ink[g["y0"]:g["y1"], g["x0"]:g["x1"]] > THR
        m = m[: int(m.shape[0] * 0.65)]             # the stem only: skip the foot/curl at the bottom
        ys, xs = np.where(m)
        if len(xs) < 20:
            continue
        # principal axis of the stem
        cov = np.cov(np.vstack([xs, ys]))
        w, v = np.linalg.eigh(cov)
        vx, vy = v[:, np.argmax(w)]
        if vy < 0: vx, vy = -vx, -vy                 # point the axis downwards (image y grows down)
        ang = -math.degrees(math.atan2(vx, vy))     # 0 = vertical, positive = leaning right
        if abs(ang) < 45:
            angles.append(ang)
    return float(np.median(angles)) if angles else 0.0


def stroke_ratio(ink, glyphs, xh):
    """stroke width / x-height from the distance transform of a few round letters."""
    vals = []
    for g in glyphs:
        if g["char"] not in "oeacsnu":
            continue
        m = ink[g["y0"]:g["y1"], g["x0"]:g["x1"]] > THR
        if m.sum() < 20:
            continue
        dt = ndi.distance_transform_edt(m)
        vals.append(2 * dt[m].max())
        if len(vals) > 40:
            break
    return float(np.median(vals)) / xh if vals else 0.0


def font_xheight_ratio(path):
    from fontTools.ttLib import TTFont
    f = TTFont(path)
    upm = f["head"].unitsPerEm
    os2 = f["OS/2"]
    if getattr(os2, "sxHeight", 0):
        return os2.sxHeight / upm
    gs = f.getGlyphSet()
    from fontTools.pens.boundsPen import BoundsPen
    bp = BoundsPen(gs); gs["x"].draw(bp)
    return bp.bounds[3] / upm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", default="build")
    ap.add_argument("--image", required=True, help="the original image (for colours and dimensions)")
    ap.add_argument("--design-width", type=int, default=1080)
    ap.add_argument("--xheight-units", type=int, default=480, help="x-height of the built font, per 1000 em")
    ap.add_argument("--matched-font", default=None)
    ap.add_argument("--matched-name", default="matched font")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    sel = load_json(os.path.join(a.build, "selected.json"))
    data = load_json(os.path.join(a.build, "glyphs.json"))
    ink = load_ink(sel["image"])
    H, W = ink.shape
    src_w, src_h = Image.open(a.image).size
    k_img = src_w / W                                   # prepared -> original px
    metrics = {int(k): v for k, v in sel["metrics"].items()}
    glyphs = data["glyphs"]
    by_line = defaultdict(list)
    for g in glyphs:
        by_line[g["line"]].append(g)

    # ---- group lines by size (body vs headings)
    groups = defaultdict(list)
    for li, m in metrics.items():
        groups[round(m["group_xheight"], 1)].append(li)
    ink_hex, paper_hex = colours(a.image)
    custom_xh_ratio = a.xheight_units / 1000
    matched_xh_ratio = font_xheight_ratio(a.matched_font) if a.matched_font else None

    styles = []
    for xh, lines in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        lines = sorted(lines)
        gs = [g for li in lines for g in by_line[li]]
        if not gs:
            continue
        xh_px = xh * k_img
        asc_px = float(np.median([metrics[li]["asc"] for li in lines])) * k_img
        baselines = sorted(metrics[li]["baseline"] * k_img for li in lines)
        pitch = float(np.median(np.diff(baselines))) if len(baselines) > 1 else None
        gaps = [g["lgap"] for g in gs if g["lgap"] is not None]
        letter_gap = float(np.median(gaps)) * k_img if gaps else 0.0
        wgs = [wg * k_img for li, wg, h in sel["word_gaps"] if li in lines]
        word_gap = float(np.median(wgs)) if wgs else xh_px * 1.1
        lefts = [min(g["x0"] for g in by_line[li]) * k_img for li in lines]
        rights = [max(g["x1"] for g in by_line[li]) * k_img for li in lines]
        centers = [(l + r) / 2 for l, r in zip(lefts, rights)]
        spread = {"left": np.std(lefts), "right": np.std(rights), "center": np.std(centers)}
        align = min(spread, key=spread.get) if len(lines) > 1 else "left"
        top = min(metrics[li]["baseline"] - metrics[li]["asc"] for li in lines) * k_img
        bottom = max(metrics[li]["baseline"] + 0.45 * metrics[li]["xheight"] for li in lines) * k_img
        slant = slant_deg(ink, gs)
        sw = stroke_ratio(ink, gs, xh)

        def for_font(xh_ratio):
            size = xh_px / xh_ratio
            return dict(font_size_px=round(size, 1),
                        font_size_at_design_width=round(size * a.design_width / src_w, 1),
                        line_height=round(pitch / size, 2) if pitch else None,
                        letter_spacing_em=round(letter_gap / size, 3),
                        word_spacing_em=round(word_gap / size, 2))
        style = dict(
            name="body" if not styles else f"style{len(styles) + 1}",
            lines=lines,
            x_height_px=round(xh_px, 1), cap_height_px=round(asc_px, 1),
            x_height_pct_of_width=round(100 * xh_px / src_w, 2),
            baseline_pitch_px=round(pitch, 1) if pitch else None,
            letter_gap_px=round(letter_gap, 2), word_gap_px=round(word_gap, 1),
            alignment=align,
            margins_pct=dict(left=round(100 * min(lefts) / src_w, 1), right=round(100 * (1 - max(rights) / src_w), 1),
                             top=round(100 * top / src_h, 1), bottom=round(100 * (1 - bottom / src_h), 1)),
            text_width_pct=round(100 * (max(rights) - min(lefts)) / src_w, 1),
            slant_deg=round(slant, 1),
            stroke_to_xheight=round(sw, 3),
            weight_hint="bold" if sw > 0.36 else ("medium" if sw > 0.26 else "regular"),
            custom_font=for_font(custom_xh_ratio),
        )
        if matched_xh_ratio:
            style["matched_font"] = for_font(matched_xh_ratio)
        styles.append(style)
    # name the biggest non-body group "heading"
    if len(styles) > 1:
        big = max(styles[1:], key=lambda s: s["x_height_px"])
        big["name"] = "heading"

    result = dict(image=os.path.abspath(a.image), image_size=[src_w, src_h], design_width=a.design_width,
                  colours=dict(ink=ink_hex, paper=paper_hex), styles=styles,
                  matched_font=a.matched_name if a.matched_font else None)
    out_dir = a.out or os.path.join(a.build, "style")
    os.makedirs(out_dir, exist_ok=True)
    json.dump(result, open(os.path.join(out_dir, "style.json"), "w"), indent=1)

    # ---- STYLE.md
    L = []
    L.append("# Typography of the source image\n")
    L.append(f"Image {src_w}x{src_h} px. Ink `{ink_hex}`, paper `{paper_hex}`. Values below are measured from the lettering; "
             f"'at design width' assumes a {a.design_width} px wide design (Instagram post size).\n")
    for st in styles:
        cf = st["custom_font"]
        L.append(f"## {st['name']} (lines {st['lines'][0]}-{st['lines'][-1]})\n")
        L.append("| measured | value |\n|---|---|")
        L.append(f"| x-height / cap height | {st['x_height_px']} px / {st['cap_height_px']} px ({st['x_height_pct_of_width']}% of image width) |")
        L.append(f"| baseline to baseline | {st['baseline_pitch_px'] or '-'} px |")
        L.append(f"| gap between letters / words | {st['letter_gap_px']} px / {st['word_gap_px']} px |")
        L.append(f"| alignment, text width | {st['alignment']}, {st['text_width_pct']}% of width |")
        m = st["margins_pct"]
        L.append(f"| margins (l / r / t / b) | {m['left']}% / {m['right']}% / {m['top']}% / {m['bottom']}% |")
        L.append(f"| slant | {st['slant_deg']} deg |")
        L.append(f"| stroke / x-height | {st['stroke_to_xheight']} -> {st['weight_hint']} |\n")
        fonts = [("the built font", cf)] + ([(a.matched_name, st["matched_font"])] if "matched_font" in st else [])
        for label, f in fonts:
            L.append(f"### Settings with {label}\n")
            ls_pct = round(100 * f["letter_spacing_em"], 1)
            lh = f["line_height"] or 1.3
            baked = label == "the built font"
            L.append("| tool | font size | line height | letter spacing | word spacing |\n|---|---|---|---|---|")
            L.append(f"| CSS | `font-size: {f['font_size_at_design_width']}px` (at {a.design_width}px) | `line-height: {lh}` | "
                     f"`letter-spacing: {'0' if baked else str(f['letter_spacing_em']) + 'em'}` | `word-spacing: {'0' if baked else str(round(f['word_spacing_em'] - 0.25, 2)) + 'em'}` |")
            L.append(f"| Figma | {f['font_size_at_design_width']} | {round(lh * 100)}% | {'0%' if baked else str(ls_pct) + '%'} | - |")
            L.append(f"| Canva | ~{round(f['font_size_at_design_width'] * 0.75)} (design {a.design_width}px wide; Canva sizes are ~1.33 px per unit, check against the specimen) | line spacing {lh} | "
                     f"letter spacing {'0' if baked else str(round(ls_pct * 10)) + ' (approx.; slider is ~1/1000 em, nudge to match)'} | - |")
            L.append(f"| Google Docs / Word | {round(f['font_size_px'] * 72 / 96)} pt (for a {round(src_w / 96, 1)} in wide page) | line spacing {lh} | "
                     f"{'0' if baked else str(round(f['letter_spacing_em'] * f['font_size_px'] * 72 / 96, 1)) + ' pt'} | - |\n")
            if baked:
                L.append("The built font already carries the measured letter and word spacing in its glyphs, so tracking stays at 0 in every tool.\n")
            else:
                L.append(f"{label} has its own x-height, so its point size differs from the built font's for the same visual size; "
                         "the tracking above is the measured gap as a starting point - nudge while comparing with the image.\n")
    L.append("## Colour\n")
    L.append(f"Text `{ink_hex}` on `{paper_hex}`. In CSS: `color: {ink_hex}; background: {paper_hex};`. Paste the hex values into Canva's colour picker.\n")
    L.append("## How to choose\n")
    L.append("Use the built font when the exact hand matters (it is the lettering itself). Use the matched free font when you need "
             "a full professional character set, kerning, or an easy install in Canva/Docs; apply the settings in its table to get the same look.\n")
    open(os.path.join(out_dir, "STYLE.md"), "w").write("\n".join(L))
    print(f"{len(styles)} text style(s); ink {ink_hex} on {paper_hex}")
    for st in styles:
        cf = st["custom_font"]
        print(f"  {st['name']}: x-height {st['x_height_px']}px, font-size {cf['font_size_px']}px, line-height {cf['line_height']}, "
              f"letter gap {cf['letter_spacing_em']}em, word gap {cf['word_spacing_em']}em, {st['alignment']}, slant {st['slant_deg']} deg, {st['weight_hint']}")
    print("->", os.path.join(out_dir, "STYLE.md"), "and style.json")


if __name__ == "__main__":
    main()
