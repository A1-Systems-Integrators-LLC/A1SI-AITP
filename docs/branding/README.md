# A1SI AITP — Branding & App-Icon Concepts

This folder holds the design exploration for the AITP app icon. It follows
the same workflow as the sibling A1SI apps —
[A1SI-CVWS](../../../A1SI-CVWS/docs/branding/README.md),
A1SI-TERM and A1SI-WIFI — so all the apps stay a visible family on a home
screen, with only the central glyph changing per product.

## Current icon — C8 "Hex Trade Node" (selected June 2026)

Concept **C8** is the chosen icon: the A1SI **hexagon badge** (the sibling of
the CVWS / TERM / WIFI "Hex Node") with the rising-candlestick glyph inside,
so AITP now sits next to the other apps as one visible family — only the
central glyph changes per product.

It is exported to every consuming surface by
[`icon-concepts/export_icons.py`](icon-concepts/export_icons.py). Reference
copies of every size live in [`icons/`](icons/) (web / iOS / Android) with
[`icons/A1SI-AITP_icon_QA_sheet.png`](icons/A1SI-AITP_icon_QA_sheet.png) for
manual visual QA — see [`icons/README.md`](icons/README.md) for the full
what-ships-where table. The live web app
([`frontend/public/`](../../frontend/public/)) carries the favicons,
apple-touch-icon, maskable PWA icons and `site.webmanifest`, wired up in
[`frontend/index.html`](../../frontend/index.html).

To regenerate the full set after tweaking the C8 art in `generate.py`:

```bash
cd docs/branding/icon-concepts
./render.sh            # refresh concept SVGs + PNGs
python3 export_icons.py
```

The selection itself was made from
[`icon-concepts/A1SI-AITP_icon_sample_sheet.html`](icon-concepts/A1SI-AITP_icon_sample_sheet.html)
(rendered [`.png`](icon-concepts/A1SI-AITP_icon_sample_sheet.png) /
[`.pdf`](icon-concepts/A1SI-AITP_icon_sample_sheet.pdf)); the other 11
concepts stay there as the design record and as candidates for sibling apps.

## The house construction

Every concept applies the shared A1SI house construction (identical to the
shipped CVWS / WIFI icons):

- gradient **navy** squircle background (lift `#1010C0` → primary `#00007B`
  → deep `#00004E`) with an inner radial highlight,
- **solid filled** white silhouettes — no hairline outlines, no foreground
  opacity below 0.45, feature sizes ≥ ~30px at 1024,
- a single glowing **cyan** accent (`#00D4FF` / `#7AEEFF`) — the house
  "signal" accent shared across the family.

> **Palette note (per the brief):** the AITP *in-app* theme (slate/blue,
> currently being reworked) is deliberately **not** used for the icon. The
> icon art uses the A1SI **house** palette so AITP matches the other apps —
> exactly how CVWS keeps house navy+cyan for its icon while its in-app theme
> stays its own. There is no green/red "trading" color: the rising-trend
> story is carried by candle height and the cyan glow.

## The concepts

12 candidates live in [`icon-concepts/`](icon-concepts/), grouped into four
families.

| Code | Name | Family | One-liner |
|---|---|---|---|
| A1 | Candlestick Rise | Markets | Four solid OHLC candles stepping up on a glowing axis |
| A2 | Trend Breakout | Markets | Cyan arrow punching up through a white resistance bar |
| A3 | Area Surge | Markets | Filled equity-curve area climbing to a glowing peak |
| B4 | Allocation Ring | Portfolio | White donut + one glowing cyan segment + up-tick |
| B5 | Coin Stack | Portfolio | Three stacks of asset coins growing, cyan-crowned |
| B6 | Secure Growth | Portfolio | Custody shield with a glowing trend climbing inside |
| C7 | AI Pulse | AI Signal | House signal fan rising off the candles |
| C8 | Hex Trade Node | AI Signal | Hexagon badge — sibling of CVWS/TERM/WIFI "Hex Node" |
| C9 | Neural Trend | AI Signal | ML node network resolving into a glowing up-trend |
| D10 | A Monogram | Mark | Heavyweight "A" (A1SI / AITP) on the glowing axis |
| D11 | Up Arrow Glyph | Mark | Abstract up-arrow from candle segments — cleanest 24px |
| D12 | Bull Mark | Mark | Abstract bull — horns sweeping up, glowing cyan eyes |

### Recommendation (design + marketing, for selection)

- **Primary: A1 "Candlestick Rise"** — the universal "markets / trading app"
  mark; zero re-learning, maximum legibility, safe default.
- **Differentiation: C7 "AI Pulse"** — foregrounds what makes AITP different
  (AI-driven, automated, live) and is the tightest tie to the house motif.
- **Family: C8 "Hex Trade Node"** — adopt the hexagon badge to make the A1SI
  apps visible siblings on a home screen.
- **Ownable: D10 "A Monogram" / D11 "Up Arrow Glyph"** — most
  trademark-friendly; D11 also doubles as the cleanest favicon.

## Palette

| Token | Hex | Use |
|---|---|---|
| `navy` | `#00007B` | House icon navy — the A1SI logo navy (= A1SI-CVWS/WIFI) |
| `navy-lift` | `#1010C0` | Gradient highlight |
| `navy-deep` | `#00004E` | Gradient terminus / depth |
| `ice` | `#E7E7FF` | Soft foreground fills (area/coin/shield gradients) |
| `cyan` | `#00D4FF` | Signal accent — **shared across the A1SI family** |
| `cyan-glow` | `#7AEEFF` | Cyan highlight stop |
| `white` | `#FFFFFF` | Primary glyph |

## Reproducing the renders

Everything is generated from source — no binary art is hand-edited.

```bash
cd docs/branding/icon-concepts
./render.sh          # regenerates svg/, png/, and both QA sheets
```

Requires `python3`, `rsvg-convert` (`brew install librsvg`), and ImageMagick
(`brew install imagemagick`). Edit
[`icon-concepts/generate.py`](icon-concepts/generate.py) to tweak a concept;
it is the single source for all 12 SVGs. The sample-sheet PNG/PDF are
rasterized from the HTML with headless Chrome.

## After a concept is selected

Set `CONCEPT` in
[`icon-concepts/export_icons.py`](icon-concepts/export_icons.py) to the
winning code and run it. It renders the chosen master to every consuming
surface — web favicons, iOS AppIcon set, Android mipmaps + Play-Store art —
into [`icons/`](icons/) (created on first run) and refreshes the live
`frontend/public/favicon.png` + `apple-touch-icon.png`. Keep `CONCEPT`
pointing at the selected `svg/*.svg` so the export never drifts from the
design.
