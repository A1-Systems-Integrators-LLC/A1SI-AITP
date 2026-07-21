#!/usr/bin/env python3
"""
A1SI AITP — App-icon concept generator.

Emits 12 candidate app-icon concepts as 1024x1024 SVGs, organized into four
design families. Mirrors the A1SI-CVWS / A1SI-TERM / A1SI-WIFI branding
workflow (squircle + navy gradient + bold solid white glyph + shared cyan
"signal" accent) so AITP reads as part of the same A1SI house family.

Why this exists: AITP ships only a loose favicon.png / apple-touch-icon.png
in frontend/public/ — there is no concept set, no platform export, and the
art is not part of the house family. Every concept here uses the SAME house
construction as the sibling apps: SOLID filled white silhouettes, feature
sizes >= ~30px at 1024, no foreground opacity below 0.45, and a single
glowing cyan accent.

IMPORTANT — palette: the AITP *in-app* theme (slate/blue, being reworked)
is deliberately NOT used here. The icon set uses the A1SI **house** palette
shared by CVWS/TERM/WIFI/EMDT/CRM so all the apps sit together as one family
on a home screen. No green/red "trading" colors: the rising-trend story is
carried by candle height + the cyan glow, exactly how CVWS signals "active".

Run:  python3 generate.py      (writes svg/*.svg)
Then: ./render.sh              (rasterizes png/ + builds the QA sheets)

House icon palette (IDENTICAL to A1SI-CVWS / A1SI-WIFI):
  navy #00007B   navy-lift #1010C0   navy-deep #00004E   ice #E7E7FF
House signal accent (shared across the family):
  cyan #00D4FF / glow #7AEEFF
"""
import math
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "svg")
os.makedirs(OUT, exist_ok=True)

NAVY = "#00007B"

# ---- shared defs (identical house set to A1SI-CVWS) -------------------------
DEFS = """
  <defs>
    <linearGradient id="navyGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%"  stop-color="#1010C0"/>
      <stop offset="55%" stop-color="#00007B"/>
      <stop offset="100%" stop-color="#00004E"/>
    </linearGradient>
    <linearGradient id="navyGradDiag" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%"  stop-color="#1414D2"/>
      <stop offset="60%" stop-color="#00007B"/>
      <stop offset="100%" stop-color="#00004E"/>
    </linearGradient>
    <linearGradient id="cyanGrad" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#7AEEFF"/>
      <stop offset="100%" stop-color="#00D4FF"/>
    </linearGradient>
    <linearGradient id="steelGrad" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#FFFFFF"/>
      <stop offset="100%" stop-color="#E7E7FF"/>
    </linearGradient>
    <radialGradient id="innerLight" cx="0.32" cy="0.24" r="0.9">
      <stop offset="0%"  stop-color="#FFFFFF" stop-opacity="0.20"/>
      <stop offset="55%" stop-color="#FFFFFF" stop-opacity="0.05"/>
      <stop offset="100%" stop-color="#FFFFFF" stop-opacity="0"/>
    </radialGradient>
    <filter id="cyanGlow" x="-40%" y="-40%" width="180%" height="180%">
      <feGaussianBlur stdDeviation="13" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <filter id="softShadow" x="-25%" y="-25%" width="150%" height="150%">
      <feGaussianBlur in="SourceAlpha" stdDeviation="9"/>
      <feOffset dx="0" dy="7" result="o"/>
      <feComponentTransfer><feFuncA type="linear" slope="0.34"/></feComponentTransfer>
      <feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
"""

R = 225  # squircle corner radius (matches iOS / the rest of the A1SI family)


def squircle(grad="navyGrad"):
    return (
        f'<rect x="0" y="0" width="1024" height="1024" rx="{R}" ry="{R}" fill="url(#{grad})"/>\n'
        f'  <rect x="0" y="0" width="1024" height="1024" rx="{R}" ry="{R}" fill="url(#innerLight)"/>'
    )


def wrap(body, grad="navyGrad"):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" '
        'width="1024" height="1024">'
        + DEFS
        + "\n  "
        + squircle(grad)
        + "\n"
        + body
        + "\n</svg>\n"
    )


# ---- shared glyph parts -----------------------------------------------------

def baseline(y=726, x=150, w=724, h=42, fill="url(#cyanGrad)", glow=True):
    """The chart axis / ground bar — AITP's equivalent of the CVWS weighbridge
    deck: a single bold glowing bar the glyph stands on."""
    g = ' filter="url(#cyanGlow)"' if glow else ' filter="url(#softShadow)"'
    return (
        f'  <g{g}><rect x="{x}" y="{y}" width="{w}" height="{h}" '
        f'rx="{h / 2:.0f}" fill="{fill}"/></g>'
    )


def candle(cx, body_top, body_bot, wick_top, wick_bot, w=100, fill="#FFFFFF"):
    """A solid OHLC candlestick: wick behind, rounded body in front."""
    bw = 20
    return (
        f'  <g filter="url(#softShadow)">\n'
        f'    <rect x="{cx - bw / 2:.0f}" y="{wick_top}" width="{bw}" '
        f'height="{wick_bot - wick_top}" rx="{bw / 2:.0f}" fill="{fill}"/>\n'
        f'    <rect x="{cx - w / 2:.0f}" y="{body_top}" width="{w}" '
        f'height="{body_bot - body_top}" rx="22" fill="{fill}"/>\n'
        f'  </g>'
    )


def arrow(x1, y1, x2, y2, w=44, head=92, color="url(#cyanGrad)", glow=True):
    """A bold arrow from (x1,y1) to the tip (x2,y2) — round-capped shaft +
    filled triangular head. The hero 'up' element."""
    ang = math.atan2(y2 - y1, x2 - x1)
    bx = x2 - head * math.cos(ang)
    by = y2 - head * math.sin(ang)
    px, py = math.cos(ang + math.pi / 2), math.sin(ang + math.pi / 2)
    hw = head * 0.6
    g = "url(#cyanGlow)" if glow else "url(#softShadow)"
    return (
        f'  <g filter="{g}">\n'
        f'    <line x1="{x1:.0f}" y1="{y1:.0f}" x2="{bx:.0f}" y2="{by:.0f}" '
        f'stroke="{color}" stroke-width="{w}" stroke-linecap="round"/>\n'
        f'    <polygon points="{x2:.0f},{y2:.0f} '
        f'{bx + px * hw:.0f},{by + py * hw:.0f} '
        f'{bx - px * hw:.0f},{by - py * hw:.0f}" fill="{color}"/>\n'
        f'  </g>'
    )


def polyline(points, w=38, color="url(#cyanGrad)", glow=True):
    """A glowing multi-segment line through points (the trend / area edge)."""
    d = "M " + " L ".join(f"{x:.0f} {y:.0f}" for x, y in points)
    g = "url(#cyanGlow)" if glow else "url(#softShadow)"
    return (
        f'  <g filter="{g}"><path d="{d}" fill="none" stroke="{color}" '
        f'stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"/></g>'
    )


def wifi_arc(cx, cy, r, w, color, opacity=1.0):
    """A 90-deg signal arc (opening downward) — the shared A1SI house motif
    (TERM cursor glow / WIFI signal fan / CVWS live-weigh)."""
    k = math.sin(math.radians(45))
    xl, yl = cx - r * k, cy - r * k
    xr, yr = cx + r * k, cy - r * k
    op = f' stroke-opacity="{opacity}"' if opacity < 1 else ""
    return (
        f'<path d="M {xl:.1f} {yl:.1f} A {r} {r} 0 0 1 {xr:.1f} {yr:.1f}" '
        f'stroke="{color}" stroke-width="{w}" stroke-linecap="round" '
        f'fill="none"{op}/>'
    )


def hexagon(cx, cy, r):
    pts = []
    for i in range(6):
        a = math.radians(60 * i - 90)
        pts.append(f"{cx + r * math.cos(a):.1f},{cy + r * math.sin(a):.1f}")
    return " ".join(pts)


def ring_arc(cx, cy, r, a0, a1, w, color, glow=True):
    """A donut segment — stroked arc between two angles (radians)."""
    x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
    x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
    large = 1 if (a1 - a0) % (2 * math.pi) > math.pi else 0
    g = "url(#cyanGlow)" if glow else "url(#softShadow)"
    return (
        f'  <g filter="{g}"><path d="M {x0:.1f} {y0:.1f} A {r} {r} 0 {large} 1 '
        f'{x1:.1f} {y1:.1f}" fill="none" stroke="{color}" stroke-width="{w}" '
        f'stroke-linecap="round"/></g>'
    )


concepts = {}

# === FAMILY A — MARKETS (price action: the candlestick / chart story) ========

# A1 — Candlestick Rise: the canonical trading mark. Four solid candles
# stepping up on a glowing axis; the closing candle glows cyan. Lowest risk.
concepts["A1_candlestick_rise"] = wrap(
    candle(298, 520, 660, 478, 700)
    + "\n"
    + candle(446, 448, 596, 410, 636)
    + "\n"
    + candle(594, 372, 520, 336, 560)
    + "\n"
    + candle(742, 300, 452, 262, 492, fill="url(#cyanGrad)")
    + "\n"
    + baseline(y=726)
)

# A2 — Trend Breakout: a glowing cyan arrow punching up through a white
# resistance bar, small candles below. Adds motion — "a move is happening".
concepts["A2_trend_breakout"] = wrap(
    candle(320, 590, 690, 556, 712, w=72)
    + "\n"
    + candle(432, 560, 668, 524, 700, w=72)
    + "\n"
    '  <g filter="url(#softShadow)"><rect x="196" y="470" width="632" '
    'height="34" rx="17" fill="#FFFFFF"/></g>\n'
    + arrow(360, 712, 742, 300)
    + "\n"
    + baseline(y=772, x=190, w=644, h=36)
)

# A3 — Area Surge: a filled area/mountain chart climbing to a glowing cyan
# peak line — the portfolio-curve story, instantly readable at any size.
concepts["A3_area_surge"] = wrap(
    '  <g filter="url(#softShadow)"><path d="M 170 724 L 170 600 L 320 540 '
    'L 460 582 L 600 432 L 744 472 L 854 326 L 854 724 Z" '
    'fill="url(#steelGrad)" fill-opacity="0.92"/></g>\n'
    + polyline([(170, 600), (320, 540), (460, 582), (600, 432),
                (744, 472), (854, 326)], w=34)
    + "\n"
    '  <g filter="url(#cyanGlow)"><circle cx="854" cy="326" r="26" '
    'fill="url(#cyanGrad)"/></g>\n'
    + baseline(y=724)
)

# === FAMILY B — PORTFOLIO (the holdings / allocation / wealth story) =========

# B4 — Allocation Ring: a heavy white donut with one glowing cyan segment and
# a cyan up-tick at its heart — diversification + growth. Pure badge, no axis.
concepts["B4_allocation_ring"] = wrap(
    '  <g filter="url(#softShadow)"><circle cx="512" cy="500" r="244" '
    'fill="none" stroke="#FFFFFF" stroke-width="128"/></g>\n'
    + ring_arc(512, 500, 244, math.radians(-104), math.radians(20), 128,
               "url(#cyanGrad)")
    + "\n"
    + arrow(512, 600, 512, 412, w=40, head=82)
)

# B5 — Coin Stack: three stacks of asset coins growing left-to-right, the
# tallest crowned by a glowing cyan coin + up-arrow. Accumulation of holdings.
def _coins():
    out = []
    stacks = [(304, 2), (512, 3), (720, 5)]
    for sx, n in stacks:
        for i in range(n):
            cy = 690 - i * 52
            top = (sx == 720 and i == n - 1)
            fill = "url(#cyanGrad)" if top else "url(#steelGrad)"
            g = "url(#cyanGlow)" if top else "url(#softShadow)"
            out.append(
                f'  <g filter="{g}"><ellipse cx="{sx}" cy="{cy}" rx="80" '
                f'ry="26" fill="{fill}"/></g>'
            )
    return "\n".join(out)


concepts["B5_coin_stack"] = wrap(
    baseline(y=730, x=170, w=684, h=36, fill="url(#cyanGrad)")
    + "\n"
    + _coins()
    + "\n"
    + arrow(720, 470, 720, 318, w=38, head=78)
)

# B6 — Secure Growth: a custody shield with a glowing cyan trend climbing
# inside — protected capital that compounds. The trust / safekeeping angle.
concepts["B6_secure_growth"] = wrap(
    '  <g filter="url(#softShadow)"><path d="M 512 248 L 760 332 L 760 540 '
    'Q 760 724 512 802 Q 264 724 264 540 L 264 332 Z" fill="url(#steelGrad)"/></g>\n'
    + arrow(348, 612, 676, 392, w=40, head=82)
    + "\n"
    + polyline([(348, 612), (452, 556), (560, 500)], w=40)
)

# === FAMILY C — AI SIGNAL (what makes AITP: ML signals, automation, live data)

# C7 — AI Pulse: the house signal fan rising off the candles — AI-driven
# signals streamed live. Strongest single-glyph tie to the TERM/WIFI/CVWS
# house motif.
concepts["C7_ai_pulse"] = wrap(
    '  <g filter="url(#softShadow)">\n'
    f'    {wifi_arc(512, 384, 206, 54, "#FFFFFF")}\n'
    f'    {wifi_arc(512, 384, 120, 54, "#FFFFFF")}\n'
    "  </g>\n"
    '  <g filter="url(#cyanGlow)"><circle cx="512" cy="384" r="30" '
    'fill="url(#cyanGrad)"/></g>\n'
    + candle(414, 596, 700, 566, 724, w=78)
    + "\n"
    + candle(512, 552, 672, 520, 700, w=78)
    + "\n"
    + candle(610, 506, 648, 474, 676, w=78, fill="url(#cyanGrad)")
    + "\n"
    + baseline(y=748, x=300, w=424, h=34)
)

# C8 — Hex Trade Node: candlesticks framed in the hexagon badge — the
# deliberate sibling of TERM/CVWS/WIFI "Hex Node". Pick this for one
# recognizable A1SI shelf identity, only the inner glyph changing per app.
concepts["C8_hex_trade_node"] = wrap(
    '  <g filter="url(#softShadow)">\n'
    f'    <polygon points="{hexagon(512, 512, 330)}" fill="#FFFFFF" '
    'fill-opacity="0.10" stroke="#FFFFFF" stroke-width="18" '
    'stroke-linejoin="round" stroke-opacity="0.9"/>\n'
    "  </g>\n"
    + candle(430, 512, 600, 482, 624, w=64)
    + "\n"
    + candle(512, 466, 576, 436, 600, w=64)
    + "\n"
    + candle(594, 420, 540, 390, 566, w=64, fill="url(#cyanGrad)")
    + "\n"
    + baseline(y=636, x=372, w=280, h=28),
    grad="navyGradDiag",
)

# C9 — Neural Trend: an ML node network resolving into a glowing up-trend —
# the FreqAI / multi-tier automation story nobody else in the family tells.
def _net():
    inp = [(316, 384), (316, 512), (316, 640)]
    hub = (520, 512)
    edges = "\n".join(
        f'    <line x1="{x}" y1="{y}" x2="{hub[0]}" y2="{hub[1]}" '
        'stroke="#FFFFFF" stroke-width="16" stroke-linecap="round" '
        'stroke-opacity="0.85"/>'
        for x, y in inp
    )
    nodes = "\n".join(
        f'  <g filter="url(#cyanGlow)"><circle cx="{x}" cy="{y}" r="34" '
        'fill="url(#cyanGrad)"/></g>'
        for x, y in inp
    )
    return (
        f'  <g filter="url(#softShadow)">\n{edges}\n  </g>\n'
        + nodes
        + f'\n  <g filter="url(#softShadow)"><circle cx="{hub[0]}" cy="{hub[1]}" '
        'r="40" fill="#FFFFFF"/></g>'
    )


concepts["C9_neural_trend"] = wrap(
    _net()
    + "\n"
    + arrow(520, 512, 808, 300, w=40, head=84)
)

# === FAMILY D — MARK (monogram / abstract pictogram; most ownable) ===========

# D10 — A Monogram: a heavyweight "A" (A1SI / AITP) standing on the glowing
# axis, its apex the peak of the climb. Trademark-friendly, unmistakable.
concepts["D10_a_monogram"] = wrap(
    '  <g filter="url(#softShadow)" fill="none" stroke="#FFFFFF" '
    'stroke-width="86" stroke-linecap="round" stroke-linejoin="round">\n'
    '    <path d="M 330 716 L 512 300 L 694 716"/>\n'
    '    <path d="M 406 528 L 618 528"/>\n'
    "  </g>\n"
    + baseline(y=772, x=246, w=532, h=42),
    grad="navyGradDiag",
)

# D11 — Up Arrow Glyph: an abstract upward arrow built from candle segments —
# a glowing cyan head over a white candlestick shaft. The cleanest 24px read;
# a strong favicon / monochrome glyph even if not chosen as the app icon.
concepts["D11_up_arrow_glyph"] = wrap(
    '  <g filter="url(#cyanGlow)"><polygon points="512,244 350,440 674,440" '
    'fill="url(#cyanGrad)"/></g>\n'
    '  <g filter="url(#softShadow)">\n'
    '    <rect x="450" y="452" width="124" height="98" rx="26" fill="#FFFFFF"/>\n'
    '    <rect x="450" y="566" width="124" height="98" rx="26" fill="#FFFFFF"/>\n'
    '    <rect x="450" y="680" width="124" height="98" rx="26" fill="#FFFFFF"/>\n'
    "  </g>"
)

# D12 — Bull Mark: an abstract bull — two horns sweeping up off a bold head,
# glowing cyan eyes. The bull-market mark; most ownable, least literal.
concepts["D12_bull_mark"] = wrap(
    '  <g filter="url(#softShadow)" fill="none" stroke="#FFFFFF" '
    'stroke-width="68" stroke-linecap="round">\n'
    '    <path d="M 404 506 C 312 446 286 366 300 288"/>\n'
    '    <path d="M 620 506 C 712 446 738 366 724 288"/>\n'
    "  </g>\n"
    '  <g filter="url(#softShadow)"><path d="M 512 744 Q 360 720 352 568 '
    'L 352 512 Q 352 474 392 474 L 632 474 Q 672 474 672 512 L 672 568 '
    'Q 664 720 512 744 Z" fill="url(#steelGrad)"/></g>\n'
    '  <g filter="url(#cyanGlow)">\n'
    '    <circle cx="452" cy="600" r="30" fill="url(#cyanGrad)"/>\n'
    '    <circle cx="572" cy="600" r="30" fill="url(#cyanGrad)"/>\n'
    "  </g>",
    grad="navyGradDiag",
)

for name, svg in concepts.items():
    with open(os.path.join(OUT, f"{name}.svg"), "w") as f:
        f.write(svg)

print(f"wrote {len(concepts)} concept SVGs to {OUT}")
for n in concepts:
    print(" -", n)
