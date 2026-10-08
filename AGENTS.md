# AGENTS.md - using this repository as an agent

This repo is a Claude Code skill, but nothing in it depends on Claude. Any agent (or person)
that can run Python and look at images can use it. The authoritative workflow with the
reasoning behind each step is `font-from-image/SKILL.md`; this file is the condensed version.

## What it does

Given an image of lettering (handwriting, a scanned note, an AI-generated quote card, a
wordmark, a screenshot) it either

- **identifies** the free font the lettering is set in (Google Fonts, open licences), or
- **creates** a font from the image: OTF, TTF and WOFF2, with every character the image lacks
  composed from the image's own strokes,

and in both cases **measures the typography** (size, line height, letter/word spacing,
alignment, margins, colours, slant, weight) as settings for CSS, Figma, Canva and Docs.

Nothing is uploaded anywhere. Candidate fonts are downloaded from github.com/google/fonts.

## Setup (once per project)

```bash
bash <repo>/font-from-image/scripts/setup.sh .venv
PY=.venv/bin/python
SK=<repo>/font-from-image/scripts
```

Work in a fresh folder named for the font. Copy the source image into it.

## Decide: font or hand?

```bash
$PY $SK/prep.py image.jpg --out build/prepared.png [--remove-rules] [--deskew] [--invert] [--scale 2]
$PY $SK/glyph_consistency.py build/prepared.png --out build/consistency.png
```

Look at `build/prepared.png` (strokes solid and separate?) and `build/consistency.png`
(are the repeated letters identical tiles?). Identical -> probably a real font, try identify
first. Varying -> drawn or generated, create. The user's own statement about the image's
origin outranks this check.

## Identify path

1. Note the lettering's features: slant, monoline vs thick/thin, single or double storey `a`
   and `g`, `y`/`f` descenders, bounce, width.
2. Choose 8-15 candidate families from `font-from-image/references/free-handwriting-fonts.md`
   (directory names as in google/fonts, e.g. `patrickhand`).
3. Render them next to a crop of the image:
   ```bash
   $PY $SK/identify.py --image image.jpg --crop X0 Y0 X1 Y1 --text "words in the crop" \
     --families caveat,kalam,patrickhand --out build/identify
   ```
4. Look at `build/identify/comparison.png`. Compare letter by letter, eliminate, repeat with
   relatives of the closest ones. Report the match honestly (exact / closest free alternative
   / looks like a commercial or system font).
5. Measure settings for the matched font:
   ```bash
   $PY $SK/measure_style.py --build build --image image.jpg --matched-font build/identify/fonts/<file>.ttf --matched-name "Caveat"
   ```
   (requires the segment step below to have run once, for line metrics)

## Create path

```bash
# transcript.txt: one line per line of lettering, same spelling and punctuation, top to bottom
$PY $SK/segment.py --image build/prepared.png --transcript transcript.txt --out build --split-touching
$PY $SK/pick_glyphs.py --build build [--native-lines 0] [--exclude-lines 12]
$PY $SK/build_font.py --build build --family "Her Hand" --style Regular --out fonts
$PY $SK/specimen.py --build build --font fonts/HerHand-Regular.ttf --compare image.jpg
$PY $SK/measure_style.py --build build --image image.jpg
```

Check after each step: the segment report (line count must match; a few skipped words are
fine), `build/selected_sheet.png` (one clean letter per tile), `build/specimen_compare.png`
(the re-typeset text next to the original). Fix the transcript or prep flags rather than
pushing on with bad segmentation.

Second weight from heading lettering in the same image:
```bash
$PY $SK/pick_glyphs.py --build build --native-lines 0
$PY $SK/build_font.py --build build --family "Her Hand" --style Bold --out fonts \
  --native --embolden 18 --xscale 0.84 --bearing-factor 0.6 --space 0.52
```
Measure the heading's stroke, width and gaps against the body's before choosing those numbers.

Preview composed characters: `$PY $SK/synth_glyphs.py --build build --chars "ABC123?&"`.

## Deliver

A self-contained folder: `fonts/` (otf, ttf, woff2), `specimen.png`, `STYLE.md` (from
`build/style/`), a `demo.html` with `@font-face`, `transcript.txt`, `build/`, and a README
stating which characters were traced from the image and which were composed, plus the
limits (one weight, no kerning, composed characters are designs not copies). Offer the choice
between the built font and a matched free font when both exist.

## Files

| path | role |
|---|---|
| `font-from-image/SKILL.md` | full workflow and judgement calls |
| `font-from-image/scripts/*.py` | the pipeline; each file's docstring documents its flags |
| `font-from-image/references/free-handwriting-fonts.md` | candidate list with the tells to compare |
| `font-from-image/references/pipeline-details.md` | internals and tuning knobs per stage |
| `evals/` | two test prompts with their images |
| `font-from-image.skill` | packaged skill for Claude's Save-skill button |

## Conventions

- `build/` is the working directory for one image; `glyphs.json` and `selected.json` carry
  absolute paths, so later steps can run from anywhere.
- Font units: 1000 per em, x-height 480 (`--xheight-units`).
- Do not upload the user's image to online font identifiers; mention that they exist.
- A font made from someone else's handwriting needs that person's permission.
