"""Split a prepared lettering image into lines, words and letters, matched to a transcript.

Usage:
  segment.py --image build/prepared.png --transcript transcript.txt --out build [--split-touching]

transcript.txt has exactly one line of text per line of lettering in the image, top to bottom,
with the same spelling and punctuation. Spaces separate words; everything else is a character
that gets its own glyph.

What happens:
  1. lines   - horizontal ink projection; thin bands (dots, accents) are merged into the line below
  2. words   - connected components grouped by gap size, matched to the transcript's words
  3. letters - one component per character. Components stacked vertically (i-dots) are merged.
               A word whose component count differs from its letter count is skipped (there are
               usually other instances of each letter); with --split-touching, merged letters are
               cut apart at the thinnest column near the boundary predicted from letter widths
               measured elsewhere in the image.

The report printed at the end lists every line and the words that could not be matched. If the
line count differs from the transcript, nothing is written: fix the transcript (or re-run prep.py)
first. Output: <out>/glyphs.json and <out>/masks/<id>.png.
"""
import argparse
import os
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from collections import defaultdict
from common import load_ink, read_transcript, save_json, THR


def find_lines(ink, thr=THR):
    rows = (ink > thr).sum(1)
    # a row counts as text if it has more than a tiny amount of ink
    on = rows > max(2, 0.002 * ink.shape[1])
    bands = []
    inl = False
    for y, v in enumerate(on):
        if v and not inl:
            s = y; inl = True
        elif not v and inl:
            bands.append([s, y]); inl = False
    if inl:
        bands.append([s, len(on)])
    if not bands:
        return []
    med_h = np.median([e - s for s, e in bands])
    # merge slivers (dots, accents, descender tips) into the nearest real band
    merged = []
    for b in bands:
        if merged and (b[1] - b[0]) < 0.35 * med_h and (b[0] - merged[-1][1]) < 0.6 * med_h:
            merged[-1][1] = b[1]
        else:
            merged.append(b)
    out = []
    for b in merged:
        if out and (b[1] - b[0]) < 0.35 * med_h and (b[0] - out[-1][1]) < 0.6 * med_h:
            out[-1][1] = b[1]
        else:
            out.append(b)
    # a sliver above a tall band (i-dots above a line) belongs to the band below it
    final = []
    i = 0
    while i < len(out):
        b = out[i]
        if (b[1] - b[0]) < 0.35 * med_h and i + 1 < len(out) and (out[i + 1][0] - b[1]) < 0.6 * med_h:
            out[i + 1][0] = b[0]; i += 1; continue
        final.append(b); i += 1
    # slivers that found nothing to merge with (image edges, stray marks) are not lines
    final = [b for b in final if (b[1] - b[0]) >= 0.35 * med_h]
    return [(int(s), int(e)) for s, e in final]


def components(sub, y_off):
    lab, n = ndi.label(sub, structure=np.ones((3, 3)))
    comps = []
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        ys, xs = sl
        mask = lab[sl] == i
        comps.append(dict(x0=xs.start, x1=xs.stop, y0=ys.start + y_off, y1=ys.stop + y_off, mask=mask, area=int(mask.sum())))
    return comps


def merge_vertical(comps, max_gap):
    """Merge components stacked vertically (i-dots, broken strokes) whose x-ranges overlap strongly."""
    comps = sorted(comps, key=lambda c: c["x0"])
    merged = []
    for c in comps:
        for m in merged:
            ov = min(c["x1"], m["x1"]) - max(c["x0"], m["x0"])
            vgap = max(c["y0"], m["y0"]) - min(c["y1"], m["y1"])
            if ov > 0 and ov >= 0.5 * min(c["x1"] - c["x0"], m["x1"] - m["x0"]) and vgap <= max_gap:
                x0, x1 = min(c["x0"], m["x0"]), max(c["x1"], m["x1"])
                y0, y1 = min(c["y0"], m["y0"]), max(c["y1"], m["y1"])
                mk = np.zeros((y1 - y0, x1 - x0), bool)
                mk[m["y0"] - y0:m["y1"] - y0, m["x0"] - x0:m["x1"] - x0] |= m["mask"]
                mk[c["y0"] - y0:c["y1"] - y0, c["x0"] - x0:c["x1"] - x0] |= c["mask"]
                m.update(x0=x0, x1=x1, y0=y0, y1=y1, mask=mk, area=int(mk.sum()))
                break
        else:
            merged.append(c)
    return sorted(merged, key=lambda c: c["x0"])


def split_touching(comps, text, exp_w):
    """Cut merged components so there is one per character of `text`, guided by expected widths."""
    comps = list(comps)
    span = comps[-1]["x1"] - comps[0]["x0"]
    tot = sum(exp_w[c] for c in text) or 1.0
    k = span / tot
    centers, x = [], comps[0]["x0"]
    for c in text:
        centers.append(x + exp_w[c] * k / 2); x += exp_w[c] * k
    assign = [[] for _ in comps]
    for i, cx in enumerate(centers):
        j = min(range(len(comps)), key=lambda j: 0 if comps[j]["x0"] <= cx < comps[j]["x1"]
                else min(abs(cx - comps[j]["x0"]), abs(cx - comps[j]["x1"])))
        assign[j].append(i)
    out = []
    for c, idx in zip(comps, assign):
        if len(idx) <= 1:
            out.append(c); continue
        m = c["mask"]; w = m.shape[1]; prof = m.sum(0).astype(float)
        ws = [exp_w[text[i]] for i in idx]; frac = np.cumsum(ws)[:-1] / sum(ws)
        cuts = []
        for f, cw in zip(frac, ws):
            pred = int(f * w); r = max(2, int(0.15 * cw * k))
            lo, hi = max(1, pred - r), min(w - 1, pred + r)
            if hi <= lo:
                cuts.append(pred); continue
            cost = prof[lo:hi] + 0.5 * np.abs(np.arange(lo, hi) - pred)
            cuts.append(lo + int(np.argmin(cost)))
        edges = [0] + sorted(cuts) + [w]
        for a_, b_ in zip(edges[:-1], edges[1:]):
            sub = m[:, a_:b_]; ys, xs = np.where(sub)
            if len(xs) == 0:
                continue
            out.append(dict(x0=c["x0"] + a_ + xs.min(), x1=c["x0"] + a_ + xs.max() + 1,
                            y0=c["y0"] + ys.min(), y1=c["y0"] + ys.max() + 1,
                            mask=sub[ys.min():ys.max() + 1, xs.min():xs.max() + 1], area=int(sub.sum())))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--out", default="build")
    ap.add_argument("--split-touching", action="store_true")
    ap.add_argument("--word-gap", type=float, default=2.2, help="a gap this many times the median letter gap starts a new word")
    a = ap.parse_args()

    ink = load_ink(a.image)
    mask_all = ink > THR
    text_lines = read_transcript(a.transcript)
    bands = find_lines(ink)
    print(f"{len(bands)} text lines detected, transcript has {len(text_lines)}")
    if len(bands) != len(text_lines):
        for i, (s, e) in enumerate(bands):
            print(f"  band {i}: rows {s}-{e} (height {e - s})")
        raise SystemExit("line count mismatch: edit the transcript (one line per band above), or re-run prep.py "
                         "(try --remove-rules / --deskew / a different --thresh)")

    os.makedirs(os.path.join(a.out, "masks"), exist_ok=True)
    # pass 1: segment every line, collect matches; pass 2 (optional): split touching letters
    per_line = []
    width_by_char = defaultdict(list)     # width / band height, from cleanly matched instances
    for li, (ys, ye) in enumerate(bands):
        pad = 3
        y0 = max(0, ys - pad)
        comps = components(mask_all[y0:ye + pad], y0)
        h = ye - ys
        med_area = np.median([c["area"] for c in comps]) if comps else 0
        comps = [c for c in comps if c["area"] >= max(4, 0.015 * med_area)]        # drop specks
        comps = merge_vertical(comps, max_gap=0.2 * h)
        if not comps:
            per_line.append((h, [], [])); continue
        gaps = [comps[i + 1]["x0"] - comps[i]["x1"] for i in range(len(comps) - 1)]
        med = np.median([g for g in gaps if g > 0]) if any(g > 0 for g in gaps) else 1
        med_w = np.median([c["x1"] - c["x0"] for c in comps])
        words = [[comps[0]]]
        word_gaps = []
        for g, c in zip(gaps, comps[1:]):
            if g > max(a.word_gap * med, 0.5 * med_w):
                words.append([c]); word_gaps.append(int(g))
            else:
                words[-1].append(c)
        per_line.append((h, words, word_gaps))
        tw = text_lines[li].split()
        if len(words) == len(tw):
            for w, t in zip(words, tw):
                if len(w) == len(t):
                    for c, ch in zip(w, t):
                        width_by_char[ch].append((c["x1"] - c["x0"]) / h)

    glyphs, report, all_word_gaps = [], [], []
    for li, (h, words, word_gaps) in enumerate(per_line):
        tw = text_lines[li].split()
        if len(words) != len(tw):
            report.append(f"line {li:2d}: {len(words)} words found vs {len(tw)} in transcript -> skipped "
                          f"({'no ink' if not words else 'try --word-gap ' + ('1.6' if len(words) < len(tw) else '3')})")
            continue
        all_word_gaps += [(li, g, h) for g in word_gaps]
        bad = []
        for w, t in zip(words, tw):
            if len(w) != len(t) and a.split_touching and len(w) < len(t) and all(width_by_char.get(c) for c in t):
                exp = {c: float(np.median(width_by_char[c])) * h for c in set(t)}
                w = split_touching(w, t, exp)
            if len(w) != len(t):
                bad.append(f"{t!r}:{len(w)}/{len(t)}")
                continue
            for k, (c, ch) in enumerate(zip(w, t)):
                gid = len(glyphs)
                Image.fromarray((c["mask"] * 255).astype(np.uint8)).save(os.path.join(a.out, "masks", f"{gid}.png"))
                glyphs.append(dict(id=gid, line=li, char=ch, x0=int(c["x0"]), x1=int(c["x1"]), y0=int(c["y0"]), y1=int(c["y1"]),
                                   lgap=int(c["x0"] - w[k - 1]["x1"]) if k > 0 else None,
                                   rgap=int(w[k + 1]["x0"] - c["x1"]) if k < len(w) - 1 else None))
        report.append(f"line {li:2d}: ok" + (f"  unmatched words: {' '.join(bad)}" if bad else ""))

    print("\n".join(report))
    chars = sorted(set(g["char"] for g in glyphs))
    counts = {c: sum(1 for g in glyphs if g["char"] == c) for c in chars}
    print(f"{len(glyphs)} glyphs matched, {len(chars)} distinct characters:")
    print(" ".join(f"{c}:{n}" for c, n in counts.items()))
    missing = sorted(set("".join(text_lines).replace(" ", "")) - set(chars))
    if missing:
        print("characters in the transcript with no clean instance:", " ".join(missing))
    save_json(dict(image=os.path.abspath(a.image), bands=bands, glyphs=glyphs, word_gaps=all_word_gaps,
                   lines=text_lines), os.path.join(a.out, "glyphs.json"))


if __name__ == "__main__":
    main()
