#!/usr/bin/env python3
"""Render the oddyssey presentation video - Pillow draws every frame, ffmpeg encodes.

    python3 make_video.py                 # full 1080p render -> out/oddyssey.mp4
    python3 make_video.py --scale 0.6667 --crf 30 --out oddyssey-trailer.mp4   # the committed 720p trailer
    python3 make_video.py --preview       # quick 15 fps / half-size draft
    python3 make_video.py --frames 12     # dump a contact sheet of stills to out/stills/
    python3 make_video.py --music track.mp3   # use your own soundtrack instead of the synthesized one
    python3 make_video.py --no-music     # silent video

The story: Odysseus (your coding agent) sails the telemetry sea, meets the
monsters (bugs, bad behaviors, bad performance, blind spots) and beats them
with the signs the gods send - Loki (logs), Tempo (traces), Mimir (metrics),
Pyroscope (profiles). Instrument once, then the ODD loop: observe, fix, verify.
"""

from __future__ import annotations

import argparse
import functools
import math
import random
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
# the closing scene reuses the repository banner (assets/images/banner.png)
BANNER_CANDIDATES = [
    HERE.parent.parent / "images" / "banner.png",
    HERE / "assets" / "banner.png",
]

W, H = 1920, 1080
FPS = 30
XFADE = 0.7  # seconds of crossfade between scenes

# ----------------------------------------------------------------------------
# palette (dark sea, gold titles, signal colours per god)
# ----------------------------------------------------------------------------
NAVY = (7, 12, 26)
DEEP = (12, 26, 48)
SKY = (24, 40, 68)
TEAL = (46, 196, 182)
GOLD = (226, 180, 76)
CREAM = (242, 232, 205)
RED = (226, 76, 62)
ORANGE = (255, 146, 44)
GREEN = (92, 218, 126)
BLUE = (96, 164, 255)
PURPLE = (186, 118, 255)
GREY = (150, 162, 180)
WHITE = (255, 255, 255)
INK = (18, 22, 34)

GODS = [
    # name, signal, colour, one-liner
    ("Loki", "Logs", GOLD, "what happened, line by line"),
    ("Tempo", "Traces", TEAL, "where the time went, span by span"),
    ("Mimir", "Metrics", BLUE, "how much, how often, how fast"),
    ("Pyroscope", "Profiles", ORANGE, "which line of code burns the CPU"),
]

# ----------------------------------------------------------------------------
# fonts
# ----------------------------------------------------------------------------
SERIF_BOLD = [
    "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
    "/Library/Fonts/Georgia Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
]
SERIF = [
    "/System/Library/Fonts/Supplemental/Georgia.ttf",
    "/Library/Fonts/Georgia.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
]
SERIF_ITALIC = [
    "/System/Library/Fonts/Supplemental/Georgia Italic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
]
MONO = [
    "/System/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/Monaco.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
]
FAMILIES = {"bold": SERIF_BOLD, "serif": SERIF, "italic": SERIF_ITALIC, "mono": MONO}


@functools.cache
def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    for path in FAMILIES[kind]:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default(size)


# ----------------------------------------------------------------------------
# small math helpers
# ----------------------------------------------------------------------------
def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else min(x, hi)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def mix(c1, c2, t: float):
    t = clamp(t)
    return tuple(round(lerp(a, b, t)) for a, b in zip(c1, c2))


def ease_out(t: float) -> float:
    t = clamp(t)
    return 1 - (1 - t) ** 3


def ease_in_out(t: float) -> float:
    t = clamp(t)
    return t * t * (3 - 2 * t)


def window(t: float, start: float, dur: float) -> float:
    """0 before `start`, 1 after `start + dur`, linear in between."""
    if dur <= 0:
        return 1.0 if t >= start else 0.0
    return clamp((t - start) / dur)


def rgba(color, alpha: float):
    return (*color[:3], int(255 * clamp(alpha)))


# ----------------------------------------------------------------------------
# drawing primitives
# ----------------------------------------------------------------------------
def text(
    d: ImageDraw.ImageDraw, xy, s: str, f, fill, anchor="la", alpha=1.0, shadow=True
):
    if alpha <= 0 or not s:
        return
    x, y = xy
    if shadow:
        d.text((x + 3, y + 3), s, font=f, fill=rgba(INK, 0.85 * alpha), anchor=anchor)
    d.text((x, y), s, font=f, fill=rgba(fill, alpha), anchor=anchor)


def text_width(f, s: str) -> int:
    left, _, right, _ = f.getbbox(s)
    return right - left


@functools.lru_cache(maxsize=64)
def glow_layer(s: str, kind: str, size: int, color, radius: int) -> Image.Image:
    """A blurred copy of a string, rendered at quarter resolution, used as a halo."""
    f = font(kind, size)
    pad = radius * 3
    w = text_width(f, s) + pad * 2
    h = size * 2 + pad * 2
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((pad, pad), s, font=f, fill=(*color, 255))
    small = layer.resize((max(1, w // 4), max(1, h // 4)), Image.Resampling.BILINEAR)
    small = small.filter(ImageFilter.GaussianBlur(radius / 4))
    return small.resize((w, h), Image.Resampling.BILINEAR)


def glow_text(
    img: Image.Image, center, s: str, kind: str, size: int, color, alpha=1.0, radius=28
):
    """Centered title with a soft halo behind it."""
    if alpha <= 0:
        return
    halo = glow_layer(s, kind, size, color, radius)
    f = font(kind, size)
    pad = radius * 3
    cx, cy = center
    left, top, right, bottom = f.getbbox(s)
    tw, th = right - left, bottom - top
    x0 = int(cx - tw / 2 - pad + left)
    y0 = int(cy - th / 2 - pad - top)
    if alpha < 1:
        halo = halo.copy()
        halo.putalpha(halo.getchannel("A").point(lambda v: int(v * alpha)))
    img.paste(halo, (x0, y0), halo)
    d = ImageDraw.Draw(img, "RGBA")
    text(d, (cx, cy), s, f, color, anchor="mm", alpha=alpha)


def card(
    d: ImageDraw.ImageDraw, box, alpha=1.0, border=GOLD, fill=(10, 20, 38), radius=22
):
    if alpha <= 0:
        return
    d.rounded_rectangle(
        box,
        radius=radius,
        fill=rgba(fill, 0.82 * alpha),
        outline=rgba(border, 0.9 * alpha),
        width=3,
    )


def polyline(d, pts, color, width=2, alpha=1.0):
    if len(pts) >= 2:
        d.line(pts, fill=rgba(color, alpha), width=width, joint="curve")


# ----------------------------------------------------------------------------
# backgrounds
# ----------------------------------------------------------------------------
@functools.lru_cache(maxsize=8)
def sky_gradient(horizon: int) -> Image.Image:
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        if y < horizon:
            c = mix(NAVY, SKY, y / max(1, horizon))
        else:
            c = mix(DEEP, NAVY, (y - horizon) / max(1, H - horizon))
        for x in range(W):
            px[x, y] = c
    return img


@functools.lru_cache(maxsize=2)
def vignette() -> Image.Image:
    small = Image.new("L", (W // 8, H // 8), 0)
    d = ImageDraw.Draw(small)
    cx, cy = small.width / 2, small.height / 2
    for r in range(40, 0, -1):
        k = r / 40
        d.ellipse(
            (
                cx - cx * 1.5 * k,
                cy - cy * 1.7 * k,
                cx + cx * 1.5 * k,
                cy + cy * 1.7 * k,
            ),
            fill=int(160 * (1 - k) ** 1.5),
        )
    mask = small.filter(ImageFilter.GaussianBlur(6)).resize(
        (W, H), Image.Resampling.BILINEAR
    )
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.putalpha(mask)
    return layer


@functools.lru_cache(maxsize=4)
def stars(seed: int) -> list:
    rnd = random.Random(seed)
    return [
        (rnd.randint(0, W), rnd.randint(0, int(H * 0.5)), rnd.random())
        for _ in range(160)
    ]


def draw_sea(img: Image.Image, t: float, horizon=0.56, storm=0.4, seed=1):
    """Stormy sea made of glowing wave lines - the telemetry sea of the banner."""
    hy = int(H * horizon)
    img.paste(sky_gradient(hy))
    d = ImageDraw.Draw(img, "RGBA")
    for sx, sy, ph in stars(seed):
        tw = 0.5 + 0.5 * math.sin(t * 2 + ph * 12)
        d.point((sx, sy), fill=rgba(CREAM, 0.25 + 0.5 * tw * (1 - storm)))
    rows = 16
    for i in range(rows):
        k = i / (rows - 1)
        y0 = hy + 10 + (k**1.35) * (H - hy - 20)
        amp = (6 + 34 * k) * (0.6 + storm)
        base = mix(TEAL, GOLD, (i % 3) / 2 * 0.6)
        color = mix(base, DEEP, 0.55 * (1 - k))
        speed = 0.6 + 0.35 * i
        pts = []
        for x in range(0, W + 1, 12):
            y = (
                y0
                + amp * math.sin(x / (170 + 25 * i) + t * speed + i * 1.7)
                + amp * 0.35 * math.sin(x / 41 - t * (1.4 + storm) + i)
            )
            pts.append((x, y))
        polyline(d, pts, color, width=1 + int(k * 3), alpha=0.35 + 0.5 * k)
    img.paste(vignette(), (0, 0), vignette())


def lightning(img: Image.Image, t: float, flashes, storm=1.0):
    """Brief white flashes at the given times, with a jagged bolt on the strongest ones."""
    d = ImageDraw.Draw(img, "RGBA")
    for ft, x, strength in flashes:
        dt = t - ft
        if 0 <= dt < 0.35:
            a = strength * storm * (1 - dt / 0.35) ** 2
            d.rectangle((0, 0, W, H), fill=rgba(WHITE, 0.22 * a))
            if strength > 0.6 and dt < 0.18:
                rnd = random.Random(int(ft * 100))
                pts = [(x, 0)]
                y = 0
                while y < H * 0.5:
                    y += rnd.randint(40, 90)
                    pts.append((pts[-1][0] + rnd.randint(-60, 60), y))
                polyline(d, pts, WHITE, width=4, alpha=a)
                polyline(d, pts, CREAM, width=10, alpha=a * 0.25)


# ----------------------------------------------------------------------------
# actors
# ----------------------------------------------------------------------------
AGENTS = ["Claude", "Copilot", "Codex", "Cursor", "Gemini"]


def draw_ship(
    d: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    s: float,
    t: float,
    alpha=1.0,
    rock=1.0,
    shields=True,
):
    """A stylised trireme, bobbing on the sea. `s` is the half-length in pixels."""
    if alpha <= 0:
        return
    bob = math.sin(t * 1.7) * 0.06 * s * rock
    tilt = math.sin(t * 1.7 + 0.8) * 0.05 * rock
    cy = cy + bob

    def P(x, y):
        # rotate slightly for the rocking motion
        xr = x * math.cos(tilt) - y * math.sin(tilt)
        yr = x * math.sin(tilt) + y * math.cos(tilt)
        return (cx + xr * s, cy + yr * s)

    hull_dark = mix((92, 58, 34), INK, 0.2)
    hull = (122, 78, 44)
    # oars first, so they come out from under the gunwale, spread along the hull only
    for k in range(10):
        x = -0.72 + k * 0.16
        stroke = math.sin(t * 2.4 + k * 0.5) * 0.08
        d.line(
            [P(x, 0.0), P(x + 0.2 + stroke, 0.62)],
            fill=rgba(hull_dark, alpha),
            width=max(1, int(s * 0.025)),
        )
    # hull
    d.polygon(
        [
            P(-1.0, 0.0),
            P(-0.82, 0.32),
            P(0.85, 0.32),
            P(1.05, 0.0),
            P(0.95, -0.14),
            P(-0.9, -0.14),
        ],
        fill=rgba(hull, alpha),
        outline=rgba(hull_dark, alpha),
    )
    d.line(
        [P(-0.9, -0.14), P(0.95, -0.14)],
        fill=rgba(GOLD, alpha * 0.9),
        width=max(1, int(s * 0.03)),
    )
    # prow curl and painted eye
    d.line(
        [P(-1.0, 0.0), P(-1.15, -0.32), P(-1.05, -0.5)],
        fill=rgba(hull_dark, alpha),
        width=max(2, int(s * 0.06)),
    )
    ex, ey = P(-0.8, 0.04)
    r = max(2, s * 0.05)
    d.ellipse((ex - r * 1.6, ey - r, ex + r * 1.6, ey + r), fill=rgba(CREAM, alpha))
    d.ellipse(
        (ex - r * 0.6, ey - r * 0.6, ex + r * 0.6, ey + r * 0.6), fill=rgba(INK, alpha)
    )
    # mast, yard, sail
    d.line(
        [P(0.05, -0.14), P(0.05, -1.35)],
        fill=rgba(hull_dark, alpha),
        width=max(2, int(s * 0.04)),
    )
    d.line(
        [P(-0.55, -1.25), P(0.65, -1.25)],
        fill=rgba(hull_dark, alpha),
        width=max(2, int(s * 0.03)),
    )
    belly = 0.12 + 0.04 * math.sin(t * 3)
    d.polygon(
        [P(-0.5, -1.22), P(0.6, -1.22), P(0.55 + belly, -0.5), P(-0.45 - belly, -0.5)],
        fill=rgba(CREAM, alpha * 0.95),
        outline=rgba(GOLD, alpha * 0.6),
    )
    # a stripe on the sail
    d.line(
        [P(-0.47, -0.86), P(0.57, -0.86)],
        fill=rgba(RED, alpha * 0.7),
        width=max(2, int(s * 0.05)),
    )
    # shields along the gunwale, one per coding agent
    if shields:
        f = font("bold", max(8, int(s * 0.09)))
        for i, name in enumerate(AGENTS):
            x = -0.5 + i * 0.34
            sx, sy = P(x, -0.06)
            rr = s * 0.15
            d.ellipse(
                (sx - rr, sy - rr, sx + rr, sy + rr),
                fill=rgba(GOLD, alpha),
                outline=rgba(hull_dark, alpha),
                width=2,
            )
            d.ellipse(
                (sx - rr * 0.35, sy - rr * 0.35, sx + rr * 0.35, sy + rr * 0.35),
                fill=rgba(RED, alpha * 0.85),
            )
            if s >= 110:
                d.text(
                    (sx, sy + rr * 1.55),
                    name,
                    font=f,
                    fill=rgba(CREAM, alpha),
                    anchor="mm",
                )


def icon_bug(d, cx, cy, r, t, alpha=1.0):
    """Scylla - a many-legged bug with a red glow."""
    for k in range(3, 0, -1):
        d.ellipse(
            (
                cx - r * (1 + k * 0.18),
                cy - r * (1 + k * 0.18),
                cx + r * (1 + k * 0.18),
                cy + r * (1 + k * 0.18),
            ),
            fill=rgba(RED, 0.06 * alpha),
        )
    wig = math.sin(t * 6) * r * 0.08
    for i in range(3):
        y = cy - r * 0.35 + i * r * 0.4
        d.line(
            [(cx - r * 0.6, y), (cx - r * 1.25, y - r * 0.35 + wig)],
            fill=rgba(RED, alpha),
            width=max(2, int(r * 0.08)),
        )
        d.line(
            [(cx + r * 0.6, y), (cx + r * 1.25, y - r * 0.35 - wig)],
            fill=rgba(RED, alpha),
            width=max(2, int(r * 0.08)),
        )
    d.ellipse(
        (cx - r * 0.65, cy - r * 0.55, cx + r * 0.65, cy + r * 0.95),
        fill=rgba(RED, alpha),
        outline=rgba(INK, alpha),
        width=2,
    )
    d.line(
        [(cx, cy - r * 0.55), (cx, cy + r * 0.95)],
        fill=rgba(INK, alpha * 0.7),
        width=max(1, int(r * 0.04)),
    )
    d.ellipse(
        (cx - r * 0.42, cy - r * 0.95, cx + r * 0.42, cy - r * 0.2),
        fill=rgba((150, 40, 32), alpha),
        outline=rgba(INK, alpha),
        width=2,
    )
    d.line(
        [(cx - r * 0.2, cy - r * 0.85), (cx - r * 0.55, cy - r * 1.35)],
        fill=rgba(RED, alpha),
        width=max(2, int(r * 0.06)),
    )
    d.line(
        [(cx + r * 0.2, cy - r * 0.85), (cx + r * 0.55, cy - r * 1.35)],
        fill=rgba(RED, alpha),
        width=max(2, int(r * 0.06)),
    )
    for sx in (-0.18, 0.18):
        d.ellipse(
            (
                cx + sx * r - r * 0.07,
                cy - r * 0.65 - r * 0.07,
                cx + sx * r + r * 0.07,
                cy - r * 0.65 + r * 0.07,
            ),
            fill=rgba(CREAM, alpha),
        )


def icon_sirens(d, cx, cy, r, t, alpha=1.0):
    """The Sirens - waves of song that lie: concentric arcs with a wobbling mask."""
    for i in range(4):
        rr = r * (0.35 + i * 0.28) + math.sin(t * 4 + i) * r * 0.03
        a = alpha * (0.9 - i * 0.18)
        d.arc(
            (cx - rr, cy - rr, cx + rr, cy + rr),
            start=200,
            end=340,
            fill=rgba(PURPLE, a),
            width=max(2, int(r * 0.07)),
        )
        d.arc(
            (cx - rr, cy - rr, cx + rr, cy + rr),
            start=20,
            end=160,
            fill=rgba(PURPLE, a * 0.6),
            width=max(2, int(r * 0.05)),
        )
    d.ellipse(
        (cx - r * 0.28, cy - r * 0.28, cx + r * 0.28, cy + r * 0.28),
        fill=rgba(PURPLE, alpha),
    )
    # a smile that is not what it seems
    d.arc(
        (cx - r * 0.16, cy - r * 0.02, cx + r * 0.16, cy + r * 0.2),
        start=200,
        end=340,
        fill=rgba(INK, alpha),
        width=3,
    )
    for sx in (-0.1, 0.1):
        d.ellipse(
            (
                cx + sx * r - r * 0.035,
                cy - r * 0.1 - r * 0.035,
                cx + sx * r + r * 0.035,
                cy - r * 0.1 + r * 0.035,
            ),
            fill=rgba(INK, alpha),
        )


def icon_whirlpool(d, cx, cy, r, t, alpha=1.0, turns=3.2):
    """Charybdis - a rotating spiral that swallows the p95."""
    pts = []
    n = 160
    for i in range(n):
        k = i / (n - 1)
        ang = k * turns * 2 * math.pi + t * 2.2
        rr = r * (0.05 + 0.95 * k)
        pts.append((cx + rr * math.cos(ang), cy + rr * 0.55 * math.sin(ang)))
    for width, col, a in (
        (int(r * 0.16), TEAL, 0.25),
        (int(r * 0.07), TEAL, 0.9),
        (2, CREAM, 0.7),
    ):
        polyline(d, pts, col, width=max(1, width), alpha=alpha * a)
    d.ellipse(
        (cx - r * 0.12, cy - r * 0.07, cx + r * 0.12, cy + r * 0.07),
        fill=rgba(INK, alpha),
    )


def icon_cyclops(d, cx, cy, r, t, alpha=1.0):
    """The Cyclops - one eye, no telemetry: a blind spot."""
    blink = 1.0 if (t % 3.1) > 0.25 else 0.15
    ry = r * 0.55 * blink
    d.ellipse(
        (cx - r, cy - ry, cx + r, cy + ry),
        fill=rgba(CREAM, alpha),
        outline=rgba(ORANGE, alpha),
        width=max(2, int(r * 0.06)),
    )
    ir = r * 0.42 * blink
    d.ellipse(
        (cx - r * 0.42, cy - ir, cx + r * 0.42, cy + ir), fill=rgba(ORANGE, alpha)
    )
    pr = r * 0.2 * blink
    d.ellipse((cx - r * 0.2, cy - pr, cx + r * 0.2, cy + pr), fill=rgba(INK, alpha))
    # the blind spot: a dark fog creeping over the eye
    d.rectangle(
        (cx - r * 1.2, cy + ry * 0.4, cx + r * 1.2, cy + r * 0.8),
        fill=rgba(NAVY, alpha * 0.75),
    )
    d.text(
        (cx, cy + r * 0.62),
        "?",
        font=font("bold", max(10, int(r * 0.5))),
        fill=rgba(ORANGE, alpha),
        anchor="mm",
    )


MONSTERS = [
    ("Scylla", "Bugs", "many heads, one bite in production", icon_bug, RED),
    (
        "The Sirens",
        "Bad behaviors",
        "the code sings one thing and does another",
        icon_sirens,
        PURPLE,
    ),
    (
        "Charybdis",
        "Bad performance",
        "the whirlpool that swallows your p95",
        icon_whirlpool,
        TEAL,
    ),
    (
        "The Cyclops",
        "Blind spots",
        "one eye, no telemetry, no way to tell",
        icon_cyclops,
        ORANGE,
    ),
]


# --- the four signals, drawn as small live widgets ---------------------------
LOG_LINES = [  # an AI agent's day, in OpenTelemetry GenAI terms
    ("INFO", "agent up, claude-fable-5", GREEN),
    ("INFO", "web_search ok 0.4s", GREEN),
    ("WARN", "web_search 429 limited", GOLD),
    ("WARN", "web_search 429 limited", GOLD),
    ("ERROR", "web_search timeout 30s", RED),
    ("INFO", "input_tokens=1842", GREEN),
    ("WARN", "no retry on web_search", GOLD),
]


def icon_logs(d, box, t, progress, alpha=1.0):
    x0, y0, x1, y1 = box
    d.rounded_rectangle(
        box,
        radius=10,
        fill=rgba(CREAM, alpha * 0.92),
        outline=rgba(GOLD, alpha),
        width=2,
    )
    # scroll rollers
    d.rounded_rectangle(
        (x0 - 8, y0 - 6, x1 + 8, y0 + 10), radius=8, fill=rgba(GOLD, alpha)
    )
    d.rounded_rectangle(
        (x0 - 8, y1 - 10, x1 + 8, y1 + 6), radius=8, fill=rgba(GOLD, alpha)
    )
    f = font("mono", 18)
    n = int(len(LOG_LINES) * progress + 0.999)
    for i, (lvl, msg, col) in enumerate(LOG_LINES[:n]):
        y = y0 + 22 + i * 28
        if y > y1 - 24:
            break
        d.text(
            (x0 + 14, y), lvl.ljust(5), font=f, fill=rgba(mix(col, INK, 0.25), alpha)
        )
        d.text((x0 + 80, y), msg, font=f, fill=rgba(INK, alpha * 0.85))


SPANS = [  # (name, start, length, depth, colour) - GenAI semantic-convention span names
    ("invoke_agent researcher", 0.0, 1.0, 0, TEAL),
    ("chat claude-fable-5", 0.02, 0.1, 1, TEAL),
    ("execute_tool web_search", 0.14, 0.8, 1, RED),
    ("HTTP GET search-api 429", 0.16, 0.76, 2, RED),
    ("chat claude-fable-5", 0.95, 0.04, 1, TEAL),
]


def icon_traces(d, box, t, progress, alpha=1.0, fixed=False):
    x0, y0, x1, y1 = box
    d.rounded_rectangle(
        box,
        radius=10,
        fill=rgba((8, 18, 34), alpha * 0.9),
        outline=rgba(TEAL, alpha),
        width=2,
    )
    f = font("mono", 16)
    w = x1 - x0 - 40
    rowh = (y1 - y0 - 20) / len(SPANS)
    for i, (name, start, length, depth, col) in enumerate(SPANS):
        if i / len(SPANS) > progress:
            break
        if fixed and col == RED:
            col, length = GREEN, length * 0.08
        y = y0 + 12 + i * rowh
        bx0 = x0 + 20 + w * start + depth * 6
        bx1 = bx0 + max(8, w * length * clamp(progress * len(SPANS) - i) - depth * 6)
        d.rounded_rectangle(
            (bx0, y, bx1, y + rowh - 8), radius=4, fill=rgba(col, alpha * 0.85)
        )
        if bx1 - bx0 > 40:
            d.text(
                (bx0 + 8, y + (rowh - 8) / 2),
                name,
                font=f,
                fill=rgba(INK if col != RED else CREAM, alpha),
                anchor="lm",
            )


def metric_series(n=60, seed=3):
    rnd = random.Random(seed)
    vals, v = [], 0.35
    for i in range(n):
        v = clamp(v + rnd.uniform(-0.08, 0.08), 0.1, 0.9)
        vals.append(v)
    return vals


def icon_metrics(
    d, box, t, progress, alpha=1.0, series=None, color=BLUE, threshold=None
):
    x0, y0, x1, y1 = box
    d.rounded_rectangle(
        box,
        radius=10,
        fill=rgba((8, 18, 34), alpha * 0.9),
        outline=rgba(color, alpha),
        width=2,
    )
    for k in range(1, 4):
        y = y0 + (y1 - y0) * k / 4
        d.line([(x0 + 10, y), (x1 - 10, y)], fill=rgba(GREY, alpha * 0.25), width=1)
    vals = series or metric_series()
    n = max(2, int(len(vals) * progress))
    pts = []
    for i in range(n):
        x = x0 + 14 + (x1 - x0 - 28) * i / (len(vals) - 1)
        y = y1 - 14 - (y1 - y0 - 28) * vals[i]
        pts.append((x, y))
    if threshold is not None:
        ty = y1 - 14 - (y1 - y0 - 28) * threshold
        d.line([(x0 + 10, ty), (x1 - 10, ty)], fill=rgba(RED, alpha * 0.7), width=2)
    # area under the curve
    d.polygon(
        pts + [(pts[-1][0], y1 - 14), (pts[0][0], y1 - 14)],
        fill=rgba(color, alpha * 0.18),
    )
    polyline(d, pts, color, width=3, alpha=alpha)
    px, py = pts[-1]
    d.ellipse((px - 5, py - 5, px + 5, py + 5), fill=rgba(CREAM, alpha))


FLAME = [  # rows of (start, length, label) fractions, bottom row first
    [(0.0, 1.0, "invoke_agent")],
    [(0.0, 0.12, "chat"), (0.13, 0.84, "execute_tool")],
    [(0.14, 0.78, "web_search"), (0.93, 0.04, "parse")],
    [(0.15, 0.7, "http.get"), (0.86, 0.06, "json")],
    [(0.16, 0.6, "socket.recv")],
]


def icon_profiles(d, box, t, progress, alpha=1.0, fixed=False):
    x0, y0, x1, y1 = box
    d.rounded_rectangle(
        box,
        radius=10,
        fill=rgba((8, 18, 34), alpha * 0.9),
        outline=rgba(ORANGE, alpha),
        width=2,
    )
    f = font("mono", 15)
    rows = len(FLAME)
    rowh = (y1 - y0 - 20) / rows
    w = x1 - x0 - 24
    for r, row in enumerate(FLAME):
        if r / rows > progress:
            break
        y = y1 - 10 - (r + 1) * rowh
        for start, length, label in row:
            if fixed and label in ("web_search", "http.get", "socket.recv"):
                length = length * 0.12
            heat = 0.35 + 0.65 * length
            col = mix(GOLD, RED, heat)
            bx0 = x0 + 12 + w * start
            bx1 = bx0 + w * length
            d.rectangle(
                (bx0, y + 2, bx1, y + rowh - 2),
                fill=rgba(col, alpha * 0.9),
                outline=rgba(INK, alpha * 0.5),
            )
            if bx1 - bx0 > 70:
                d.text(
                    (bx0 + 6, y + rowh / 2),
                    label,
                    font=f,
                    fill=rgba(INK, alpha),
                    anchor="lm",
                )


SIGNAL_ICONS = [icon_logs, icon_traces, icon_metrics, icon_profiles]


# ----------------------------------------------------------------------------
# scenes: each renders one frame at local time t (seconds since the scene start)
# ----------------------------------------------------------------------------
TITLE_FLASHES = [(1.1, 420, 0.9), (1.25, 460, 0.5), (4.6, 1500, 0.8), (7.2, 900, 0.5)]


def scene_title(t: float) -> Image.Image:
    img = Image.new("RGB", (W, H), NAVY)
    draw_sea(img, t, horizon=0.58, storm=0.9, seed=1)
    d = ImageDraw.Draw(img, "RGBA")
    # the ship far away, coming in
    k = ease_out(window(t, 0.5, 6.0))
    draw_ship(
        d,
        lerp(-200, 560, k),
        H * 0.7,
        lerp(60, 120, k),
        t,
        alpha=window(t, 0.5, 1.0),
        shields=False,
    )
    lightning(img, t, TITLE_FLASHES)
    a = ease_out(window(t, 0.8, 1.6))
    glow_text(
        img,
        (W / 2, H * 0.36 - 18 * (1 - a)),
        "ODDYSSEY",
        "bold",
        190,
        GOLD,
        alpha=a,
        radius=36,
    )
    text(
        d,
        (W / 2, H * 0.36 + 130),
        "Observability-Driven Development for coding agents",
        font("serif", 46),
        CREAM,
        anchor="mm",
        alpha=window(t, 2.0, 1.0),
    )
    text(
        d,
        (W / 2, H * 0.36 + 200),
        "a telemetry tale, told the Homeric way",
        font("italic", 34),
        GREY,
        anchor="mm",
        alpha=window(t, 3.0, 1.0),
    )
    return img


def scene_hero(t: float) -> Image.Image:
    img = Image.new("RGB", (W, H), NAVY)
    draw_sea(img, t, horizon=0.5, storm=0.35, seed=2)
    d = ImageDraw.Draw(img, "RGBA")
    k = ease_in_out(window(t, 0.0, 4.0))
    draw_ship(d, lerp(-400, W * 0.5, k), H * 0.66, 210, t, rock=0.6)
    text(
        d,
        (W / 2, 110),
        "Our Odysseus: your coding agent",
        font("bold", 76),
        GOLD,
        anchor="mm",
        alpha=window(t, 0.4, 1.0),
    )
    text(
        d,
        (W / 2, 190),
        "Claude Code, Copilot, Codex, Cursor, Gemini - one crew, one ship.",
        font("serif", 38),
        CREAM,
        anchor="mm",
        alpha=window(t, 1.6, 1.0),
    )
    a = window(t, 4.5, 1.0)
    card(d, (W / 2 - 700, H - 250, W / 2 + 700, H - 90), alpha=a)
    text(
        d,
        (W / 2, H - 200),
        "Every voyage starts with the same question:",
        font("italic", 36),
        GREY,
        anchor="mm",
        alpha=a,
    )
    text(
        d,
        (W / 2, H - 140),
        "what is my service really doing out there?",
        font("bold", 46),
        CREAM,
        anchor="mm",
        alpha=window(t, 5.5, 1.0),
    )
    return img


MONSTER_FLASHES = [
    (0.4, 300, 0.7),
    (3.3, 1200, 0.9),
    (3.45, 1250, 0.4),
    (7.8, 700, 0.8),
    (10.5, 1600, 0.6),
]


def scene_monsters(t: float) -> Image.Image:
    img = Image.new("RGB", (W, H), NAVY)
    draw_sea(img, t, horizon=0.62, storm=1.0, seed=3)
    d = ImageDraw.Draw(img, "RGBA")
    draw_ship(d, W * 0.5 + math.sin(t * 0.7) * 60, H * 0.86, 150, t, rock=1.6)
    lightning(img, t, MONSTER_FLASHES)
    d = ImageDraw.Draw(img, "RGBA")
    text(
        d,
        (W / 2, 90),
        "The monsters of the sea",
        font("bold", 76),
        RED,
        anchor="mm",
        alpha=window(t, 0.3, 0.8),
    )
    cw, gap = 400, 40
    total = 4 * cw + 3 * gap
    for i, (name, kind, tagline, icon, col) in enumerate(MONSTERS):
        a = ease_out(window(t, 1.2 + i * 1.9, 0.9))
        if a <= 0:
            continue
        x0 = (W - total) / 2 + i * (cw + gap)
        y0 = 190 + 40 * (1 - a)
        card(d, (x0, y0, x0 + cw, y0 + 470), alpha=a, border=col)
        icon(d, x0 + cw / 2, y0 + 170, 85, t, alpha=a)
        text(
            d,
            (x0 + cw / 2, y0 + 320),
            name,
            font("bold", 40),
            col,
            anchor="mm",
            alpha=a,
        )
        text(
            d,
            (x0 + cw / 2, y0 + 370),
            kind,
            font("serif", 34),
            CREAM,
            anchor="mm",
            alpha=a,
        )
        # tagline wrapped on two lines
        words, lines, cur = tagline.split(), [], ""
        for wd in words:
            trial = (cur + " " + wd).strip()
            if text_width(font("italic", 24), trial) > cw - 40:
                lines.append(cur)
                cur = wd
            else:
                cur = trial
        lines.append(cur)
        for j, line in enumerate(lines):
            text(
                d,
                (x0 + cw / 2, y0 + 415 + j * 28),
                line,
                font("italic", 24),
                GREY,
                anchor="mm",
                alpha=a,
            )
    text(
        d,
        (W / 2, H - 60),
        "Odysseus had a crew, a ship, and a plan. He was still blind past the horizon.",
        font("italic", 32),
        CREAM,
        anchor="mm",
        alpha=window(t, 9.5, 1.0),
    )
    return img


def scene_gods(t: float) -> Image.Image:
    img = Image.new("RGB", (W, H), NAVY)
    draw_sea(img, t, horizon=0.78, storm=0.3, seed=4)
    d = ImageDraw.Draw(img, "RGBA")
    draw_ship(d, W * 0.84, H * 0.93, 120, t, rock=0.5, shields=False)
    text(
        d,
        (W / 2, 80),
        "The gods send their signs",
        font("bold", 76),
        GOLD,
        anchor="mm",
        alpha=window(t, 0.3, 0.8),
    )
    cw, gap = 420, 34
    total = 4 * cw + 3 * gap
    for i, (name, signal, col, line) in enumerate(GODS):
        start = 1.0 + i * 2.6
        a = ease_out(window(t, start, 0.8))
        if a <= 0:
            continue
        x0 = (W - total) / 2 + i * (cw + gap)
        y0 = 150 + 30 * (1 - a)
        card(d, (x0, y0, x0 + cw, y0 + 560), alpha=a, border=col)
        # a beam from the sky onto the ship
        beam_a = a * (0.35 + 0.15 * math.sin(t * 5 + i))
        d.polygon(
            [
                (x0 + cw / 2 - 30, y0 + 560),
                (x0 + cw / 2 + 30, y0 + 560),
                (W * 0.84 + 20, H * 0.9),
                (W * 0.84 - 20, H * 0.9),
            ],
            fill=rgba(col, beam_a * 0.25),
        )
        text(
            d, (x0 + cw / 2, y0 + 50), name, font("bold", 46), col, anchor="mm", alpha=a
        )
        text(
            d,
            (x0 + cw / 2, y0 + 100),
            signal,
            font("serif", 36),
            CREAM,
            anchor="mm",
            alpha=a,
        )
        progress = window(t, start + 0.6, 1.6)
        SIGNAL_ICONS[i](
            d, (x0 + 30, y0 + 150, x0 + cw - 30, y0 + 430), t, progress, alpha=a
        )
        text(
            d,
            (x0 + cw / 2, y0 + 480),
            line,
            font("italic", 24),
            GREY,
            anchor="mm",
            alpha=a,
        )
    a = window(t, 11.0, 1.0)
    text(
        d,
        (W / 2, H - 200),
        "All four speak OpenTelemetry.",
        font("bold", 38),
        CREAM,
        anchor="mm",
        alpha=a,
    )
    text(
        d,
        (W / 2, H - 150),
        "Locally: one Grafana stack, piloted by the oddyssey MCP server.",
        font("serif", 30),
        GREY,
        anchor="mm",
        alpha=window(t, 11.8, 1.0),
    )
    text(
        d,
        (W / 2, H - 110),
        "Remotely: Grafana, Datadog, Dynatrace, Azure Monitor, CloudWatch, Splunk.",
        font("serif", 30),
        GREY,
        anchor="mm",
        alpha=window(t, 12.4, 1.0),
    )
    return img


ERR_BEFORE = [
    0.05,
    0.1,
    0.3,
    0.5,
    0.62,
    0.7,
    0.66,
    0.72,
    0.7,
    0.74,
    0.7,
    0.72,
    0.71,
    0.73,
    0.7,
    0.72,
]
ERR_AFTER = [0.7, 0.4, 0.15, 0.04, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def scene_battle(t: float) -> Image.Image:
    img = Image.new("RGB", (W, H), NAVY)
    fixed_k = ease_in_out(window(t, 9.0, 2.0))
    draw_sea(img, t, horizon=0.55, storm=lerp(1.0, 0.25, fixed_k), seed=5)
    d = ImageDraw.Draw(img, "RGBA")
    # Scylla on the left, lunging at the ship - then fading once fixed
    mon_a = 1 - fixed_k
    lunge = max(0.0, math.sin(t * 2.6)) * 70 * mon_a
    icon_bug(d, W * 0.22 + lunge, H * 0.7, 200 * (1 - 0.5 * fixed_k), t, alpha=mon_a)
    draw_ship(d, W * 0.66 + lunge * 0.4, H * 0.72, 170, t, rock=1.4 * mon_a + 0.4)
    text(
        d,
        (W / 2, 80),
        "The battle",
        font("bold", 76),
        GOLD,
        anchor="mm",
        alpha=window(t, 0.2, 0.8),
    )
    # the monster's label
    a = window(t, 0.8, 0.8) * mon_a
    card(
        d,
        (W * 0.22 - 300, H * 0.7 + 190, W * 0.22 + 300, H * 0.7 + 280),
        alpha=a,
        border=RED,
    )
    text(
        d,
        (W * 0.22, H * 0.7 + 235),
        "execute_tool: 23 % in error",
        font("mono", 30),
        RED,
        anchor="mm",
        alpha=a,
    )
    # the gods' signs arrive, one per second
    finding_lines = [
        (
            "Mimir",
            "gen_ai.client.operation.duration: 23 % of execute_tool carry error.type",
            BLUE,
        ),
        (
            "Tempo",
            "span execute_tool web_search: 30 s, error.type=timeout, on every failure",
            TEAL,
        ),
        (
            "Loki",
            '"429 rate limited" from the search API, gen_ai.tool.name=web_search, no retry',
            GOLD,
        ),
        ("Pyroscope", "91 % of wall time waiting on the web_search socket", ORANGE),
    ]
    bx0, by0 = W * 0.5 - 660, 150
    fa = window(t, 2.0, 0.8)
    card(d, (bx0, by0, bx0 + 1320, by0 + 290), alpha=fa)
    text(
        d,
        (bx0 + 30, by0 + 34),
        "Finding F1 - what the gods saw",
        font("bold", 32),
        CREAM,
        anchor="lm",
        alpha=fa,
    )
    for i, (god, line, col) in enumerate(finding_lines):
        la = window(t, 2.8 + i * 1.1, 0.5)
        y = by0 + 90 + i * 46
        d.ellipse((bx0 + 34, y - 10, bx0 + 54, y + 10), fill=rgba(col, la))
        text(
            d,
            (bx0 + 70, y),
            god.ljust(10),
            font("mono", 24),
            col,
            anchor="lm",
            alpha=la,
        )
        text(d, (bx0 + 220, y), line, font("mono", 24), CREAM, anchor="lm", alpha=la)
        d.line(
            [(bx0 + 44, y), (W * 0.66 + lunge * 0.4, H * 0.72 - 230)],
            fill=rgba(col, la * 0.35),
            width=3,
        )
    # the fix, then the verification
    fix_a = window(t, 7.5, 0.8)
    card(
        d,
        (W * 0.5 - 660, by0 + 320, W * 0.5 + 660, by0 + 400),
        alpha=fix_a,
        border=GREEN,
    )
    text(
        d,
        (W * 0.5, by0 + 360),
        "The SDD wave: spec -> plan -> fix: back off and retry web_search on 429, cap its timeout at 5 s",
        font("serif", 30),
        GREEN,
        anchor="mm",
        alpha=fix_a,
    )
    # error-rate chart on the right, dropping to zero once fixed
    ca = window(t, 3.0, 0.8)
    series = ERR_BEFORE + [lerp(0.72, v, fixed_k) for v in ERR_AFTER]
    icon_metrics(
        d,
        (W - 470, H - 330, W - 60, H - 80),
        t,
        1.0,
        alpha=ca,
        series=series,
        color=RED,
        threshold=0.08,
    )
    text(
        d,
        (W - 265, H - 350),
        "execute_tool error rate",
        font("mono", 24),
        RED,
        anchor="mm",
        alpha=ca,
    )
    va = window(t, 11.2, 0.8)
    glow_text(
        img,
        (W * 0.38, H - 140),
        "Verified: 0 errors on 1,200 execute_tool spans",
        "bold",
        50,
        GREEN,
        alpha=va,
        radius=24,
    )
    text(
        d,
        (W * 0.38, H - 80),
        "every check of the stored protocol passes - measured, not assumed",
        font("serif", 30),
        CREAM,
        anchor="mm",
        alpha=va,
    )
    return img


TERMINAL = [
    ("$ /odd-instrument-otel add OpenTelemetry to my project", CREAM, 0.0),
    ("  otel-instrumentation-expert investigates the codebase", GREY, 2.2),
    (
        "  report -> .odd/otel-instrumentation-reports/  (the SDD wave starts here)",
        GOLD,
        3.0,
    ),
    ("$ /odd-observe check that my agent's tool calls all succeed", CREAM, 4.4),
    (
        "  observe-run drives the run, queries logs, traces, metrics, profiles",
        GREY,
        6.6,
    ),
    ("  4 findings, evidence, replay protocol -> .odd/observe-run-reports/", TEAL, 7.4),
    ("$ /odd-verify check that the last report has been fixed", CREAM, 8.8),
    (
        "  same agent replays the stored protocol: before, after, pass criterion",
        GREY,
        10.6,
    ),
    ("  9/9 checks pass - measured, not assumed", GREEN, 11.4),
]


def scene_loop(t: float) -> Image.Image:
    img = Image.new("RGB", (W, H), NAVY)
    draw_sea(img, t, horizon=0.86, storm=0.2, seed=6)
    d = ImageDraw.Draw(img, "RGBA")
    text(
        d,
        (W / 2, 80),
        "Instrument once, then the loop",
        font("bold", 76),
        GOLD,
        anchor="mm",
        alpha=window(t, 0.2, 0.8),
    )
    # terminal window
    tx0, ty0, tx1, ty1 = 80, 150, 1150, 800
    card(
        d,
        (tx0, ty0, tx1, ty1),
        alpha=window(t, 0.4, 0.6),
        border=GREY,
        fill=(6, 10, 20),
        radius=14,
    )
    for i, col in enumerate((RED, GOLD, GREEN)):
        d.ellipse(
            (tx0 + 22 + i * 28, ty0 + 16, tx0 + 40 + i * 28, ty0 + 34),
            fill=rgba(col, 0.9),
        )
    f = font("mono", 22)
    y = ty0 + 70
    for line, col, start in TERMINAL:
        if t < start:
            break
        chars = int((t - start) * 55) if line.startswith("$") else len(line)
        shown = line[:chars]
        text(d, (tx0 + 30, y), shown, f, col, anchor="lm", shadow=False)
        if line.startswith("$") and chars < len(line) and int(t * 3) % 2 == 0:
            d.rectangle(
                (
                    tx0 + 30 + text_width(f, shown) + 4,
                    y - 12,
                    tx0 + 30 + text_width(f, shown) + 16,
                    y + 12,
                ),
                fill=rgba(CREAM, 0.9),
            )
        y += 46
    # the cycle diagram on the right: instrument is the entry step, the loop is observe -> fix -> verify
    cx, cy, r = 1520, 500, 190
    steps = [
        ("Observe", TEAL, -math.pi / 2, (0, -58)),
        ("Spec, plan, fix", GREEN, math.pi / 6, (0, 56)),
        ("Verify", BLUE, 5 * math.pi / 6, (0, 56)),
    ]
    da = window(t, 1.0, 1.0)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=rgba(GREY, 0.5 * da), width=4)
    # entry arrow from the one-time instrumentation into the loop
    ex, ey = cx - 250, cy - 330
    ox, oy = cx + r * math.cos(-math.pi / 2), cy + r * math.sin(-math.pi / 2)
    d.line([(ex, ey), (ox - 30, oy - 30)], fill=rgba(GOLD, 0.7 * da), width=4)
    d.polygon(
        [(ox - 22, oy - 22), (ox - 52, oy - 30), (ox - 30, oy - 52)],
        fill=rgba(GOLD, 0.9 * da),
    )
    d.ellipse((ex - 22, ey - 22, ex + 22, ey + 22), fill=rgba(GOLD, da))
    text(
        d,
        (ex - 34, ey),
        "Instrument, once",
        font("bold", 28),
        GOLD,
        anchor="rm",
        alpha=da,
    )
    spin = t * 0.5
    for i, (label, col, ang, off) in enumerate(steps):
        px, py = cx + r * math.cos(ang), cy + r * math.sin(ang)
        lit = 0.55 + 0.45 * (0.5 + 0.5 * math.cos(spin * 2 - i * 2 * math.pi / 3))
        d.ellipse((px - 26, py - 26, px + 26, py + 26), fill=rgba(col, da * lit))
        text(
            d,
            (px + off[0], py + off[1]),
            label,
            font("bold", 28),
            col,
            anchor="mm",
            alpha=da,
        )
    # a travelling dot around the loop
    ang = -math.pi / 2 + (t * 0.8) % (2 * math.pi)
    d.ellipse(
        (
            cx + r * math.cos(ang) - 10,
            cy + r * math.sin(ang) - 10,
            cx + r * math.cos(ang) + 10,
            cy + r * math.sin(ang) + 10,
        ),
        fill=rgba(CREAM, da),
    )
    text(d, (cx, cy), "ODD", font("bold", 60), CREAM, anchor="mm", alpha=da)
    text(d, (cx, cy + 50), "and again", font("italic", 26), GREY, anchor="mm", alpha=da)
    a = window(t, 12.2, 1.0)
    text(
        d,
        (W / 2, H - 130),
        "Also aboard: /odd-status (where is the loop?), /odd-instrument-bench (k6 benchmarks), /odd-config (switch stack).",
        font("serif", 30),
        GREY,
        anchor="mm",
        alpha=a,
    )
    return img


TREE = [
    (".odd/", GOLD, 0),
    ("otel-instrumentation-reports/", CREAM, 1),
    ("2026-08-22-mcp-server-instrumentation.md", GREY, 2),
    ("observe-run-reports/", CREAM, 1),
    ("2026-08-22-2154-mcp-otel-instrumentation-verification.md", GREY, 2),
    ("2026-08-22-2227-verify-mcp-otel-instrumentation-verification.md", GREY, 2),
    ("benchmarks/", CREAM, 1),
    ("mcp-server-read-heavy/  (script.js + manifest)", GREY, 2),
    ("decisions.md", CREAM, 1),
]


def scene_memory(t: float) -> Image.Image:
    img = Image.new("RGB", (W, H), NAVY)
    draw_sea(img, t, horizon=0.8, storm=0.15, seed=7)
    d = ImageDraw.Draw(img, "RGBA")
    draw_ship(d, W * 0.82, H * 0.9, 110, t, rock=0.4, shields=False)
    text(
        d,
        (W / 2, 80),
        "The ship's log",
        font("bold", 76),
        GOLD,
        anchor="mm",
        alpha=window(t, 0.2, 0.8),
    )
    text(
        d,
        (W / 2, 150),
        "every report lands in .odd/, committed and versioned with the code",
        font("italic", 34),
        GREY,
        anchor="mm",
        alpha=window(t, 0.8, 0.8),
    )
    x0, y0 = 300, 220
    card(
        d,
        (x0 - 40, y0 - 20, x0 + 1000, y0 + 420),
        alpha=window(t, 0.6, 0.6),
        border=GREY,
        fill=(6, 10, 20),
        radius=14,
    )
    f = font("mono", 26)
    for i, (name, col, depth) in enumerate(TREE):
        a = window(t, 1.2 + i * 0.35, 0.4)
        prefix = "" if depth == 0 else ("|-- " if depth == 1 else "|   |-- ")
        text(
            d,
            (x0, y0 + 20 + i * 42),
            prefix + name,
            f,
            col,
            anchor="lm",
            alpha=a,
            shadow=False,
        )
    lines = [
        ("Shared with the whole crew.", 5.0),
        ("Recalled as the baseline of the next run.", 5.8),
        ("Append-only: the loop accumulates knowledge instead of starting blind.", 6.6),
    ]
    for i, (line, start) in enumerate(lines):
        text(
            d,
            (1350, 300 + i * 70),
            line,
            font("serif", 32),
            CREAM,
            anchor="lm",
            alpha=window(t, start, 0.7),
        )
    return img


@functools.lru_cache(maxsize=1)
def banner() -> Image.Image:
    for path in BANNER_CANDIDATES:
        if path.exists():
            return Image.open(path).convert("RGB")
    return Image.new("RGB", (W, H), DEEP)


def banner_frame(t: float, dur: float, zoom_to: float) -> Image.Image:
    """The banner cropped to the frame, slowly zooming in (Ken Burns)."""
    src = banner()
    zoom = lerp(1.0, zoom_to, ease_in_out(window(t, 0, dur)))
    sw, sh = src.size
    scale = max(W / sw, H / sh) * zoom
    cw, ch = int(W / scale), int(H / scale)
    cx = int((sw - cw) / 2 + lerp(-40, 40, t / dur))
    cy = int((sh - ch) / 2)
    return src.crop((cx, cy, cx + cw, cy + ch)).resize(
        (W, H), Image.Resampling.BILINEAR
    )


def scene_opening(t: float) -> Image.Image:
    # the banner, full brightness, as the very first frame: it is the thumbnail GitHub
    # shows for an uploaded video, so the README keeps the banner as its poster
    return banner_frame(t, 2.5, 1.05)


def scene_outro(t: float) -> Image.Image:
    # Ken Burns over the banner, darkened for the closing text
    src = banner()
    zoom = lerp(1.0, 1.12, ease_in_out(window(t, 0, 9)))
    sw, sh = src.size
    scale = max(W / sw, H / sh) * zoom
    cw, ch = int(W / scale), int(H / scale)
    cx = int((sw - cw) / 2 + lerp(-40, 40, t / 9))
    cy = int((sh - ch) / 2)
    img = src.crop((cx, cy, cx + cw, cy + ch)).resize((W, H), Image.Resampling.BILINEAR)
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle((0, 0, W, H), fill=rgba(NAVY, 0.45 + 0.15 * window(t, 2, 2)))
    img.paste(vignette(), (0, 0), vignette())
    glow_text(
        img,
        (W / 2, H * 0.3),
        "Sail on.",
        "bold",
        120,
        GOLD,
        alpha=window(t, 0.3, 1.0),
        radius=30,
    )
    text(
        d,
        (W / 2, H * 0.3 + 110),
        "Instrument once. Then observe, fix, verify. Repeat.",
        font("serif", 44),
        CREAM,
        anchor="mm",
        alpha=window(t, 1.4, 1.0),
    )
    a = window(t, 2.6, 1.0)
    card(
        d,
        (W / 2 - 800, H * 0.6 - 72, W / 2 + 800, H * 0.6 + 72),
        alpha=a,
        border=GREY,
        fill=(6, 10, 20),
        radius=14,
    )
    text(
        d,
        (W / 2, H * 0.6 - 24),
        "apm install using-system/oddyssey",
        font("mono", 34),
        TEAL,
        anchor="mm",
        alpha=a,
        shadow=False,
    )
    text(
        d,
        (W / 2, H * 0.6 + 34),
        "or from your CLI's plugin marketplace - Claude Code, Copilot, Codex, and friends",
        font("italic", 26),
        GREY,
        anchor="mm",
        alpha=a,
    )
    text(
        d,
        (W / 2, H * 0.6 + 140),
        "github.com/using-system/oddyssey",
        font("bold", 44),
        GOLD,
        anchor="mm",
        alpha=window(t, 3.4, 1.0),
    )
    text(
        d,
        (W / 2, H * 0.6 + 200),
        "MIT - built on OpenTelemetry - packaged for every CLI coding agent",
        font("italic", 28),
        GREY,
        anchor="mm",
        alpha=window(t, 4.0, 1.0),
    )
    return img


SCENES = [  # (name, duration in seconds, render function)
    ("opening", 2.5, scene_opening),
    ("title", 8.5, scene_title),
    ("hero", 8.5, scene_hero),
    ("monsters", 12.5, scene_monsters),
    ("gods", 15.0, scene_gods),
    ("battle", 14.0, scene_battle),
    ("loop", 15.0, scene_loop),
    ("memory", 9.0, scene_memory),
    ("outro", 9.5, scene_outro),
]


# ----------------------------------------------------------------------------
# timeline: crossfade between consecutive scenes, fade to black at both ends
# ----------------------------------------------------------------------------
def total_duration() -> float:
    return sum(dur for _, dur, _ in SCENES)


def render_frame(gt: float) -> Image.Image:
    """Compose the frame at global time `gt`."""
    start = 0.0
    for i, (name, dur, fn) in enumerate(SCENES):
        end = start + dur
        if gt < end or i == len(SCENES) - 1:
            t = min(gt - start, dur)
            img = fn(t)
            # crossfade into the next scene during the last XFADE seconds
            if i + 1 < len(SCENES) and gt > end - XFADE:
                k = (gt - (end - XFADE)) / XFADE
                nxt = SCENES[i + 1][2](gt - (end - XFADE))
                img = Image.blend(img, nxt, ease_in_out(k))
            break
        start = end
    # fade to black at the very end (no fade-in: frame 0 is the banner, the video's thumbnail)
    fade = 1 - window(gt, total_duration() - 1.2, 1.2)
    if fade < 1:
        img = Image.blend(Image.new("RGB", (W, H), (0, 0, 0)), img, fade)
    return img


def encode(
    out_path: Path,
    fps: int,
    scale: float,
    music: Path | None,
    quiet: bool,
    crf: int = 26,
):
    ow, oh = int(W * scale) // 2 * 2, int(H * scale) // 2 * 2
    duration = total_duration()
    nframes = int(duration * fps)
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error" if quiet else "warning",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{ow}x{oh}",
        "-r",
        str(fps),
        "-i",
        "-",
    ]
    if music:
        cmd += [
            "-i",
            str(music),
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-af",
            f"afade=t=out:st={duration - 2.5}:d=2.5",
            "-shortest",
        ]
    # CRF 26 + tune animation: flat colours and sharp text compress very well (~30 MB for 92 s);
    # CRF 18 is near-lossless and more than twice the size, for no visible difference.
    cmd += [
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        str(crf),
        "-tune",
        "animation",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-t",
        f"{duration:.3f}",
        str(out_path),
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        for n in range(nframes):
            img = render_frame(n / fps)
            if scale != 1.0:
                img = img.resize((ow, oh), Image.Resampling.BILINEAR)
            proc.stdin.write(img.tobytes())
            if n % fps == 0:
                sys.stderr.write(
                    f"\r  {n / fps:5.1f}s / {duration:.1f}s  ({100 * n / nframes:4.1f} %)"
                )
                sys.stderr.flush()
    finally:
        proc.stdin.close()
        proc.wait()
    sys.stderr.write("\n")
    if proc.returncode != 0:
        raise SystemExit(f"ffmpeg failed with exit code {proc.returncode}")


def synthesize_music(path: Path) -> Path:
    """Generate the ambient soundtrack with make_music.py, timed on this timeline."""
    import make_music

    starts, acc = {}, 0.0
    for name, dur, _ in SCENES:
        starts[name] = acc
        acc += dur
    starts["end"] = acc
    flashes = [(starts["title"] + ft, s) for (ft, _, s) in TITLE_FLASHES] + [
        (starts["monsters"] + ft, s) for (ft, _, s) in MONSTER_FLASHES
    ]
    print(f"synthesizing soundtrack -> {path}")
    return make_music.render(acc, starts, flashes, path)


def stills(count: int, out_dir: Path):
    """Dump evenly spaced frames plus one per scene start, for a quick visual check."""
    out_dir.mkdir(parents=True, exist_ok=True)
    duration = total_duration()
    times = [duration * (i + 0.5) / count for i in range(count)]
    for i, gt in enumerate(times):
        render_frame(gt).save(out_dir / f"still-{i:02d}-{gt:05.1f}s.png")
    print(f"wrote {count} stills to {out_dir}")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--out", type=Path, default=OUT / "oddyssey.mp4")
    ap.add_argument(
        "--preview", action="store_true", help="15 fps, half size, fast encode"
    )
    ap.add_argument("--fps", type=int, default=None)
    ap.add_argument("--scale", type=float, default=None)
    ap.add_argument(
        "--music",
        type=Path,
        default=None,
        help="soundtrack to mix in (default: synthesize out/ambience.wav with make_music.py)",
    )
    ap.add_argument("--no-music", action="store_true", help="render a silent video")
    ap.add_argument(
        "--frames",
        type=int,
        default=0,
        help="only dump N stills to out/stills/ and exit",
    )
    ap.add_argument(
        "--crf",
        type=int,
        default=26,
        help="x264 quality, lower = bigger file (default 26; 18 near-lossless)",
    )
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if args.frames:
        stills(args.frames, OUT / "stills")
        return
    fps = args.fps or (15 if args.preview else FPS)
    scale = args.scale or (0.5 if args.preview else 1.0)
    out = (
        args.out
        if not args.preview or args.out != OUT / "oddyssey.mp4"
        else OUT / "oddyssey-preview.mp4"
    )
    music = args.music
    if music is None and not args.no_music:
        music = synthesize_music(OUT / "ambience.wav")
    print(f"rendering {total_duration():.1f}s at {fps} fps, scale {scale} -> {out}")
    encode(out, fps, scale, music, args.quiet, args.crf)
    print(f"done: {out}")


if __name__ == "__main__":
    main()
