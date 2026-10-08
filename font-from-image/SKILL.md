---
name: font-from-image
description: Turn lettering in an image into a usable font, or find the free font it already is. Use this whenever someone shares a picture of handwriting, a handwritten note, a scanned letter, an AI-generated "handwritten" quote card, a logo wordmark, calligraphy, or a screenshot of text and wants a font file from it, asks "what font is this", wants to "type in my own handwriting", or wants to recreate a lettering style for a website, poster or Instagram post. Covers both paths - identifying a matching open-licensed font (Google Fonts) and building a real OTF/TTF/WOFF2 from the image, including composing capitals, digits and punctuation the image does not contain. Also use it for "make a bold/second weight from this heading" and for checking whether an image was set in a real font at all.
---

# Font from image

Two ways to get a font out of a picture of lettering:

1. **Identify** - the lettering was set in an existing typeface and a free, open-licensed
   one may match it. Cheap, and the result is a professionally made font.
2. **Create** - the lettering is handwritten, AI-generated, or unique, so the font has to be
   cut out of the image itself. Slower, but it reproduces exactly that hand.

Most requests need a quick look at both. The sections below go through: decide, identify,
create, finish. The scripts live in `scripts/` (Python; run `scripts/setup.sh` once to make a
virtualenv with fonttools, potracer, numpy, scipy, pillow, scikit-image, brotli).

## 1. Decide which path

Look at the image first, as an image. Note what you see: upright or slanted, monoline or
thick/thin, single-storey `a` and `g` or double, does the baseline bounce, do letters connect,
is there a heavier heading. These observations drive both paths.

Then ask the one question that matters: **do repeated letters look identical?** Fonts repeat
glyphs exactly; hands do not. Run

```bash
python scripts/glyph_consistency.py prepared.png --out build/consistency.png
```

and look at the tile sheet it writes. If the tiles are the same shape, the image is probably
set in a font (identify first). If they vary, it is drawn or generated: creating is the only
route. AI image generators sometimes produce perfectly repeated glyphs, so the user's knowledge
("I drew this", "ChatGPT made it") outranks the check.

Ask the user which they want only when it is genuinely open: someone who says "make me a font
from my handwriting" wants the create path, someone who asks "what font is this" wants
identify. When unsure, offer both in one sentence and default to identify-then-create.

## 2. Identify a free font

Claude can view images, so identification is a visual comparison, not a lookup. The method
that works: shortlist candidates from what the lettering looks like, render the same sentence
in each candidate, and look at them next to the crop.

1. Pick a line from the image with a good mix of letters (`a g y f t e s` are the most
   diagnostic). Note its pixel region.
2. Choose 8-15 candidate families from `references/free-handwriting-fonts.md` (grouped by
   look: marker, neat print, casual script, brush, school hand, etc.). Prefer families whose
   distinguishing letters match what you noted in step 1.
3. Render the comparison sheet:
   ```bash
   python scripts/identify.py --image image.png --crop X0 Y0 X1 Y1 \
     --text "the exact words in the crop" --families kalam,caveat,patrickhand --out build/identify
   ```
   It downloads the TTFs from the google/fonts repository (all open-licensed) and writes
   `build/identify/comparison.png` with the crop on top.
4. Look at the sheet. Compare letter by letter, not by overall feel: slant, stroke contrast,
   the shapes of `a g y f t`, letter width, bounce. Eliminate, pick the two or three closest,
   and do a second round with their relatives (same designer, same category) if nothing is
   exact. Two rounds usually settle it.

Report the result honestly: "this is Kalam Bold" when it is, "closest free match is X, but the
g and y differ" when it is not. If the lettering is clearly a commercial font, say so and name
the closest free alternative. Do not upload the user's image to an online identifier yourself;
you can tell them that WhatTheFont (MyFonts) and Font Squirrel's Matcherator exist if they want
to try one, since those accept uploads.

A matching free font ends the job: tell the user the family, where it is (Google Fonts), the
license (OFL or Apache), and the CSS to use it. If they still want the exact image hand, or
nothing matched, continue to create.

## 3. Create a font from the image

The pipeline cuts every letter out of the image, picks the best instance of each, traces it,
and assembles real font files. Each step writes something to look at; look at it before moving
on, because every later step trusts the earlier ones.

### 3.1 Prepare the image

```bash
python scripts/prep.py image.jpg --out build/prepared.png [--remove-rules] [--deskew] [--invert] [--scale 2]
```

Produces dark ink on white with lighting evened out. Use `--remove-rules` for notebook paper,
`--deskew` for photos taken at an angle, `--invert` for light-on-dark, `--scale 2` when letters
are under ~25 px tall (tracing needs at least that). View the output: strokes should be solid
and separate. Adjust `--thresh` if they are broken (lower) or bleeding together (higher).

### 3.2 Transcribe

Write `transcript.txt`: exactly one line per line of lettering, top to bottom, same spelling,
same punctuation, spaces only between words. Read the text from the image yourself; for
handwriting that is hard to read, ask the user to confirm the transcript rather than guessing,
because every character you get wrong becomes a wrongly labelled glyph.

Signature lines, crossed-out words and doodles: include the line in the transcript if it is
text (you can exclude it later), or crop it out of the image before prep.

### 3.3 Segment and match

```bash
python scripts/segment.py --image build/prepared.png --transcript transcript.txt --out build --split-touching
```

Lines are found by ink projection, words by gap size, letters as connected components
(i-dots are merged with their stems). Each word is matched to the transcript word; a word
whose letter count does not match is skipped, which is fine because most letters occur many
times. `--split-touching` cuts letters that touch (common in headings) using letter widths
measured elsewhere in the image.

Read the report. If the line count differs from the transcript nothing is written: fix the
transcript or re-prep. A few skipped words per line are normal; a whole line skipped usually
means the word-gap heuristic failed (`--word-gap 1.6` or `3`). "Characters with no clean
instance" will be composed later, or you can crop a clearer sample.

### 3.4 Pick glyphs

```bash
python scripts/pick_glyphs.py --build build [--native-lines 0] [--exclude-lines 12]
```

For each character the medoid instance (most similar to all the others) is chosen, and each
line's baseline and x-height are measured so letters keep their own vertical bounce. Look at
`build/selected_sheet.png`: every tile should be a clean single letter. A wrong tile means a
mis-segmented word; fix the transcript or exclude that line.

`--native-lines` marks lines whose lettering is a different style (a bold heading): their
glyphs become the source for a second weight. `--exclude-lines` drops a signature or a
different hand.

### 3.5 Build

```bash
python scripts/build_font.py --build build --family "Her Hand" --style Regular --out fonts
```

Traces each glyph (8x upscaled, potrace), spaces it with the gaps measured between letters in
the image, composes every standard character the image lacks from the strokes it has
(`scripts/synth_glyphs.py`: capitals, digits, punctuation, currency, and lowercase letters
that never appeared), and writes OTF, TTF and WOFF2. The pen for composed glyphs is measured
from the real letters, so they share the stroke weight.

For a second weight from heading lettering:
```bash
python scripts/build_font.py --build build --family "Her Hand" --style Bold --out fonts \
  --native --embolden 18 --xscale 0.84 --bearing-factor 0.6 --space 0.52
```
`--native` uses the heading's own glyphs where they exist; the other flags shape the fallback
glyphs to match (thicker, condensed, tighter). Measure rather than guess: compare the heading's
stroke width, letter width and gaps to the body's and set the flags from those ratios.

### 3.6 Check

```bash
python scripts/specimen.py --build build --font fonts/HerHand-Regular.ttf --compare image.jpg
```

Re-typesets the transcript at the measured positions, next to the original. Look at it. The
things that go wrong and how to see them:

- a letter looks wrong everywhere -> the picked instance is bad: exclude that line or crop a
  better sample and re-run pick
- the text is wider or narrower than the original -> spacing; `--bearing-factor`
- stray dots or fragments on a glyph -> a neighbour's piece was merged in; check the
  selected sheet, re-segment
- strokes thinner than the original -> prep threshold too high
- composed glyphs look heavier or lighter than traced ones -> check `synth_glyphs.py` preview
  (`python scripts/synth_glyphs.py --build build`) and adjust the prep threshold

Also render a line of composed characters (capitals, digits) and show it to the user; they
are designs in the hand's pen, not copies, and the user should know which characters those are.

## 4. Finish

Deliver a small project, not loose files: `fonts/` with all three formats, a `demo.html` with
`@font-face` rules, `specimen.png`, the transcript and build directory so it can be rebuilt,
and a README that lists which characters came from the image and which were composed. Say in
the README (and to the user) what the font cannot do: no kerning, no alternates, composed
characters are approximations. Suggest the SIL Open Font License if the user wants to share
it, with themselves as copyright holder; a font made from someone else's handwriting needs
that person's permission.

Tell the user how to install (double-click the TTF, or `@font-face` on the web) and offer the
obvious next steps: a second weight, better composed glyphs from a sample sheet they write
containing the missing characters, or a cleaner source image.

## Working notes

- Resolution is the main quality limit. Letters under 20 px x-height trace soft. Ask for the
  original file rather than a screenshot of it when the image is small.
- Stroke weight is measured, not assumed: when adding a weight, compare stroke/x-height ratios
  before choosing `--embolden`.
- The medoid pick is robust, but with only one or two instances of a letter it just takes
  what is there. Mention low-count letters (the segment report lists counts) if they look off.
- Keep the user's image private: everything here runs locally; nothing is uploaded.
- `references/pipeline-details.md` explains each script's internals and knobs when something
  needs adjusting beyond the flags above.
