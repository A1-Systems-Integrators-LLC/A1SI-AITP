# A1SI AITP — Shipped Icon Set (C8 "Hex Trade Node")

Reference copies of the selected icon, exported to every consuming surface by
[`../icon-concepts/export_icons.py`](../icon-concepts/export_icons.py). **Do
not hand-edit these PNGs** — they are rendered from
[`../icon-concepts/svg/C8_hex_trade_node.svg`](../icon-concepts/svg/C8_hex_trade_node.svg)
(kept in lockstep with `generate.py`). To regenerate, run `python3
export_icons.py`.

[`A1SI-AITP_icon_QA_sheet.png`](A1SI-AITP_icon_QA_sheet.png) is the
manual-review strip (512 → 32 px).

## What ships where

| Surface | Files | Consumed by |
|---|---|---|
| `web/` | `favicon-16/32/48`, `apple-touch-icon` (180), `icon-192`, `icon-512` | reference copies of the live web set |
| `ios/` | `AppIcon-*` set (20–1024 pt @1–3x) | a future native iOS build / App Store art |
| `android/` | `mipmap-mdpi … xxxhdpi`, `play-store-512` | a future native Android build / Play-Store art |
| **`frontend/public/`** | `favicon.png`, `favicon-16x16`, `favicon-32x32`, `apple-touch-icon`, `icon-192`, `icon-512`, `site.webmanifest` | **the live web app + mobile PWA** (wired in `frontend/index.html`) |

AITP has no native mobile project today, so the **live** surface is the web
app + mobile-web/PWA only; the `ios/` and `android/` sets are the design
record and the source for store art / a future native build. The maskable
`icon-192` / `icon-512` and `site.webmanifest` make Android/Chrome
add-to-homescreen and iOS apple-touch-icon resolve to the C8 mark.

## Palette

House A1SI navy squircle (`#1010C0`→`#00007B`→`#00004E`) + single glowing
cyan accent (`#00D4FF`/`#7AEEFF`), white/ice glyph — identical to the
CVWS / WIFI icons. The manifest `theme_color` is `#00007B`, `background_color`
is `#00004E`.
