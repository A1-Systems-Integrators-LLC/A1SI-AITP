#!/usr/bin/env bash
# Reproducible render pipeline for the A1SI AITP icon concepts.
#
#   1. (re)generates the concept SVGs from generate.py
#   2. rasterizes each to a 1024x1024 master PNG (App Store / Play Store size)
#   3. rasterizes a 48px tile per concept (small-size legibility check)
#   4. composites a contact sheet + a small-size verification strip
#
# Requires: python3, rsvg-convert (brew install librsvg), ImageMagick (brew install imagemagick).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

mkdir -p svg png /tmp/aitp48
python3 generate.py

for f in svg/*.svg; do
  n="$(basename "$f" .svg)"
  rsvg-convert -w 1024 -h 1024 "$f" -o "png/${n}_1024.png"
  rsvg-convert -w 48   -h 48   "$f" -o "/tmp/aitp48/${n}.png"
done

# Contact sheet (4x3) + 48px legibility strip. +label so montage skips the
# text-label path (no ghostscript/freetype required).
magick montage +label png/*_1024.png -tile 4x3 -geometry 300x300+10+10 \
  -background '#00004E' png/_contact_sheet.png
magick montage +label /tmp/aitp48/*.png -tile 12x1 -geometry 48x48+10+10 \
  -background '#00004E' png/_small_size_verification.png

echo "Rendered $(ls png/*_1024.png | wc -l | tr -d ' ') concepts + 2 QA sheets into png/"
echo "Open A1SI-AITP_icon_sample_sheet.html to review the labelled sample sheet."
