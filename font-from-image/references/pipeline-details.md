# Pipeline details and knobs

How each script works, what it writes, and what to change when the defaults fail. Read the
section for the step that produced a bad result.

## prep.py -> build/prepared.png
Grayscale, optional invert, background division (median+gaussian blur of the page) so uneven
light or a coloured background becomes flat white, contrast stretch to the 99.5th percentile,
then a soft threshold (`--thresh`, default 0.25). `--remove-rules` erases horizontal runs longer
than a quarter of the width (ruled paper). `--deskew` tries rotations of +-5 degrees and keeps
the one with the sharpest line profile.

- strokes broken into pieces -> `--thresh 0.15`; letters fused -> `--thresh 0.35`
- `--soft` keeps the full grey ramp (better antialiasing for crisp digital images)
- tiny image -> `--scale 2` or 3 (upsampling before thresholding gives smoother outlines)

## glyph_consistency.py -> build/consistency.png
Template-matches one small round letter (auto-picked, or `--region`) across the image and
tiles the best matches. Identical tiles with scores >= 0.97 mean exact repeats.

## identify.py -> build/identify/comparison.png
Downloads the named families' TTFs from github.com/google/fonts (ofl/, apache/, ufl/) into
`build/identify/fonts/`, renders `--text` at a size matched to the crop, and stacks them under
the crop. `--size` overrides the render size. Variable fonts render at their default instance.

## segment.py -> build/glyphs.json, build/masks/<id>.png
1. Lines: rows with more than 0.2% ink form bands; slivers under 35% of the median band height
   (i-dots, descender tips) are merged into the neighbouring band.
2. Components: 8-connected, specks under 1.5% of the median area dropped, vertically stacked
   components with >= 50% x-overlap merged when the gap is under 20% of the band height
   (i-dots and broken strokes, but not the next line's ascenders).
3. Words: a gap larger than `--word-gap` (2.2) x the median letter gap, and at least half the
   median letter width, starts a new word. Lines where the word count disagrees with the
   transcript are skipped and reported.
4. Letters: one component per character, else the word is skipped; `--split-touching` cuts
   merged components at the thinnest column near each boundary predicted from the widths of
   the same letters elsewhere (needs every letter in the word to have been seen cleanly).
   Each glyph records its left/right gap to neighbours; word gaps are recorded per line.

The JSON holds the absolute prepared-image path, so later steps can be run from anywhere.

## pick_glyphs.py -> build/selected.json, build/selected_sheet.png
Medoid selection on 48x48 normalised crops (mean absolute difference). Line metrics:
baseline = median bottom of non-descender alphanumerics; x-height = median top of
`aceimnorsuvwxz`, or 0.68 x cap height when a line has no such letters; ascender = median top
of `bdfhklt0-9A-Z`. Lines whose x-height is within 15% of the median share one scale (`group_xheight`),
so same-size lines do not get slightly different sizes; headings keep their own.

`--native-lines` puts those lines' glyphs in `selected_native` (used by `build_font.py --native`)
and keeps them out of the regular pick. `--exclude-lines` ignores lines entirely.

## synth_glyphs.py -> used by build_font; preview build/synth_sheet.png
Lifts strokes from `l o c u n v w x z s .` when present (skeletonise, dilate to a thin core),
scales/flips them into recipes, adds procedural lines and arcs (with a slight bow for a hand
feel), and re-inks everything with a round pen whose radius is the median distance-transform
value along the skeletons of the real letters. Procedural stand-ins cover any missing piece.
Recipes exist for a-z, A-Z, 0-9, common punctuation, `& @ # % $ € ₹ £` and quotes/dashes.
Sizes: x-height = measured; cap height = measured ascender x 0.98; digits = 0.95 cap.

To change a letter's design, edit its recipe (one line each). To preview a subset:
`synth_glyphs.py --build build --chars "ABC123"`.

## build_font.py -> fonts/<Family>-<Style>.{otf,ttf,woff2}
- Scale: `--xheight-units` (480) / line x-height, per line group. Vertical offsets from the
  baseline are preserved per glyph.
- Tracing: 8x bicubic upscale of the masked grey crop, threshold 0.5, 1-px opening, potrace
  (turdsize 64, alphamax 1.0, opttolerance 0.25). `--embolden N` dilates the bitmap by N font
  units per side first.
- Bearings: half of the median gap measured on each side of that character, times
  `--bearing-factor`; composed glyphs get 1.2 px (1.5 for capitals and symbols) each side.
- Space: measured median word gap, or `--space` in x-heights.
- `--xscale` scales outlines and bearings horizontally (condense/extend).
- `--native`: characters present in `selected_native` are traced from there without
  embolden/xscale, with their own measured bearings.
- Composed glyphs: every character in `--synth-chars` (default: a-z A-Z 0-9 punctuation)
  that the image does not supply. `--no-synth` disables.
- Metrics: ascender = 1.08 x tallest of `l d h b k t`, descender = 1.1 x lowest of `g j p q y`,
  lineGap 0. OS/2 weight class 700 and the bold bits are set when the style name starts with
  "Bold". Glyph names follow the Adobe Glyph List.
- Contour direction is normalised per format (CFF counter-clockwise outer, TrueType clockwise).

Three outputs: CFF OTF (cubic, smallest), TrueType TTF (quadratic via cu2qu), WOFF2 of the TTF.

## specimen.py -> build/specimen.png (+ _compare.png)
Draws each transcript line at its measured baseline and left edge, at size
x-height / xheight-units x 1000 px, with `--native-font` for native lines. `--compare` puts the
original beside it. Pillow renders with FreeType, so advances round to whole pixels at small
sizes; judge spacing at the specimen size, not at 12 px.

## measure_style.py -> build/style/STYLE.md, style.json
Groups lines by `group_xheight` (body vs headings). Per group: x-height and ascender in
original-image px, baseline pitch (median of baseline differences), median letter gap and word
gap, alignment (whichever of left edges / right edges / centres varies least), text block
margins, slant (principal axis of the upper part of `l i I d` stems), stroke/x-height from the
distance transform of round letters (weight hint: regular < 0.26 < medium < 0.36 < bold).
Font size = x-height / the font's x-height ratio: 0.48 for built fonts, the OS/2 sxHeight for a
`--matched-font`. Letter spacing is reported in em (gap / font size); for the built font it is
baked into the side bearings, so tools get 0. Colours: median RGB of ink pixels and of paper
pixels after background normalisation. Canva font-size numbers are approximate (Canva units are
~1.33 px); the specimen is the ground truth.

## Making a second weight without bold lettering in the image
Measure before setting flags. For the heading vs body of one image: stroke width (distance
transform on both), letter width per x-height, letter gap per x-height, word gap per x-height.
Then `--embolden` = (target stroke - body stroke) / 2 in font units, `--xscale` = width ratio,
`--bearing-factor` from the gap ratio adjusted for the extra stroke, `--space` = word gap ratio.
In the reference case (an Instagram quote card) that came out at 18 / 0.84 / 0.6 / 0.52.
