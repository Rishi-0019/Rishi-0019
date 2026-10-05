#!/usr/bin/env python3
"""
generate_profile.py - animated, self-contained SVGs for a GitHub profile README.

Creates (pure SMIL, no CSS/JS, no external assets):
  github-contribution-animation.svg   53x7 calendar, diagonal slant reveal + glint
  terminal-card.svg                   high-detail coloured ASCII portrait in a terminal
  info-card.svg                       neofetch-style card: status pill, tech pills, sections
  banner.svg                          animated header: gradient name, role cycler, orbit rings
  tech-marquee.svg                    two scrolling rows of tech pills
  stats-card.svg                      streaks, active days, weekday bar chart
  footer.svg                          animated waves
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
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
except ImportError:
    sys.exit("Pillow is required:  pip install pillow")

# --------------------------------------------------------------------------- #
# EDIT ME: content for the info card
# --------------------------------------------------------------------------- #
PROFILE = {
    "name": "Rishabh Tiwari",
    "tagline": "Full Stack Developer",
    "roles": [
        "Full Stack Developer",
        "Real-time systems tinkerer",
        "Hackathon grand finalist",
        "Open to work",
    ],
    "marquee": [
        [
            "JavaScript", "TypeScript", "Python", "Java", "C", "OOP", "React.js",
            "Tailwind CSS", "Bootstrap", "HTML5", "CSS3", "Node.js", "Express.js",
            "FastAPI", "RESTful APIs", "JWT Authentication", "WebSockets", "WebRTC",
        ],
        [
            "PostgreSQL", "MySQL", "MongoDB", "Firebase Firestore", "Elasticsearch",
            "Prisma", "Mongoose", "Redis", "BullMQ", "Docker", "Docker Compose",
            "Job Queues", "Async Processing", "Pandas", "TensorFlow", "Satellite.js",
            "Git", "GitHub", "Firebase", "Vercel", "Railway", "Communication",
            "Team Collaboration", "Adaptability",
        ],
    ],
    "about": [
        ("Name", "Rishabh Tiwari"),
        ("Role", "Full Stack Developer"),
        ("Education", "B.E. Comp. Engg · AKTU '28"),
        ("Location", "Delhi, India"),
        ("Status", "● Open to work"),
    ],
    "stack": [
        ("Languages", "JS · TS · Python · Java · C"),
        ("Frontend", "React.js · Tailwind · Bootstrap"),
        ("Backend", "Node.js · Express · FastAPI · JWT"),
        ("Data", "PostgreSQL · MySQL · MongoDB"),
        ("Infra", "Redis · Docker · Firebase"),
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

# ASCII portrait geometry (a monospace glyph is ~0.6 x font-size wide).
# More columns + smaller font = noticeably sharper portrait in the same footprint.
COLS, FS = 80, 7.6
CW, LH = FS * 0.6, 8.2
ROWS = round(COLS * CW / LH)
AW, AH = COLS * CW, ROWS * LH
TERM_W = int(AW + 2 * 32)
AX = (TERM_W - AW) / 2
CMD_Y = 10 + TB + 20            # "$ render ..." line above the portrait
AY = CMD_Y + 16
FOOT_Y1 = AY + AH + 30          # $ whoami
FOOT_Y2 = FOOT_Y1 + 22          # name
FOOT_Y3 = FOOT_Y2 + 17          # tagline
CARD_H = int(FOOT_Y3 + 46)      # terminal + info card share this height
INFO_W = round(TERM_W * 0.48 / 0.52)  # README table splits ~52/48

# Dense -> sparse ramp, ordered by visual weight (70 levels).
RAMP = " .'`^\",:;Il!i><~+_-?][}{1)(|/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"

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
        "query{viewer{login contributionsCollection{contributionCalendar{"
        "totalContributions weeks{contributionDays{date contributionLevel}}}}}}"
    )
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json", "User-Agent": UA},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    if data.get("errors"):
        messages = "; ".join(error.get("message", "Unknown GraphQL error") for error in data["errors"])
        raise RuntimeError(messages)
    viewer = data.get("data", {}).get("viewer")
    if not viewer:
        raise RuntimeError("GitHub returned no authenticated-user data. Check that your token is valid.")
    if viewer["login"].casefold() != username.casefold():
        raise RuntimeError(
            f"Token belongs to '{viewer['login']}', but --username is '{username}'. "
            "Use a token for the account whose contributions you want to show."
        )
    cal = viewer["contributionsCollection"]["contributionCalendar"]
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
    td = (today - start).days
    today_ring = (
        f'<rect x="{GX + (td // 7) * PITCH - 2}" y="{GY + (td % 7) * PITCH - 2}" width="{CELL + 4}" height="{CELL + 4}" rx="4.5" '
        f'fill="none" stroke="{CYAN}" stroke-width="1.3" opacity="0">'
        f'<animate attributeName="opacity" values="0;1;.2;1" dur="2.2s" begin="{reveal_end:.2f}s" repeatCount="indefinite"/></rect>'
    )

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
        + today_ring
        + f'\n<g font-family="{FONT}">{legend}</g>\n</svg>\n'
    )


# --------------------------------------------------------------------------- #
# 2) ASCII terminal card  (upgraded)
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


def avatar_to_ascii(img: Image.Image, invert: bool = False) -> list[list[tuple[str, float]]]:
    """Return ROWS x COLS cells of (char, brightness 0..1).

    Quality tricks vs. a plain resize:
      * work at 4x the target grid, then downsample -> smoother tonal steps
      * unsharp mask -> crisp eyes / hairline / jaw edges
      * local-ish contrast: autocontrast + contrast + gamma
      * 70-level density ramp instead of 16
    """
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    bg = Image.new("RGBA", img.size, (13, 17, 23, 255))
    bg.alpha_composite(img)
    img = bg.convert("L")
    w, h = img.size
    s = min(w, h)
    left, top = (w - s) // 2, (h - s) // 2
    img = img.crop((left, top, left + s, top + s))

    # character cells are taller than wide, so sample a matching aspect
    big = img.resize((COLS * 4, ROWS * 4), Image.LANCZOS)
    big = ImageOps.autocontrast(big, cutoff=1.5)
    big = big.filter(ImageFilter.UnsharpMask(radius=3, percent=190, threshold=2))
    big = ImageEnhance.Contrast(big).enhance(1.25)
    img = big.resize((COLS, ROWS), Image.BOX)
    if invert:
        img = ImageOps.invert(img)

    px, n = img.load(), len(RAMP) - 1
    rows = []
    for y in range(ROWS):
        row = []
        for x in range(COLS):
            v = (px[x, y] / 255) ** 1.15      # >1 darkens mids -> deeper shadows
            row.append((RAMP[min(n, int(v * n + 0.5))], v))
        rows.append(row)
    return rows


def _mix(a: str, b: str, t: float) -> str:
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


def row_hue(frac: float) -> str:
    """Vertical hue sweep: cyan (top) -> green -> purple (bottom)."""
    if frac < 0.55:
        return _mix(CYAN, GREEN, frac / 0.55)
    return _mix(GREEN, PURPLE, (frac - 0.55) / 0.45)


SHADES = 6
DIM = "#1b3a4b"


def shade_color(hue: str, bucket: int) -> str:
    t = bucket / (SHADES - 1)
    if bucket == SHADES - 1:
        return _mix(hue, "#ffffff", 0.55)        # highlights glow near-white
    return _mix(DIM, hue, 0.22 + 0.78 * t)       # shadows sink into the background


def row_markup(cells: list[tuple[str, float]], frac: float) -> str:
    """One <tspan> per run of equal brightness bucket (keeps the SVG small)."""
    hue = row_hue(frac)
    runs, buf, cur = [], "", None
    for ch, v in cells:
        if ch == " ":
            buf += ch
            continue
        b = min(SHADES - 1, int(v * SHADES))
        if cur is None:
            cur = b
        elif b != cur:
            runs.append((buf, cur))
            buf, cur = "", b
        buf += ch
    if buf:
        runs.append((buf, cur if cur is not None else 0))
    return "".join(f'<tspan fill="{shade_color(hue, b)}">{escape(t)}</tspan>' for t, b in runs)


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


def hud_corners() -> str:
    """Four viewfinder brackets around the portrait."""
    pad, L = 8, 14
    x0, y0, x1, y1 = AX - pad, AY - pad, AX + AW + pad, AY + AH + pad
    d = (
        f"M{x0} {y0 + L} V{y0} H{x0 + L} "
        f"M{x1 - L} {y0} H{x1} V{y0 + L} "
        f"M{x1} {y1 - L} V{y1} H{x1 - L} "
        f"M{x0 + L} {y1} H{x0} V{y1 - L}"
    )
    return (
        f'<path d="{d}" fill="none" stroke="{CYAN}" stroke-width="1.4" stroke-linecap="round" opacity="0">'
        f'<animate attributeName="opacity" from="0" to=".75" begin="0.2s" dur="0.5s" fill="freeze"/></path>'
    )


def make_terminal_svg(cells: list[list[tuple[str, float]]], username: str, name: str, tagline: str) -> str:
    t0, rd = 1.5, 0.06                      # portrait starts after the command is typed
    clips, texts, cursors = [], [], []
    for i, row in enumerate(cells):
        ry, t = AY + i * LH, t0 + i * rd
        frac = i / max(1, ROWS - 1)
        clips.append(
            f'<clipPath id="r{i}"><rect x="{AX:.2f}" y="{ry:.2f}" width="0" height="{LH}">'
            f'<animate attributeName="width" from="{CW}" to="{AW:.2f}" begin="{t:.3f}s" dur="{rd}s" fill="freeze"/>'
            f"</rect></clipPath>"
        )
        texts.append(
            f'<text x="{AX:.2f}" y="{ry + FS - 0.6:.2f}" textLength="{AW:.2f}" lengthAdjust="spacing" '
            f'clip-path="url(#r{i})">{row_markup(row, frac)}</text>'
        )
        cursors.append(
            f'<rect x="{AX:.2f}" y="{ry:.2f}" width="{CW}" height="{LH}" fill="#ffffff" opacity="0">'
            f'<set attributeName="opacity" to="0.9" begin="{t:.3f}s"/>'
            f'<animate attributeName="x" from="{AX:.2f}" to="{AX + AW - CW:.2f}" begin="{t:.3f}s" dur="{rd}s" fill="freeze"/>'
            f'<set attributeName="opacity" to="0" begin="{t + rd:.3f}s"/></rect>'
        )
    ascii_end = t0 + ROWS * rd

    # --- command line above the portrait ---------------------------------- #
    cmd, _ = typed_text(
        AX, CMD_Y,
        [("$ ", GREEN, True), ("ascii-render ", WHITE, False), ("avatar.png", BLUE, False)],
        0.35, 0.045, font_size=11,
    )
    hud_label = (
        f'<text x="{AX + AW:.1f}" y="{CMD_Y}" text-anchor="end" font-family="{FONT}" font-size="9.5" fill="{MUTED}" opacity="0">'
        f'{COLS}×{ROWS} · {len(RAMP)} levels'
        f'<animate attributeName="opacity" from="0" to="1" begin="1.3s" dur="0.4s" fill="freeze"/></text>'
    )

    # --- footer prompt ----------------------------------------------------- #
    who, t1 = typed_text(
        AX, FOOT_Y1, [("$ ", GREEN, True), ("whoami", WHITE, False)], ascii_end + 0.4, 0.08, font_size=12
    )
    nm, t2 = typed_text(AX, FOOT_Y2, [(name, CYAN, True)], t1 + 0.35, 0.05, font_size=15)
    tg, _ = typed_text(AX, FOOT_Y3, [(tagline, MUTED, False)], t2 + 0.2, 0.025, font_size=11, cursor=True)

    # --- status bar -------------------------------------------------------- #
    sb_y = FOOT_Y3 + 22
    status = (
        f'<line x1="{AX:.1f}" y1="{sb_y - 12:.1f}" x2="{AX + AW:.1f}" y2="{sb_y - 12:.1f}" stroke="#ffffff" stroke-opacity=".08"/>'
        f'<g font-family="{FONT}" font-size="9.5" fill="{MUTED}">'
        f'<circle cx="{AX + 4:.1f}" cy="{sb_y - 3:.1f}" r="3" fill="{GREEN}">'
        f'<animate attributeName="opacity" values="1;.35;1" dur="2.4s" repeatCount="indefinite"/></circle>'
        f'<text x="{AX + 14:.1f}" y="{sb_y:.1f}">zsh · utf-8</text>'
        f'<text x="{AX + AW:.1f}" y="{sb_y:.1f}" text-anchor="end">main ✓ · {escape(username.lower())}</text>'
        f"</g>"
    )

    # --- beams -------------------------------------------------------------- #
    beam_h = 16
    reveal_beam = (
        f'<rect x="{AX - 4:.1f}" y="{AY - beam_h / 2:.1f}" width="{AW + 8:.1f}" height="{beam_h}" fill="url(#beam)" opacity="0">'
        f'<set attributeName="opacity" to="1" begin="{t0:.2f}s"/>'
        f'<animate attributeName="y" from="{AY - beam_h / 2:.1f}" to="{AY + AH - beam_h / 2:.1f}" '
        f'begin="{t0:.2f}s" dur="{ROWS * rd:.2f}s" fill="freeze"/>'
        f'<set attributeName="opacity" to="0" begin="{ascii_end:.2f}s"/></rect>'
    )
    idle_beam = (
        f'<rect x="{AX - 4:.1f}" y="{AY - beam_h:.1f}" width="{AW + 8:.1f}" height="{beam_h}" fill="url(#beam)" opacity="0">'
        f'<set attributeName="opacity" to=".7" begin="{ascii_end + 2:.2f}s"/>'
        f'<animateTransform attributeName="transform" type="translate" values="0 0;0 {AH + beam_h:.1f};0 {AH + beam_h:.1f}" '
        f'keyTimes="0;0.45;1" dur="9s" begin="{ascii_end + 2:.2f}s" repeatCount="indefinite"/></rect>'
    )

    extra = f"""  <linearGradient id="beam" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{CYAN}" stop-opacity="0"/>
    <stop offset=".5" stop-color="{CYAN}" stop-opacity=".30"/>
    <stop offset="1" stop-color="{CYAN}" stop-opacity="0"/>
  </linearGradient>
  <radialGradient id="portraitGlow">
    <stop offset="0" stop-color="{CYAN}" stop-opacity=".14"/>
    <stop offset=".6" stop-color="{PURPLE}" stop-opacity=".05"/>
    <stop offset="1" stop-color="{CYAN}" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="vignette" cx=".5" cy=".5" r=".75">
    <stop offset=".6" stop-color="#000000" stop-opacity="0"/>
    <stop offset="1" stop-color="#000000" stop-opacity=".45"/>
  </radialGradient>
  <pattern id="scan" width="4" height="3" patternUnits="userSpaceOnUse">
    <rect width="4" height="1" fill="#000000" fill-opacity=".22"/>
  </pattern>
  <clipPath id="bodyClip"><rect x="10" y="{10 + TB}" width="{TERM_W - 20}" height="{CARD_H - 20 - TB}" rx="0"/></clipPath>
  {"".join(clips)}
"""
    return (
        svg_open(TERM_W, CARD_H, f"ASCII portrait of {username}")
        + common_defs(extra)
        + frame(TERM_W, CARD_H, f"{username.lower()}@github: ~/portrait — zsh")
        + f'<ellipse cx="{TERM_W/2}" cy="{AY + AH/2:.1f}" rx="{AW*0.66:.1f}" ry="{AH*0.62:.1f}" fill="url(#portraitGlow)"/>\n'
        + hud_corners()
        + "\n"
        + cmd + "\n" + hud_label + "\n"
        + f'<g font-family="{FONT}" font-size="{FS}" font-weight="600" xml:space="preserve">{"".join(texts)}</g>\n'
        + "".join(cursors)
        + "\n"
        + f'<g clip-path="url(#bodyClip)">{reveal_beam}{idle_beam}</g>\n'
        + f'<rect x="10" y="{10 + TB}" width="{TERM_W - 20}" height="{CARD_H - 20 - TB}" fill="url(#vignette)" pointer-events="none"/>\n'
        + f'<rect x="10" y="{10 + TB}" width="{TERM_W - 20}" height="{CARD_H - 20 - TB}" fill="url(#scan)" opacity=".55" pointer-events="none"/>\n'
        + who + "\n" + nm + "\n" + tg + "\n"
        + status
        + "\n</svg>\n"
    )


# --------------------------------------------------------------------------- #
# 3) Info card  (redesigned: status pill, tech pills, section markers)
# --------------------------------------------------------------------------- #
def pill(x: float, y: float, txt: str, color: str, fs: float = 10) -> tuple[str, float]:
    w = len(txt) * fs * 0.61 + 14
    svg = (
        f'<rect x="{x:.1f}" y="{y - 12:.1f}" width="{w:.1f}" height="17" rx="8.5" fill="{color}" fill-opacity=".12" '
        f'stroke="{color}" stroke-opacity=".55" stroke-width=".8"/>'
        f'<text x="{x + w / 2:.1f}" y="{y:.1f}" font-size="{fs}" text-anchor="middle" fill="{color}">{escape(txt)}</text>'
    )
    return svg, w


def make_info_svg(handle: str, profile: dict) -> str:
    W, H = INFO_W, CARD_H
    X, VX, FSZ = 32, 108, 11.5
    stack_colors = [CYAN, GREEN, ORANGE, PURPLE, BLUE]

    items: list[str] = []
    y = 10 + TB + 34

    # header ------------------------------------------------------------------
    items.append(
        f'<text x="{X}" y="{y}" font-size="15" xml:space="preserve">'
        f'<tspan fill="{CYAN}" font-weight="700">{escape(handle)}</tspan><tspan fill="{WHITE}">@</tspan>'
        f'<tspan fill="{GREEN}" font-weight="700">github</tspan></text>'
    )
    y += 12
    rule_w = W - 2 * X
    items.append(
        f'<line x1="{X}" y1="{y}" x2="{W - X}" y2="{y}" stroke="url(#rule)" stroke-width="1.5" stroke-linecap="round" '
        f'stroke-dasharray="{rule_w}" stroke-dashoffset="{rule_w}">'
        f'<animate attributeName="stroke-dashoffset" from="{rule_w}" to="0" begin="0.4s" dur="0.9s" fill="freeze"/></line>'
    )
    y += 26

    # status pill ---------------------------------------------------------------
    status = dict(profile["about"]).get("Status", "").replace("●", "").strip()
    if status:
        sw = len(status) * 6.7 + 34
        items.append(
            f'<rect x="{X}" y="{y - 13}" width="{sw:.1f}" height="20" rx="10" fill="{GREEN}" fill-opacity=".10" '
            f'stroke="{GREEN}" stroke-opacity=".55"/>'
            f'<circle cx="{X + 12}" cy="{y - 3}" r="3.2" fill="{GREEN}">'
            f'<animate attributeName="opacity" values="1;.25;1" dur="1.8s" repeatCount="indefinite"/>'
            f'<animate attributeName="r" values="3.2;4.2;3.2" dur="1.8s" repeatCount="indefinite"/></circle>'
            f'<text x="{X + 23}" y="{y + 1}" font-size="11" fill="{GREEN}">{escape(status)}</text>'
        )
        y += 32

    def section(label: str, color: str) -> str:
        return (
            f'<rect x="{X}" y="{y - 10}" width="3" height="12" rx="1.5" fill="{color}"/>'
            f'<text x="{X + 10}" y="{y}" font-size="11" font-weight="700" fill="{color}">{escape(label)}</text>'
            f'<line x1="{X + 12 + len(label) * 7}" y1="{y - 4}" x2="{W - X}" y2="{y - 4}" stroke="{color}" stroke-opacity=".18"/>'
        )

    def kv(k: str, v: str, marker: str | None = None, mcolor: str = CYAN, vcolor: str = WHITE) -> str:
        m = f'<text x="{X}" y="{y}" font-size="9" fill="{mcolor}">{marker}</text>' if marker else ""
        return (
            m + f'<text x="{X + (14 if marker else 0)}" y="{y}" font-size="{FSZ}" fill="{CYAN}">{escape(k)}</text>'
            f'<text x="{VX + (6 if marker else 0)}" y="{y}" font-size="{FSZ}" fill="{vcolor}">{escape(v)}</text>'
        )

    # about -------------------------------------------------------------------
    items.append(section("About", ORANGE)); y += 21
    for k, v in profile["about"]:
        if k == "Status":
            continue
        items.append(kv(k, v)); y += 19
    y += 8

    # stack as pills ---------------------------------------------------------------
    items.append(section("Stack", BLUE)); y += 23
    for i, (k, v) in enumerate(profile["stack"]):
        col = stack_colors[i % len(stack_colors)]
        row = f'<text x="{X}" y="{y}" font-size="{FSZ}" fill="{MUTED}">{escape(k)}</text>'
        px = VX
        for part in v.split(" · "):
            p, w = pill(px, y, part, col)
            row += p
            px += w + 6
        items.append(row); y += 24
    y += 4

    # highlights -----------------------------------------------------------------------
    items.append(section("Highlights", GREEN)); y += 21
    for k, v in profile["highlights"]:
        items.append(kv(k, v, marker="◆", mcolor=GREEN)); y += 19
    y += 6

    # palette + prompt --------------------------------------------------------------------
    swatches = [CYAN, GREEN, ORANGE, PURPLE, BLUE, WHITE]
    items.append("".join(
        f'<rect x="{X + j * 24}" y="{y - 9}" width="20" height="10" rx="3" fill="{c}"/>' for j, c in enumerate(swatches)
    ))
    y += 28
    items.append(
        f'<text x="{X}" y="{y}" font-size="12" xml:space="preserve"><tspan fill="{GREEN}" font-weight="700">$</tspan>'
        f'<tspan fill="#ffffff"> █<animate attributeName="visibility" values="visible;hidden" calcMode="discrete" '
        f'dur="1.1s" repeatCount="indefinite"/></tspan></text>'
    )
    if y > H - 22:
        print(f"[warn] info card content overflows by {y - (H - 22):.0f}px - trim PROFILE entries")

    out = []
    for i, body in enumerate(items):
        begin = 0.35 + i * 0.07
        out.append(
            f'<g opacity="0">{body}'
            f'<animate attributeName="opacity" from="0" to="1" begin="{begin:.2f}s" dur="0.4s" fill="freeze"/>'
            f'<animateTransform attributeName="transform" type="translate" from="0 10" to="0 0" '
            f'begin="{begin:.2f}s" dur="0.4s" fill="freeze" calcMode="spline" keyTimes="0;1" keySplines="0.16 1 0.3 1"/></g>'
        )
    extra = f"""  <linearGradient id="rule" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="{CYAN}"/><stop offset=".6" stop-color="{GREEN}"/><stop offset="1" stop-color="{PURPLE}"/>
  </linearGradient>
"""
    return (
        svg_open(W, H, "Developer info card")
        + common_defs(extra)
        + frame(W, H, "neofetch")
        + f'<g font-family="{FONT}">' + "\n".join(out) + "</g>\n</svg>\n"
    )


# --------------------------------------------------------------------------- #
# 4) Banner
# --------------------------------------------------------------------------- #
BW = 882
BH = 200


def role_cycle(roles: list[str], x: float, y: float, slot: float = 3.0, begin: float = 2.2) -> str:
    n, f = len(roles), 0.05 / len(roles)
    out = []
    for i, role in enumerate(roles):
        a, b = i / n, (i + 1) / n
        pts = [(0.0, 0)]
        if a > 0:
            pts.append((a, 0))
        pts += [(a + f, 1), (b - f, 1)]
        pts.append((b, 0))
        if b < 1:
            pts.append((1.0, 0))
        kt = ";".join(f"{t:.4f}" for t, _ in pts)
        ov = ";".join(str(v) for _, v in pts)
        tv = ";".join("0 0" if v else "0 8" for _, v in pts)
        dur = n * slot
        out.append(
            f'<g opacity="0"><text x="{x}" y="{y}" font-size="20" xml:space="preserve">'
            f'<tspan fill="{GREEN}" font-weight="700">&gt; </tspan><tspan fill="{WHITE}">{escape(role)}</tspan></text>'
            f'<animate attributeName="opacity" values="{ov}" keyTimes="{kt}" dur="{dur}s" begin="{begin}s" repeatCount="indefinite"/>'
            f'<animateTransform attributeName="transform" type="translate" values="{tv}" keyTimes="{kt}" dur="{dur}s" begin="{begin}s" repeatCount="indefinite"/></g>'
        )
    return "".join(out)


def make_banner_svg(profile: dict) -> str:
    W, H = BW, BH
    name = profile["name"]
    status = dict(profile["about"]).get("Status", "Open to work").replace("●", "").strip()

    glyphs = [("{ }", 420, 40, 11), ("</>", 520, 170, 13), ("=>", 610, 60, 12), ("0x1F", 300, 176, 10),
              ("[ ]", 850, 40, 12), ("&&", 770, 176, 11), ("λ", 560, 120, 14), ("::", 380, 100, 12), ("#!", 840, 130, 11)]
    glyph_svg = "".join(
        f'<text x="{gx}" y="{gy}" font-size="{gs}" fill="{WHITE}" opacity=".10">{escape(g)}'
        f'<animateTransform attributeName="transform" type="translate" values="0 0;0 -14;0 0" dur="{7 + i}s" repeatCount="indefinite"/>'
        f'<animate attributeName="opacity" values=".05;.2;.05" dur="{5 + i * 0.8:.1f}s" repeatCount="indefinite"/></text>'
        for i, (g, gx, gy, gs) in enumerate(glyphs)
    )

    cx, cy = 735, 100
    rings = (
        f'<g transform="translate({cx} {cy})">'
        f'<circle r="86" fill="none" stroke="{WHITE}" stroke-opacity=".10" stroke-dasharray="2 7">'
        f'<animateTransform attributeName="transform" type="rotate" from="0" to="-360" dur="50s" repeatCount="indefinite"/></circle>'
        f'<circle r="60" fill="none" stroke="{CYAN}" stroke-opacity=".25" stroke-dasharray="14 8">'
        f'<animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="30s" repeatCount="indefinite"/></circle>'
        f'<circle r="36" fill="none" stroke="{PURPLE}" stroke-opacity=".30"/>'
        f'<g><animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="9s" repeatCount="indefinite"/>'
        f'<circle cx="36" r="4" fill="{PURPLE}" filter="url(#dotGlow)"/></g>'
        f'<g><animateTransform attributeName="transform" type="rotate" from="120" to="480" dur="14s" repeatCount="indefinite"/>'
        f'<circle cx="60" r="4.5" fill="{CYAN}" filter="url(#dotGlow)"/></g>'
        f'<g><animateTransform attributeName="transform" type="rotate" from="240" to="-120" dur="22s" repeatCount="indefinite"/>'
        f'<circle cx="86" r="4" fill="{GREEN}" filter="url(#dotGlow)"/></g>'
        f'<circle r="20" fill="#0d1117" stroke="url(#edge)" stroke-width="1.2"/>'
        f'<text y="5" text-anchor="middle" font-size="13" font-weight="700" fill="{CYAN}">&lt;/&gt;</text></g>'
    )

    chip_w = len(status) * 6.9 + 36
    chip = (
        f'<g opacity="0"><rect x="48" y="30" width="{chip_w:.1f}" height="24" rx="12" fill="{GREEN}" fill-opacity=".10" stroke="{GREEN}" stroke-opacity=".55"/>'
        f'<circle cx="62" cy="42" r="3.4" fill="{GREEN}"><animate attributeName="opacity" values="1;.25;1" dur="1.8s" repeatCount="indefinite"/></circle>'
        f'<text x="74" y="46" font-size="11.5" fill="{GREEN}">{escape(status)}</text>'
        f'<animate attributeName="opacity" from="0" to="1" begin="0.2s" dur="0.5s" fill="freeze"/></g>'
    )

    extra = f"""  <clipPath id="bclip"><rect width="{W}" height="{H}" rx="18"/></clipPath>
  <filter id="orb" x="-150%" y="-150%" width="400%" height="400%"><feGaussianBlur stdDeviation="42"/></filter>
  <filter id="dotGlow" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  <pattern id="grid" width="28" height="28" patternUnits="userSpaceOnUse"><path d="M28 0H0V28" fill="none" stroke="#ffffff" stroke-opacity=".045"/></pattern>
  <linearGradient id="nameGrad" gradientUnits="userSpaceOnUse" x1="48" y1="0" x2="548" y2="0" spreadMethod="reflect">
    <stop offset="0" stop-color="{CYAN}"/><stop offset=".5" stop-color="#ffffff"/><stop offset="1" stop-color="{PURPLE}"/>
    <animate attributeName="x1" values="48;548" dur="7s" repeatCount="indefinite"/>
    <animate attributeName="x2" values="548;1048" dur="7s" repeatCount="indefinite"/>
  </linearGradient>
  <clipPath id="nameClip"><rect x="40" y="52" width="0" height="80">
    <animate attributeName="width" from="0" to="640" begin="0.6s" dur="1.1s" fill="freeze" calcMode="spline" keyTimes="0;1" keySplines="0.3 0 0.2 1"/></rect></clipPath>
"""
    return (
        svg_open(W, H, f"{name} banner")
        + common_defs(extra)
        + f'<g clip-path="url(#bclip)"><rect width="{W}" height="{H}" fill="{BG}"/>'
        + f'<circle cx="150" cy="40" r="110" fill="{CYAN}" opacity=".20" filter="url(#orb)"><animate attributeName="cx" values="150;330;150" dur="16s" repeatCount="indefinite"/></circle>'
        + f'<circle cx="760" cy="170" r="120" fill="{PURPLE}" opacity=".24" filter="url(#orb)"><animate attributeName="cx" values="760;600;760" dur="19s" repeatCount="indefinite"/></circle>'
        + f'<circle cx="480" cy="210" r="90" fill="{GREEN}" opacity=".12" filter="url(#orb)"><animate attributeName="cy" values="210;150;210" dur="13s" repeatCount="indefinite"/></circle>'
        + f'<rect width="{W}" height="{H}" fill="url(#grid)"/>'
        + f'<g font-family="{FONT}">{glyph_svg}</g>'
        + f'<g font-family="{FONT}">{rings}{chip}'
        + f'<g clip-path="url(#nameClip)"><text x="48" y="112" font-size="52" font-weight="800" letter-spacing="-1.5" fill="url(#nameGrad)">{escape(name)}</text></g>'
        + role_cycle(profile["roles"], 50, 158)
        + "</g>"
        + f'<rect x="0" y="{H - 3}" width="{W}" height="3" fill="url(#nameGrad)" opacity=".8"/></g>\n'
        + f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="17" fill="none" stroke="url(#edge)" stroke-width="1.2"/>\n</svg>\n'
    )


# --------------------------------------------------------------------------- #
# 5) Tech marquee
# --------------------------------------------------------------------------- #
def pill_row(names: list[str], cy: float, width: int, speed: float, reverse: bool, offset: int) -> str:
    palette = [CYAN, GREEN, ORANGE, PURPLE, BLUE]
    pills, x, i = [], 0.0, 0
    while x < width + 40 or i < len(names):
        txt = names[i % len(names)]
        col = palette[(i + offset) % len(palette)]
        w = 26 + len(txt) * 7.5 + 14
        pills.append(
            f'<g transform="translate({x:.1f} 0)">'
            f'<rect y="{cy - 14}" width="{w:.1f}" height="28" rx="14" fill="{col}" fill-opacity=".10" stroke="{col}" stroke-opacity=".5"/>'
            f'<circle cx="14" cy="{cy}" r="3" fill="{col}"/>'
            f'<text x="26" y="{cy + 4.2}" font-size="12.5" fill="{WHITE}">{escape(txt)}</text></g>'
        )
        x += w + 12
        i += 1
    copy_w = x
    body = "".join(pills)
    frm, to = ("0 0", f"-{copy_w:.1f} 0") if not reverse else (f"-{copy_w:.1f} 0", "0 0")
    return (
        f'<g>{body}<g transform="translate({copy_w:.1f} 0)">{body}</g>'
        f'<animateTransform attributeName="transform" type="translate" from="{frm}" to="{to}" dur="{copy_w / speed:.1f}s" repeatCount="indefinite"/></g>'
    )


def make_marquee_svg(profile: dict) -> str:
    W, H = BW, 10 + TB + 98
    rows = profile["marquee"]
    extra = f"""  <linearGradient id="mfade" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#000"/><stop offset=".07" stop-color="#fff"/><stop offset=".93" stop-color="#fff"/><stop offset="1" stop-color="#000"/>
  </linearGradient>
  <mask id="mq" maskUnits="userSpaceOnUse" x="10" y="{10 + TB}" width="{W - 20}" height="{H - 20 - TB}"><rect x="10" y="{10 + TB}" width="{W - 20}" height="{H - 20 - TB}" fill="url(#mfade)"/></mask>
"""
    body = (
        pill_row(rows[0], 10 + TB + 28, W, 32, False, 0)
        + pill_row(rows[1], 10 + TB + 70, W, 26, True, 2)
    )
    return (
        svg_open(W, H, "Tech stack")
        + common_defs(extra)
        + frame(W, H, "~/stack — tail -f")
        + f'<g font-family="{FONT}" mask="url(#mq)">{body}</g>\n</svg>\n'
    )


# --------------------------------------------------------------------------- #
# 6) Stats card
# --------------------------------------------------------------------------- #
def streak_stats(levels: dict, today: dt.date):
    start = calendar_start(today)
    days = [start + dt.timedelta(days=i) for i in range((today - start).days + 1)]
    active = [levels.get(d, 0) > 0 for d in days]
    longest = run = 0
    for a in active:
        run = run + 1 if a else 0
        longest = max(longest, run)
    cur, i = 0, len(active) - 1
    if i >= 0 and not active[i]:
        i -= 1                      # today may simply not have commits yet
    while i >= 0 and active[i]:
        cur += 1
        i -= 1
    by_wd = [0] * 7                 # Sunday-first
    for d, a in zip(days, active):
        if a:
            by_wd[(d.weekday() + 1) % 7] += 1
    return sum(active), cur, longest, by_wd


def make_stats_svg(levels: dict, total: int | None, today: dt.date) -> str:
    W, H = BW, 226
    active, cur, longest, by_wd = streak_stats(levels, today)
    note = "" if total is not None else " — placeholder data"
    tiles = [
        ("Contributions", f"{total:,}" if total is not None else "—", "last 12 months", CYAN, "◆"),
        ("Active days", str(active), "days with a commit", GREEN, "●"),
        ("Current streak", str(cur), "days in a row", ORANGE, "▲"),
        ("Longest streak", str(longest), "best run this year", PURPLE, "★"),
    ]
    top, tw, th, gap = 10 + TB + 18, 128, 112, 12
    parts = []
    for i, (label, val, sub, col, glyph) in enumerate(tiles):
        x, t = 32 + i * (tw + gap), 0.35 + i * 0.15
        txt, _ = typed_text(x + 14, top + 68, [(val, col, True)], t + 0.3, 0.09, font_size=30)
        parts.append(
            f'<rect x="{x}" y="{top}" width="{tw}" height="{th}" rx="12" fill="#ffffff" fill-opacity=".03" stroke="#ffffff" stroke-opacity=".08" opacity="0">'
            f'<animate attributeName="opacity" from="0" to="1" begin="{t:.2f}s" dur="0.4s" fill="freeze"/></rect>'
            f'<g opacity="0"><text x="{x + 14}" y="{top + 27}" font-size="10.5" fill="{MUTED}">{escape(label)}</text>'
            f'<text x="{x + tw - 14}" y="{top + 27}" font-size="10" text-anchor="end" fill="{col}">{glyph}</text>'
            f'<text x="{x + 14}" y="{top + 90}" font-size="9.5" fill="{MUTED}">{escape(sub)}</text>'
            f'<animate attributeName="opacity" from="0" to="1" begin="{t:.2f}s" dur="0.4s" fill="freeze"/></g>'
            + txt
            + f'<rect x="{x + 14}" y="{top + th - 14}" width="0" height="2.5" rx="1.25" fill="{col}">'
            f'<animate attributeName="width" from="0" to="{tw - 28}" begin="{t + 0.2:.2f}s" dur="0.9s" fill="freeze" calcMode="spline" keyTimes="0;1" keySplines="0.2 0.8 0.2 1"/></rect>'
        )

    # weekday bar chart
    cx0, base, max_h = 612, top + th - 20, 62
    peak = max(by_wd) or 1
    names = ["S", "M", "T", "W", "T", "F", "S"]
    chart = f'<text x="{cx0}" y="{top + 14}" font-size="10.5" fill="{MUTED}">Active days by weekday</text>'
    for i, v in enumerate(by_wd):
        bh = max(3.0, v / peak * max_h)
        x, t = cx0 + i * 34 + 3, 0.6 + i * 0.08
        col = _mix("#0e4429", GREEN, v / peak)
        chart += (
            f'<rect x="{x}" y="{base}" width="24" height="0" rx="4" fill="{col}">'
            f'<animate attributeName="height" from="0" to="{bh:.1f}" begin="{t:.2f}s" dur="0.7s" fill="freeze" calcMode="spline" keyTimes="0;1" keySplines="0.2 0.8 0.2 1"/>'
            f'<animate attributeName="y" from="{base}" to="{base - bh:.1f}" begin="{t:.2f}s" dur="0.7s" fill="freeze" calcMode="spline" keyTimes="0;1" keySplines="0.2 0.8 0.2 1"/></rect>'
            f'<text x="{x + 12}" y="{base - bh - 5:.1f}" font-size="9" text-anchor="middle" fill="{WHITE}" opacity="0">{v}'
            f'<animate attributeName="opacity" from="0" to=".85" begin="{t + 0.6:.2f}s" dur="0.3s" fill="freeze"/></text>'
            f'<text x="{x + 12}" y="{base + 15}" font-size="9.5" text-anchor="middle" fill="{MUTED}">{names[i]}</text>'
        )
    return (
        svg_open(W, H, "GitHub stats")
        + common_defs()
        + frame(W, H, f"~/stats{note}")
        + f'<g font-family="{FONT}">{"".join(parts)}{chart}</g>\n</svg>\n'
    )


# --------------------------------------------------------------------------- #
# 7) Footer waves
# --------------------------------------------------------------------------- #
def wave_path(W: int, H: int, base: float, amp: float, period: float, phase: float = 0.0) -> str:
    pts, x = [], 0
    while x <= 2 * W:
        pts.append(f"{x:.0f},{base + amp * math.sin(2 * math.pi * x / period + phase):.1f}")
        x += 6
    return "M" + " L".join(pts) + f" L{2 * W},{H} L0,{H} Z"


def make_footer_svg(today: dt.date) -> str:
    W, H = BW, 130
    waves = [
        (CYAN, .16, 78, 8, W / 2, 0.0, 14, False),
        (PURPLE, .20, 88, 6, W / 3, 1.7, 18, True),
        (GREEN, .16, 98, 5, W / 4, 3.1, 22, False),
    ]
    paths = ""
    for col, op, base, amp, per, ph, dur, rev in waves:
        frm, to = ("0 0", f"-{W} 0") if not rev else (f"-{W} 0", "0 0")
        paths += (
            f'<path d="{wave_path(W, H, base, amp, per, ph)}" fill="{col}" fill-opacity="{op}">'
            f'<animateTransform attributeName="transform" type="translate" from="{frm}" to="{to}" dur="{dur}s" repeatCount="indefinite"/></path>'
        )
    extra = f"""  <linearGradient id="footGrad" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{W}" y2="0">
    <stop offset="0" stop-color="{CYAN}"/><stop offset=".5" stop-color="{GREEN}"/><stop offset="1" stop-color="{PURPLE}"/>
  </linearGradient>
"""
    return (
        svg_open(W, H, "Footer")
        + common_defs(extra)
        + paths
        + f'<g font-family="{FONT}" text-anchor="middle">'
        + f'<text x="{W / 2}" y="40" font-size="17" font-weight="700" fill="url(#footGrad)" opacity="0">thanks for stopping by ✦'
        + '<animate attributeName="opacity" from="0" to="1" begin="0.3s" dur="0.8s" fill="freeze"/></text>'
        + f'<text x="{W / 2}" y="60" font-size="10.5" fill="{MUTED}" opacity="0">updated {today.strftime("%d %b %Y")} · pure SVG, no JavaScript'
        + '<animate attributeName="opacity" from="0" to="1" begin="0.7s" dur="0.8s" fill="freeze"/></text></g>\n</svg>\n'
    )


# --------------------------------------------------------------------------- #
# README injection
# --------------------------------------------------------------------------- #
START, END = "<!-- PROFILE-CARDS:START -->", "<!-- PROFILE-CARDS:END -->"


def readme_block(alt_name: str) -> str:
    pct_term = round(TERM_W / (TERM_W + INFO_W) * 100, 1)
    pct_info = round(100 - pct_term, 1)
    return f"""<div align="center">
<img src="./banner.svg" width="100%" alt="{escape(alt_name)}"/>
<br/>
<table>
  <tr>
    <td width="{pct_term}%" valign="top"><img src="./terminal-card.svg" width="100%" alt="{escape(alt_name)} ASCII terminal portrait"/></td>
    <td width="{pct_info}%" valign="top"><img src="./info-card.svg" width="100%" alt="{escape(alt_name)} developer info"/></td>
  </tr>
</table>
<br/>
<img src="./tech-marquee.svg" width="100%" alt="Tech stack"/>
<br/>
<img src="./stats-card.svg" width="100%" alt="GitHub stats"/>
<br/>
<img src="./github-contribution-animation.svg" width="100%" alt="GitHub contribution graph"/>
<br/>
<img src="./footer.svg" width="100%" alt=""/>
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
            sys.exit(f"GitHub contribution fetch failed: {e}")
    if levels is None:
        levels = synthetic_contributions(calendar_start(today), today, args.username)
        print("[info] placeholder contribution data (set GITHUB_TOKEN for your real graph)")
    (out / "github-contribution-animation.svg").write_text(make_contrib_svg(levels, total, today), encoding="utf-8")

    # 2) terminal card
    try:
        cells = avatar_to_ascii(load_avatar(args.username, args.avatar), args.invert)
    except Exception as e:  # noqa: BLE001
        sys.exit(f"Could not load avatar for '{args.username}': {e}\nTip: pass --avatar path/to/image.png")
    (out / "terminal-card.svg").write_text(
        make_terminal_svg(cells, args.username, PROFILE["name"], PROFILE["tagline"]), encoding="utf-8"
    )

    # 3) info card
    (out / "info-card.svg").write_text(make_info_svg(args.username.lower(), PROFILE), encoding="utf-8")
    # 4-7) banner, marquee, stats, footer
    (out / "banner.svg").write_text(make_banner_svg(PROFILE), encoding="utf-8")
    (out / "tech-marquee.svg").write_text(make_marquee_svg(PROFILE), encoding="utf-8")
    (out / "stats-card.svg").write_text(make_stats_svg(levels, total, today), encoding="utf-8")
    (out / "footer.svg").write_text(make_footer_svg(today), encoding="utf-8")
    print(f"[ok] wrote 7 SVGs to {out.resolve()}")

    if not args.no_readme:
        readme = Path(args.readme)
        inject_readme(readme, readme_block(PROFILE["name"]))
        print(f"[ok] updated {readme}")


if __name__ == "__main__":
    main()