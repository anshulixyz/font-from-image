"""Choose one instance of each character and measure each line's baseline and x-height.

Usage: pick_glyphs.py --build build [--native-lines 0,1] [--exclude-lines 20]

For every character the "medoid" instance is chosen: the one most similar to all the others,
which is the most typical shape and rejects damaged or mis-segmented instances. The per-line
baseline and x-height let build_font.py keep each letter's own vertical offset (the natural
bounce of the hand) while putting every line on a common scale.

--native-lines marks lines whose glyphs should be used as-is for a second style (for instance a
bold heading): they are stored separately as `selected_native` and excluded from the regular pick.
--exclude-lines drops lines entirely (a signature, a different hand).

Writes <build>/selected.json and <build>/selected_sheet.png (look at the sheet!).
"""
import argparse
import os
import numpy as np
from PIL import Image
from collections import defaultdict
from common import load_ink, load_json, save_json, THR

DESCENDERS = set("gjpqy,;()[]{}@")
XHEIGHT_CHARS = set("aceimnorsuvwxz")
TALL_CHARS = set("bdfhklt0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def crop_feature(ink, g, s=48):
    m = ink[g["y0"]:g["y1"], g["x0"]:g["x1"]] > THR
    img = Image.fromarray((m * 255).astype(np.uint8)).resize((s, s), Image.BILINEAR)
    return np.asarray(img).astype(np.float32) / 255


def medoid(ink, gs):
    if len(gs) <= 2:
        return 0
    feats = [crop_feature(ink, g) for g in gs]
    n = len(gs); D = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            D[i, j] = D[j, i] = np.abs(feats[i] - feats[j]).mean()
    return int(np.argmin(D.sum(1)))


def line_metrics(gs):
    """baseline (row), x-height and ascender height (px) for one line from its matched glyphs."""
    base_src = [g["y1"] for g in gs if g["char"] not in DESCENDERS and g["char"].isalnum()]
    if not base_src:
        base_src = [g["y1"] for g in gs]
    base = float(np.median(base_src))
    xs = [base - g["y0"] for g in gs if g["char"] in XHEIGHT_CHARS]
    tall = [base - g["y0"] for g in gs if g["char"] in TALL_CHARS]
    if xs:
        xh = float(np.median(xs))
    elif tall:
        xh = 0.68 * float(np.median(tall))          # no lowercase on this line: estimate from cap height
    else:
        xh = float(np.median([g["y1"] - g["y0"] for g in gs]))
    asc = float(np.median(tall)) if tall else xh * 1.5
    return dict(baseline=base, xheight=xh, asc=asc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", default="build")
    ap.add_argument("--native-lines", default="", help="comma-separated line numbers kept as a separate style source")
    ap.add_argument("--exclude-lines", default="", help="comma-separated line numbers to ignore")
    a = ap.parse_args()
    native = {int(x) for x in a.native_lines.split(",") if x.strip()}
    exclude = {int(x) for x in a.exclude_lines.split(",") if x.strip()}

    data = load_json(os.path.join(a.build, "glyphs.json"))
    ink = load_ink(data["image"])
    G = [g for g in data["glyphs"] if g["line"] not in exclude]
    by_line = defaultdict(list)
    for g in G:
        by_line[g["line"]].append(g)
    metrics = {li: line_metrics(gs) for li, gs in by_line.items()}

    # size groups: lines whose x-height is within 15% of the median share one scale (the "body");
    # others (headings) keep their own
    body_lines = [li for li in metrics if li not in native]
    med_xh = float(np.median([metrics[li]["xheight"] for li in body_lines])) if body_lines else 1.0
    for li, m in metrics.items():
        m["group_xheight"] = med_xh if abs(m["xheight"] - med_xh) <= 0.15 * med_xh else m["xheight"]

    def pick(lines_filter):
        by = defaultdict(list)
        for g in G:
            if lines_filter(g["line"]):
                by[g["char"]].append(g)
        sel = {}
        for ch, gs in by.items():
            g = gs[medoid(ink, gs)]
            m = metrics[g["line"]]
            sel[ch] = dict(g, baseline=m["baseline"], xheight=m["group_xheight"], n=len(gs))
        return sel

    selected = pick(lambda li: li not in native)
    selected_native = pick(lambda li: li in native) if native else {}
    print("line metrics (baseline / x-height / ascender px):")
    for li in sorted(metrics):
        m = metrics[li]
        print(f"  {li:2d}: {m['baseline']:.0f} / {m['xheight']:.1f} / {m['asc']:.1f}" + ("  [native]" if li in native else ""))
    print("picked:", " ".join(f"{c}:{v['n']}" for c, v in sorted(selected.items())))
    if selected_native:
        print("native style glyphs:", "".join(sorted(selected_native)))
    save_json(dict(selected=selected, selected_native=selected_native, metrics={str(k): v for k, v in metrics.items()},
                   body_xheight=med_xh, image=data["image"], lines=data["lines"], bands=data["bands"],
                   word_gaps=data["word_gaps"]), os.path.join(a.build, "selected.json"))

    # contact sheet of the chosen glyphs
    chars = sorted(selected)
    cell = 90
    sheet = Image.new("L", (cell * 12, cell * ((len(chars) + 11) // 12) + 10), 255)
    for i, ch in enumerate(chars):
        g = selected[ch]
        tile = ink[max(0, g["y0"] - 2):g["y1"] + 2, max(0, g["x0"] - 2):g["x1"] + 2]
        t = Image.fromarray((255 - tile * 255).astype(np.uint8))
        k = min(3.0, (cell - 10) / max(t.height, t.width, 1))
        t = t.resize((max(1, int(t.width * k)), max(1, int(t.height * k))), Image.NEAREST)
        sheet.paste(t, ((i % 12) * cell + 5, (i // 12) * cell + 5))
    sheet.save(os.path.join(a.build, "selected_sheet.png"))
    print("->", os.path.join(a.build, "selected.json"), "and selected_sheet.png")


if __name__ == "__main__":
    main()
