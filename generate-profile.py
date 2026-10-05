#!/usr/bin/env python3
"""
generate_profile.py - animated, self-contained SVGs for a GitHub profile README.

Creates (pure SMIL, no CSS/JS, no external assets):
  github-contribution-animation.svg   53x7 calendar, diagonal slant reveal + glint
  terminal-card.svg                   ASCII avatar in a macOS terminal + `whoami`
  info-card.svg                       neofetch-style card, staggered slide-up lines
and injects them into README.md between two marker comments.

Usage:
  pip install pillow
  python generate_profile.py --username YOUR_GITHUB_USERNAME
  GITHUB_TOKEN=ghp_xxx python generate_profile.py --username YOUR_GITHUB_USERNAME   # real contributions

Options:
  --avatar PATH   use a local image instead of downloading the GitHub avatar
  --invert        flip ASCII brightness (use if your avatar has a bright background)
  --out DIR       where to write SVGs (default: current dir)
  --readme PATH   README to update (default: ./README.md)
  --no-readme     only write the SVGs
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import math
import os
import random
import re
import sys
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

try:
    from PIL import Image, ImageEnhance, ImageOps
except ImportError:
    sys.exit("Pillow is required:  pip install pillow")

# --------------------------------------------------------------------------- #
# EDIT ME: content for the info card
# --------------------------------------------------------------------------- #
PROFILE = {
    "name": "Rishabh Tiwari",
    "about": [
        ("Name", "Rishabh Tiwari"),
        ("Role", "Full Stack Developer"),
        ("Education", "B.E. Comp. Engg · AKTU '28"),
        ("Location", "Delhi, India"),
        ("Status", "● Open to work"),
    ],
    "stack": [
        ("Frontend", "React.js · TypeScript"),
        ("Backend", "Node · Express · FastAPI"),
        ("Data", "PostgreSQL · MongoDB · Redis"),
        ("Infra", "Docker · Prisma · BullMQ · Firebase"),
        ("Realtime", "WebSockets · WebRTC"),
    ],
    "highlights": [
        ("Hackathon", "HackerCup Grand Finalist"),
        ("Project", "AstroTrack · satellite tracking"),
        ("Project", "Acousta · LAN audio via WebRTC"),
        ("Project", "ReachInbox · email scheduler"),
    ],
}

# --------------------------------------------------------------------------- #
# Palette & shared layout
# --------------------------------------------------------------------------- #
BG = "#0d1117"
CYAN, GREEN, ORANGE = "#00e5ff", "#39ff88", "#ff9e3d"
PURPLE, BLUE = "#b388ff", "#79c0ff"
WHITE, MUTED = "#e6edf3", "#8b949e"
FONT = "'JetBrains Mono','Fira Code','SF Mono',Menlo,Consolas,'DejaVu Sans Mono','Liberation Mono',monospace"
UA = "profile-readme-generator/1.0"

TB = 34  # title-bar height of every "window"

# ASCII portrait geometry (a monospace glyph is ~0.6 x font-size wide)
COLS, FS = 76, 8
CW, LH = FS * 0.6, 8.4
ROWS = round(COLS * CW / LH)
AW, AH = COLS * CW, ROWS * LH
TERM_W = int(AW + 2 * 32)
AX = (TERM_W - AW) / 2
AY = 10 + TB + 18
FOOT_Y1 = AY + AH + 30
FOOT_Y2 = FOOT_Y1 + 22
CARD_H = int(FOOT_Y2 + 28)  # terminal + info card share this height
INFO_W = round(TERM_W * 0.48 / 0.52)  # README table splits ~52/48

RAMP = " .`'^\",:;Il!i><~+_-?][}{1)(|/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"

# Contribution levels 0-4 (4 = neon), and the colour each cell flashes from
LEVEL_COLORS = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39ff88"]
FLASH_COLORS = ["#2d3543", "#c8ffe0", "#e6fff0", "#ffffff", "#ffffff"]
CELL, GAP = 12, 3
PITCH = CELL + GAP


# --------------------------------------------------------------------------- #
# Shared SVG pieces
# --------------------------------------------------------------------------- #
def svg_open(w: int, h: int, title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}">\n'
        f"<title>{escape(title)}</title>\n"
    )


def common_defs(extra: str = "") -> str:
    return f"""<defs>
  <linearGradient id="edge" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{CYAN}" stop-opacity=".8"/>
    <stop offset=".5" stop-color="#ffffff" stop-opacity=".08"/>
    <stop offset="1" stop-color="{PURPLE}" stop-opacity=".8"/>
  </linearGradient>
  <linearGradient id="glass" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#1b2230" stop-opacity=".93"/>
    <stop offset="1" stop-color="#0d1117" stop-opacity=".95"/>
  </linearGradient>
  <radialGradient id="spec" cx=".15" cy="0" r="1">
    <stop offset="0" stop-color="#ffffff" stop-opacity=".10"/>
    <stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
  </radialGradient>
  <filter id="blur" x="-20%" y="-20%" width="140%" height="140%">
    <feGaussianBlur stdDeviation="12"/>
  </filter>
{extra}</defs>
"""


def frame(w: int, h: int, title: str) -> str:
    cy = 10 + TB / 2
    return f"""<rect width="{w}" height="{h}" rx="18" fill="{BG}"/>
<rect x="14" y="14" width="{w-28}" height="{h-28}" rx="16" fill="none" stroke="url(#edge)" stroke-width="3" filter="url(#blur)" opacity=".5">
  <animate attributeName="opacity" values=".3;.7;.3" dur="6s" repeatCount="indefinite"/>
</rect>
<rect x="10" y="10" width="{w-20}" height="{h-20}" rx="14" fill="url(#glass)" stroke="url(#edge)" stroke-width="1.2"/>
<rect x="10" y="10" width="{w-20}" height="{h-20}" rx="14" fill="url(#spec)"/>
<path d="M10 {10+TB} V24 a14 14 0 0 1 14 -14 H{w-24} a14 14 0 0 1 14 14 V{10+TB} Z" fill="#ffffff" fill-opacity=".04"/>
<line x1="10" y1="{10+TB}" x2="{w-10}" y2="{10+TB}" stroke="#ffffff" stroke-opacity=".08"/>
<circle cx="30" cy="{cy}" r="5.5" fill="#ff5f56"/>
<circle cx="48" cy="{cy}" r="5.5" fill="#ffbd2e"/>
<circle cx="66" cy="{cy}" r="5.5" fill="#27c93f"/>
<text x="{w/2}" y="{cy+4}" text-anchor="middle" font-family="{FONT}" font-size="11.5" fill="{MUTED}">{escape(title)}</text>
"""


# --------------------------------------------------------------------------- #
# 1) Contribution graph
# --------------------------------------------------------------------------- #
def calendar_start(today: dt.date) -> dt.date:
    days_since_sunday = (today.weekday() + 1) % 7
    return today - dt.timedelta(days=days_since_sunday) - dt.timedelta(weeks=52)


def fetch_contributions(username: str, token: str):
    query = (
        "query($u:String!){user(login:$u){contributionsCollection{contributionCalendar{"
        "totalContributions weeks{contributionDays{date contributionLevel}}}}}}"
    )
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": {"u": username}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json", "User-Agent": UA},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    cal = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    lv = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}
    levels = {}
    for week in cal["weeks"]:
        for day in week["contributionDays"]:
            levels[dt.date.fromisoformat(day["date"])] = lv[day["contributionLevel"]]
    return levels, cal["totalContributions"]


def synthetic_contributions(start: dt.date, today: dt.date, seed: str):
    """Plausible-looking placeholder data (used when no GITHUB_TOKEN is available)."""
    rng = random.Random(seed)
    levels, i, d = {}, 0, start
    while d <= today:
        base = 0.55 + 0.35 * math.sin(i / 9.0) + 0.2 * math.sin(i / 3.7)
        if d.weekday() >= 5:
            base -= 0.3
        v = base + rng.uniform(-0.35, 0.35)
        levels[d] = 0 if v < 0.25 else 1 if v < 0.5 else 2 if v < 0.72 else 3 if v < 0.9 else 4
        d += dt.timedelta(days=1)
        i += 1
    return levels


def make_contrib_svg(levels: dict, total: int | None, today: dt.date) -> str:
    start = calendar_start(today)
    GX, GY = 56, 10 + TB + 30
    grid_w, grid_h = 53 * PITCH - GAP, 7 * PITCH - GAP
    W, H = GX + grid_w + 34, int(GY + 7 * PITCH + 40)

    title = "~/contributions" + (f" — {total:,} in the last year" if total is not None else "")
    reveal_step, reveal_start = 0.04, 0.4

    base_cells, glow_cells = [], []
    for col in range(53):
        for row in range(7):
            d = start + dt.timedelta(days=col * 7 + row)
            if d > today:
                continue
            lvl = levels.get(d, 0)
            c, flash = LEVEL_COLORS[lvl], FLASH_COLORS[lvl]
            x, y = GX + col * PITCH, GY + row * PITCH
            t = reveal_start + (col + (6 - row)) * reveal_step  # bottom-left -> top-right
            rect = (
                f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="3" fill="{c}" opacity="0">'
                f'<animate attributeName="opacity" from="0" to="1" begin="{t:.2f}s" dur="0.15s" fill="freeze"/>'
                f'<animate attributeName="fill" values="{flash};{flash};{c}" keyTimes="0;0.2;1" '
                f'begin="{t:.2f}s" dur="0.75s" fill="freeze"/></rect>'
            )
            (glow_cells if lvl >= 3 else base_cells).append(rect)
    reveal_end = reveal_start + 58 * reveal_step + 0.8

    # month labels
    months, last_m, last_c = [], None, -10
    for col in range(53):
        d = start + dt.timedelta(days=col * 7)
        if d.month != last_m:
            if col - last_c >= 3:
                months.append(f'<text x="{GX + col * PITCH}" y="{GY - 9}" font-size="10" fill="{MUTED}">{d.strftime("%b")}</text>')
                last_c = col
            last_m = d.month
    days = "".join(
        f'<text x="{GX - 10}" y="{GY + r * PITCH + 10}" font-size="10" text-anchor="end" fill="{MUTED}">{n}</text>'
        for r, n in ((1, "Mon"), (3, "Wed"), (5, "Fri"))
    )

    # legend (bottom right)
    ly = GY + 7 * PITCH + 14
    right = GX + grid_w
    legend = f'<text x="{right - 5*PITCH - 62}" y="{ly + 9}" font-size="10" text-anchor="end" fill="{MUTED}">Less</text>'
    for i, col_ in enumerate(LEVEL_COLORS):
        legend += f'<rect x="{right - 5*PITCH - 54 + i*PITCH}" y="{ly}" width="{CELL}" height="{CELL}" rx="3" fill="{col_}"/>'
    legend += f'<text x="{right - 5*PITCH + 26 + 4*0}" y="{ly + 9}" font-size="10" fill="{MUTED}">More</text>'

    extra = f"""  <filter id="cellGlow" x="-5%" y="-20%" width="110%" height="140%">
    <feGaussianBlur in="SourceGraphic" stdDeviation="3.2" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <clipPath id="gridClip"><rect x="{GX-2}" y="{GY-2}" width="{grid_w+4}" height="{grid_h+4}"/></clipPath>
  <linearGradient id="shine" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#ffffff" stop-opacity="0"/>
    <stop offset=".5" stop-color="#9dffd0" stop-opacity=".17"/>
    <stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
  </linearGradient>
"""
    band_h = grid_h
    shine = f"""<g clip-path="url(#gridClip)">
  <polygon points="0,0 70,0 {70+band_h},{band_h} {band_h},{band_h}" fill="url(#shine)" transform="translate(-320 {GY})">
    <animateTransform attributeName="transform" type="translate" values="-320 {GY};{W+60} {GY};{W+60} {GY}" keyTimes="0;0.4;1" dur="10s" begin="{reveal_end + 1.2:.2f}s" repeatCount="indefinite"/>
  </polygon>
</g>"""

    return (
        svg_open(W, H, "GitHub contribution graph")
        + common_defs(extra)
        + frame(W, H, title)
        + f'<g font-family="{FONT}">{"".join(months)}{days}</g>\n'
        + f'<g>{"".join(base_cells)}</g>\n'
        + f'<g filter="url(#cellGlow)">{"".join(glow_cells)}</g>\n'
        + shine
        + f'\n<g font-family="{FONT}">{legend}</g>\n</svg>\n'
    )


# --------------------------------------------------------------------------- #
# 2) ASCII terminal card
# --------------------------------------------------------------------------- #
def load_avatar(username: str, local: str | None) -> Image.Image:
    if local:
        img = Image.open(local)
    else:
        req = urllib.request.Request(f"https://github.com/{username}.png?size=460", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            img = Image.open(io.BytesIO(r.read()))
    img.load()
    return img


def avatar_to_ascii(img: Image.Image, invert: bool = False) -> list[str]:
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    bg = Image.new("RGBA", img.size, (13, 17, 23, 255))
    bg.alpha_composite(img)
    img = bg.convert("L")
    w, h = img.size
    s = min(w, h)
    left, top = (w - s) // 2, (h - s) // 2
    img = img.crop((left, top, left + s, top + s))
    img = ImageOps.autocontrast(img, cutoff=2)
    img = ImageEnhance.Contrast(img).enhance(1.2)
    img = img.resize((COLS, ROWS), Image.LANCZOS)
    if invert:
        img = ImageOps.invert(img)
    px, n = img.load(), len(RAMP) - 1
    return [
        "".join(RAMP[int((px[x, y] / 255) ** 0.9 * n)] for x in range(COLS))
        for y in range(ROWS)
    ]


def typed_text(x, y, segments, t0, step, font_size=13, cursor=False):
    """Typewriter line: one hidden <tspan> per character, revealed with <set>."""
    parts, t = [], t0
    for txt, color, bold in segments:
        weight = ' font-weight="700"' if bold else ""
        for ch in txt:
            parts.append(
                f'<tspan fill="{color}"{weight} visibility="hidden">{escape(ch)}'
                f'<set attributeName="visibility" to="visible" begin="{t:.2f}s" fill="freeze"/></tspan>'
            )
            t += step
    if cursor:
        parts.append(
            f'<tspan fill="#ffffff" visibility="hidden">█'
            f'<animate attributeName="visibility" values="visible;hidden" calcMode="discrete" '
            f'dur="1.1s" begin="{t + 0.05:.2f}s" repeatCount="indefinite"/></tspan>'
        )
    svg = (
        f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{font_size}" xml:space="preserve">'
        + "".join(parts)
        + "</text>"
    )
    return svg, t


def make_terminal_svg(lines: list[str], username: str, name: str) -> str:
    t0, rd = 0.5, 0.075
    clips, texts, cursors = [], [], []
    for i, line in enumerate(lines):
        ry, t = AY + i * LH, t0 + i * rd
        clips.append(
            f'<clipPath id="r{i}"><rect x="{AX:.2f}" y="{ry:.2f}" width="0" height="{LH}">'
            f'<animate attributeName="width" from="{CW}" to="{AW:.2f}" begin="{t:.3f}s" dur="{rd}s" fill="freeze"/>'
            f"</rect></clipPath>"
        )
        texts.append(
            f'<text x="{AX:.2f}" y="{ry + FS - 0.8:.2f}" textLength="{AW:.2f}" lengthAdjust="spacing" '
            f'clip-path="url(#r{i})">{escape(line)}</text>'
        )
        cursors.append(
            f'<rect x="{AX:.2f}" y="{ry:.2f}" width="{CW}" height="{LH}" fill="#ffffff" opacity="0">'
            f'<set attributeName="opacity" to="0.95" begin="{t:.3f}s"/>'
            f'<animate attributeName="x" from="{AX:.2f}" to="{AX + AW - CW:.2f}" begin="{t:.3f}s" dur="{rd}s" fill="freeze"/>'
            f'<set attributeName="opacity" to="0" begin="{t + rd:.3f}s"/></rect>'
        )
    ascii_end = t0 + ROWS * rd

    who, t1 = typed_text(
        AX, FOOT_Y1, [("$ ", GREEN, True), ("whoami", WHITE, False)], ascii_end + 0.5, 0.09
    )
    nm, _ = typed_text(
        AX, FOOT_Y2, [(name, CYAN, True)], t1 + 0.45, 0.06, cursor=True
    )

    extra = f"""  <linearGradient id="asciiGrad" gradientUnits="userSpaceOnUse" x1="0" y1="{AY:.1f}" x2="0" y2="{AY + AH:.1f}">
    <stop offset="0" stop-color="{CYAN}"/>
    <stop offset=".55" stop-color="{GREEN}"/>
    <stop offset="1" stop-color="{PURPLE}"/>
  </linearGradient>
  <radialGradient id="portraitGlow">
    <stop offset="0" stop-color="{CYAN}" stop-opacity=".16"/>
    <stop offset="1" stop-color="{CYAN}" stop-opacity="0"/>
  </radialGradient>
  {"".join(clips)}
"""
    return (
        svg_open(TERM_W, CARD_H, f"ASCII portrait of {username}")
        + common_defs(extra)
        + frame(TERM_W, CARD_H, f"{username.lower()}@github: ~/portrait — zsh")
        + f'<ellipse cx="{TERM_W/2}" cy="{AY + AH/2:.1f}" rx="{AW*0.62:.1f}" ry="{AH*0.58:.1f}" fill="url(#portraitGlow)"/>\n'
        + f'<g font-family="{FONT}" font-size="{FS}" fill="url(#asciiGrad)" xml:space="preserve">{"".join(texts)}</g>\n'
        + "".join(cursors)
        + f'\n<line x1="{AX:.1f}" y1="{AY + AH + 10:.1f}" x2="{AX + AW:.1f}" y2="{AY + AH + 10:.1f}" '
        f'stroke="#ffffff" stroke-opacity=".18" stroke-dasharray="3 4"/>\n'
        + who
        + "\n"
        + nm
        + "\n</svg>\n"
    )


# --------------------------------------------------------------------------- #
# 3) Neofetch info card
# --------------------------------------------------------------------------- #
def make_info_svg(handle: str, profile: dict) -> str:
    W, H = INFO_W, CARD_H
    X, VX, FSZ = 32, 118, 11.5

    def kv(k, v, vcolor=WHITE):
        return (
            f'<tspan fill="{CYAN}">{escape(k)}</tspan>'
            f'<tspan x="{VX}" fill="{vcolor}">{escape(v)}</tspan>'
        )

    def section(label, color):
        return f'<tspan fill="{color}" font-weight="700">:: {escape(label)}</tspan>'

    rows = [
        ("text", f'<tspan fill="{CYAN}" font-weight="700">{escape(handle)}</tspan>'
                 f'<tspan fill="{WHITE}">@</tspan><tspan fill="{GREEN}" font-weight="700">github</tspan>'),
        ("rule", ""),
        ("blank", ""),
        ("text", section("About", ORANGE)),
    ]
    for k, v in profile["about"]:
        rows.append(("text", kv(k, v, GREEN if k == "Status" else WHITE)))
    rows += [("blank", ""), ("text", section("Stack", BLUE))]
    rows += [("text", kv(k, v)) for k, v in profile["stack"]]
    rows += [("blank", ""), ("text", section("Highlights", GREEN))]
    rows += [("text", kv(k, v)) for k, v in profile["highlights"]]
    rows += [
        ("blank", ""),
        ("palette", ""),
        ("text", f'<tspan fill="{GREEN}">$</tspan><tspan fill="#ffffff" xml:space="preserve"> █'
                 f'<animate attributeName="visibility" values="visible;hidden" calcMode="discrete" '
                 f'dur="1.1s" repeatCount="indefinite"/></tspan>'),
    ]

    top = 10 + TB + 16
    pitch = min(18.0, (H - top - 38) / len(rows))
    out = []
    for i, (kind, payload) in enumerate(rows):
        if kind == "blank":
            continue
        y = top + i * pitch + 12
        begin = 0.45 + i * 0.06  # staggered 0.06s per row
        if kind == "text":
            body = f'<text x="{X}" y="{y:.1f}" font-size="{FSZ}" xml:space="preserve">{payload}</text>'
        elif kind == "rule":
            body = f'<line x1="{X}" y1="{y - 4:.1f}" x2="{W - X}" y2="{y - 4:.1f}" stroke="{CYAN}" stroke-opacity=".35"/>'
        else:  # palette
            swatches = [CYAN, GREEN, ORANGE, PURPLE, BLUE, WHITE]
            body = "".join(
                f'<rect x="{X + j * 22}" y="{y - 9:.1f}" width="18" height="10" rx="2" fill="{c}"/>'
                for j, c in enumerate(swatches)
            )
        out.append(
            f'<g opacity="0">{body}'
            f'<animate attributeName="opacity" from="0" to="1" begin="{begin:.2f}s" dur="0.4s" fill="freeze"/>'
            f'<animateTransform attributeName="transform" type="translate" from="0 10" to="0 0" '
            f'begin="{begin:.2f}s" dur="0.4s" fill="freeze" calcMode="spline" keyTimes="0;1" keySplines="0.16 1 0.3 1"/></g>'
        )

    return (
        svg_open(W, H, "Developer info card")
        + common_defs()
        + frame(W, H, "neofetch")
        + f'<g font-family="{FONT}">' + "\n".join(out) + "</g>\n</svg>\n"
    )


# --------------------------------------------------------------------------- #
# README injection
# --------------------------------------------------------------------------- #
START, END = "<!-- PROFILE-CARDS:START -->", "<!-- PROFILE-CARDS:END -->"


def readme_block(alt_name: str) -> str:
    pct_term = round(TERM_W / (TERM_W + INFO_W) * 100, 1)
    pct_info = round(100 - pct_term, 1)
    return f"""<div align="center">
<table>
  <tr>
    <td width="{pct_term}%" valign="top"><img src="./terminal-card.svg" width="100%" alt="{escape(alt_name)} ASCII terminal portrait"/></td>
    <td width="{pct_info}%" valign="top"><img src="./info-card.svg" width="100%" alt="{escape(alt_name)} developer info"/></td>
  </tr>
</table>
<br/>
<img src="./github-contribution-animation.svg" width="100%" alt="GitHub contribution graph"/>
</div>"""


def inject_readme(path: Path, block: str) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    wrapped = f"{START}\n{block}\n{END}"
    if START in text and END in text:
        text = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _m: wrapped, text, flags=re.S)
    else:
        text = wrapped + ("\n\n" + text if text else "\n")
    path.write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--username", default=os.environ.get("GITHUB_USERNAME"), help="GitHub username")
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"), help="token for real contribution data")
    ap.add_argument("--avatar", help="local image to use instead of the GitHub avatar")
    ap.add_argument("--invert", action="store_true", help="invert ASCII brightness")
    ap.add_argument("--out", default=".", help="output directory")
    ap.add_argument("--readme", default="README.md")
    ap.add_argument("--no-readme", action="store_true")
    args = ap.parse_args()

    if not args.username:
        sys.exit("Pass --username YOUR_GITHUB_USERNAME (or set GITHUB_USERNAME).")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    today = dt.date.today()

    # 1) contributions
    levels, total = None, None
    if args.token:
        try:
            levels, total = fetch_contributions(args.username, args.token)
            print(f"[ok] fetched real contributions ({total} total)")
        except Exception as e:  # noqa: BLE001
            print(f"[warn] contribution fetch failed ({e}); using placeholder data")
    if levels is None:
        levels = synthetic_contributions(calendar_start(today), today, args.username)
        print("[info] placeholder contribution data (set GITHUB_TOKEN for your real graph)")
    (out / "github-contribution-animation.svg").write_text(make_contrib_svg(levels, total, today), encoding="utf-8")

    # 2) terminal card
    try:
        ascii_lines = avatar_to_ascii(load_avatar(args.username, args.avatar), args.invert)
    except Exception as e:  # noqa: BLE001
        sys.exit(f"Could not load avatar for '{args.username}': {e}\nTip: pass --avatar path/to/image.png")
    (out / "terminal-card.svg").write_text(
        make_terminal_svg(ascii_lines, args.username, PROFILE["name"]), encoding="utf-8"
    )

    # 3) info card
    (out / "info-card.svg").write_text(make_info_svg(args.username.lower(), PROFILE), encoding="utf-8")
    print(f"[ok] wrote 3 SVGs to {out.resolve()}")

    if not args.no_readme:
        readme = Path(args.readme)
        inject_readme(readme, readme_block(PROFILE["name"]))
        print(f"[ok] updated {readme}")


if __name__ == "__main__":
    main()