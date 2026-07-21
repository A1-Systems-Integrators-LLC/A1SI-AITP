#!/usr/bin/env python3
"""
A1SI AITP — icon export pipeline (run AFTER a concept is selected).

The sample sheet (A1SI-AITP_icon_sample_sheet.html) is the selection step.
Once a concept wins, set CONCEPT below to its code and run:

    python3 export_icons.py

It renders the chosen master — svg/<CONCEPT>.svg, the single source kept in
lockstep with generate.py — to every consuming surface:

  - docs/branding/icons/web/      favicons (16/32/48/180/192/512)
  - docs/branding/icons/ios/      AppIcon set (mirrors the shared Icons tree)
  - docs/branding/icons/android/  mipmap densities + play-store-512
  - docs/branding/icons/A1SI-AITP_icon_QA_sheet.png   manual visual QA
  - frontend/public/              favicon.png + apple-touch-icon.png (live app)

Requires rsvg-convert (brew install librsvg) and ImageMagick (magick).
Keep CONCEPT pointing at the selected svg/*.svg; do not hand-edit binaries.
"""
import os
import shutil
import subprocess
import sys

# ---- the selected concept ---------------------------------------------------
# Selected from the sample sheet (June 2026): C8 "Hex Trade Node" — the A1SI
# family badge (sibling of CVWS/TERM/WIFI "Hex Node"), candlesticks inside.
CONCEPT = "C8_hex_trade_node"

HERE = os.path.dirname(os.path.abspath(__file__))
SVG = os.path.join(HERE, "svg", f"{CONCEPT}.svg")
ICONS = os.path.normpath(os.path.join(HERE, "..", "icons"))
# frontend/public lives at <repo>/frontend/public (HERE = repo/docs/branding/icon-concepts)
PUBLIC = os.path.normpath(os.path.join(HERE, "..", "..", "..", "frontend", "public"))

# size -> filename, per surface
WEB = {
    16: "favicon-16.png",
    32: "favicon-32.png",
    48: "favicon-48.png",
    180: "apple-touch-icon.png",
    192: "icon-192.png",
    512: "icon-512.png",
}
# iOS AppIcon set — names mirror /Dev/A1SI/Icons/Light/iOS-iPadOS
IOS = {
    40: "AppIcon-20x20@2x.png", 60: "AppIcon-20x20@3x.png",
    58: "AppIcon-29x29@2x.png", 87: "AppIcon-29x29@3x.png",
    80: "AppIcon-40x40@2x.png", 120: "AppIcon-60x60@2x.png",
    180: "AppIcon-60x60@3x.png", 76: "AppIcon-76x76@1x.png",
    152: "AppIcon-76x76@2x.png", 167: "AppIcon-83.5x83.5@2x.png",
    1024: "AppIcon-1024x1024@1x.png",
}
ANDROID = {
    48: "mipmap-mdpi.png", 72: "mipmap-hdpi.png", 96: "mipmap-xhdpi.png",
    144: "mipmap-xxhdpi.png", 192: "mipmap-xxxhdpi.png", 512: "play-store-512.png",
}
# Live web + PWA set written straight into frontend/public/ (size -> filename).
# 16/32/48 favicons, 180 apple-touch (iOS add-to-home), 192/512 maskable PWA.
LIVE = {
    16: "favicon-16x16.png", 32: "favicon-32x32.png", 48: "favicon.png",
    180: "apple-touch-icon.png", 192: "icon-192.png", 512: "icon-512.png",
}
MANIFEST = """{
  "name": "A1SI-AITP Investment Platform",
  "short_name": "AITP",
  "description": "AI-powered multi-asset investment platform",
  "icons": [
    { "src": "/favicon-32x32.png", "sizes": "32x32", "type": "image/png" },
    { "src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable" },
    { "src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable" }
  ],
  "theme_color": "#00007B",
  "background_color": "#00004E",
  "display": "standalone",
  "start_url": "/"
}
"""


def render(size, out):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    subprocess.run(
        ["rsvg-convert", "-w", str(size), "-h", str(size), SVG, "-o", out],
        check=True,
    )


def emit(mapping, subdir):
    dest = os.path.join(ICONS, subdir)
    for size, name in sorted(mapping.items()):
        render(size, os.path.join(dest, name))
    print(f"  {subdir:9s} -> {len(mapping)} files")


def main():
    if not os.path.exists(SVG):
        sys.exit(f"missing {SVG} — run ./render.sh (or fix CONCEPT={CONCEPT!r})")
    if not shutil.which("rsvg-convert"):
        sys.exit("rsvg-convert not found — brew install librsvg")

    print(f"Exporting concept {CONCEPT!r}")
    emit(WEB, "web")
    emit(IOS, "ios")
    emit(ANDROID, "android")

    # live app surfaces — full web + PWA set + manifest
    if os.path.isdir(PUBLIC):
        for size, name in sorted(LIVE.items()):
            render(size, os.path.join(PUBLIC, name))
        with open(os.path.join(PUBLIC, "site.webmanifest"), "w") as f:
            f.write(MANIFEST)
        print(f"  frontend/public -> {len(LIVE)} icons + site.webmanifest")
    else:
        print(f"  (skipped frontend/public — not found at {PUBLIC})")

    # QA sheet: a strip of representative sizes for manual review
    if shutil.which("magick"):
        sizes = [512, 180, 120, 76, 48, 32]
        tmp = []
        for s in sizes:
            p = os.path.join(ICONS, f".qa_{s}.png")
            render(s, p)
            tmp.append(p)
        sheet = os.path.join(ICONS, "A1SI-AITP_icon_QA_sheet.png")
        subprocess.run(
            ["magick", "montage", "+label", *tmp, "-tile", f"{len(sizes)}x1",
             "-geometry", "+12+12", "-background", "#00004E", sheet],
            check=True,
        )
        for p in tmp:
            os.remove(p)
        print(f"  QA sheet -> {os.path.relpath(sheet, HERE)}")

    print("done.")


if __name__ == "__main__":
    main()
