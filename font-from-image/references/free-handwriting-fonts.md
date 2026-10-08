# Free handwriting and display fonts to compare against

All families below are on Google Fonts (SIL Open Font License or Apache 2.0) and can be
fetched by `scripts/identify.py --families <dirname,...>`. The directory name is the family
name lower-cased with spaces removed (as in github.com/google/fonts/tree/main/ofl).

Use the look of the lettering to pick a group, then compare 8-15 families at once. The
"tells" column lists what to check against the image.

## Marker / felt-tip, upright, some stroke contrast
| family | dir | weights | tells |
|---|---|---|---|
| Kalam | kalam | 300/400/700 | slight slant, brush contrast, Devanagari sibling; `y` straight tail |
| Caveat Brush | caveatbrush | 400 | condensed, heavy, quirky `e` |
| Permanent Marker | permanentmarker | 400 | wide, very heavy, square-ish bowls |
| Rock Salt | rocksalt | 400 | rough chalky edges, caps-like |
| Sedgwick Ave / Display | sedgwickave, sedgwickavedisplay | 400 | wide marker, bouncy |
| Mansalva | mansalva | 400 | upright marker, angular |
| Covered By Your Grace | coveredbyyourgrace | 400 | jittery thin-thick, tall |
| Gloria Hallelujah | gloriahallelujah | 400 | wide, rounded, childlike |
| Delicious Handrawn | delicioushandrawn | 400 | narrow marker |
| Gochi Hand | gochihand | 400 | upright, quirky angled `o` |

## Neat upright print (monoline, "school" or "architect" hand)
| family | dir | weights | tells |
|---|---|---|---|
| Patrick Hand / SC | patrickhand, patrickhandsc | 400 | condensed, monoline, open `g` |
| Architects Daughter | architectsdaughter | 400 | wide, tall x-height |
| Coming Soon | comingsoon | 400 | rounded monoline, wide |
| Short Stack | shortstack | 400 | heavy monoline |
| Schoolbell | schoolbell | 400 | bold rounded |
| Handlee | handlee | 400 | slight slant, soft |
| Delius | delius | 400 | rounded print, very regular |
| Shantell Sans | shantellsans | 300-800, variable | monoline, bouncy axis, many weights |
| Edu NSW ACT / QLD / SA / TAS / VIC WA NT | edunswactfoundation, eduqldbeginner, edusabeginner, edutasbeginner, eduvicwantbeginner | 400-700 | Australian school print hands |
| Comic Neue | comicneue | 300/400/700 | tidy comic print |
| Mali | mali | 200-700 | Thai+Latin, round monoline, many weights |
| Itim | itim | 400 | round, friendly |
| Sriracha | sriracha | 400 | slanted, bold |

## Casual script / connected-ish
| family | dir | weights | tells |
|---|---|---|---|
| Caveat | caveat | 400-700 variable | slanted, condensed, popular |
| Shadows Into Light / Two | shadowsintolight, shadowsintolighttwo | 400 | thin, tall, airy |
| Indie Flower | indieflower | 400 | round, bubbly |
| Reenie Beanie | reeniebeanie | 400 | thin ballpoint |
| Just Another Hand | justanotherhand | 400 | very condensed, tall |
| Nothing You Could Do | nothingyoucoulddo | 400 | ink-pen contrast |
| Homemade Apple | homemadeapple | 400 | cursive, loopy |
| Dawning of a New Day | dawningofanewday | 400 | thin cursive |
| Cedarville Cursive | cedarvillecursive | 400 | cursive school |
| Zeyada | zeyada | 400 | scratchy cursive |
| Kristi | kristi | 400 | thin flowing |
| Mrs Saint Delafield | mrssaintdelafield | 400 | elegant script |
| Sacramento | sacramento | 400 | monoline script |
| Dancing Script | dancingscript | 400-700 | bouncy formal script |
| Pacifico | pacifico | 400 | heavy retro script |
| Grape Nuts | grapenuts | 400 | upright pencil |
| Mynerve | mynerve | 400 | bouncy, narrow |
| Playwrite (regional variants) | playwrite* | 100-400 | school cursive models |

## Korean / Japanese handwriting families with Latin
| family | dir | weights | tells |
|---|---|---|---|
| Gaegu | gaegu | 300/400/700 | pen-like, childlike Latin |
| Nanum Pen Script | nanumpenscript | 400 | scratchy pen |
| Hi Melody | himelody | 400 | thin, cute |
| Gamja Flower | gamjaflower | 400 | marker |
| Poor Story | poorstory | 400 | rounded |
| Single Day | singleday | 400 | bold |
| Klee One | kleeone | 400/600 | pen, calligraphic |
| Yomogi | yomogi | 400 | thin pen |
| Zen Kurenaido | zenkurenaido | 400 | pen |

## Brush / calligraphic
| family | dir | weights | tells |
|---|---|---|---|
| Caveat Brush | caveatbrush | 400 | |
| Nanum Brush Script | nanumbrushscript | 400 | dry brush |
| Kaushan Script | kaushanscript | 400 | slanted brush |
| Courgette | courgette | 400 | soft brush script |
| Satisfy | satisfy | 400 | brush script |
| Yellowtail | yellowtail | 400 | retro brush |

## Indic-script families with handwriting-style Latin
| family | dir | weights | tells |
|---|---|---|---|
| Kalam | kalam | 300/400/700 | Devanagari |
| Dekko | dekko | 400 | Devanagari, upright casual |
| Chilanka | chilanka | 400 | Malayalam, rounded |
| Baloo (2) family | baloo2, baloobhai2, ... | 400-800 | rounded display, many scripts |

## Not on Google Fonts but common in images
If the lettering matches none of the above but looks like a system or app font, name the
likely one and say it is not free to redistribute: Bradley Hand, Marker Felt, Noteworthy,
Chalkboard (macOS); Segoe Print, Segoe Script, Ink Free, Kristen ITC (Windows); Hand of Sean,
Brittany and other Canva-exclusive fonts. The user can still use what their OS or Canva license
allows; the free alternative from the tables above is the thing to recommend for the web.

## Reading the comparison sheet
Judge in this order, because it eliminates fastest: slant -> stroke contrast (monoline vs
thick/thin) -> `a` (single or double storey) -> `g` (open tail, loop, or closed) -> `y` and `f`
descenders -> `t` crossbar height -> letter width -> baseline bounce. A family can match on
feel and fail on one of these; only a font that matches all of them is the font.
