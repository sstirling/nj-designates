"""
Generate the social-share card (Open Graph / Twitter) for the site.

The card is composed directly in Pillow using Georgia TrueType rendering — an
earlier cairosvg-only approach mangled the "ffi" ligature in "official" and no
amount of tspan / font-feature tweaking fixed it. The logo itself still comes
from its SVG source, rasterized once via cairosvg (its all-caps curved text
renders cleanly).

Reads live figures from site/data/meta.json so the stat line stays in sync.
Run after every data refresh:
    python scripts/make_social_card.py
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import cairosvg
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
META = ROOT / "site" / "data" / "meta.json"
LOGO = ROOT / "site" / "assets" / "hereby-designated-logo.svg"
OUT_PNG = ROOT / "site" / "assets" / "social-card.png"

# Palette — keep in sync with site/css/base.css.
CREAM = (246, 241, 231)
INK = (26, 24, 18)
MUTED = (106, 101, 88)
NAVY = (11, 37, 69)
BRICK = (184, 64, 23)

# Font paths. Primary set is macOS. Fallback to whatever PIL can resolve.
FONT_CANDIDATES = {
    "bold": [
        "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
        "DejaVuSerif-Bold.ttf",
    ],
    "regular": [
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
        "DejaVuSerif.ttf",
    ],
    "italic": [
        "/System/Library/Fonts/Supplemental/Georgia Italic.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
        "DejaVuSerif-Italic.ttf",
    ],
}


def load_font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES[kind]:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    # Last resort — Pillow's bundled bitmap font. Ugly but won't crash.
    return ImageFont.load_default()


def render_logo(pixel_size: int) -> Image.Image:
    png = cairosvg.svg2png(
        bytestring=LOGO.read_bytes(),
        output_width=pixel_size,
        output_height=pixel_size,
    )
    return Image.open(io.BytesIO(png)).convert("RGBA")


def draw_star(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, color) -> None:
    """Five-point star centered at (cx, cy) with outer radius r."""
    import math
    pts = []
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5
        radius = r if i % 2 == 0 else r * 0.4
        pts.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    draw.polygon(pts, fill=color)


def main() -> None:
    meta = json.loads(META.read_text())
    total = f"{meta['total_bills']:,}"
    span = f"{meta['earliest_session']}–{meta['latest_session'] + 1}"

    W, H = 1200, 630
    img = Image.new("RGB", (W, H), CREAM)
    draw = ImageDraw.Draw(img)

    # Double-ruled border — echoes the seal's concentric rings.
    draw.rectangle([(28, 28), (W - 28, H - 28)], outline=NAVY, width=3)
    draw.rectangle([(40, 40), (W - 40, H - 40)], outline=NAVY, width=1)

    # Logo, left column.
    logo = render_logo(420)
    img.paste(logo, (90, 105), logo)

    # Right column: title, divider, tagline, stat. The text block is hand-tuned
    # so its vertical center aligns with the logo's (logo center ≈ y=315).
    x = 560
    y = 160

    f_title = load_font("bold", 58)
    draw.text((x, y), "Hereby Designated", font=f_title, fill=INK)

    # Decorative divider: ruled line · star · ruled line.
    dy = y + 112
    draw.line([(x, dy), (x + 56, dy)], fill=BRICK, width=2)
    draw_star(draw, x + 76, dy, 8, BRICK)
    draw.line([(x + 96, dy), (x + 152, dy)], fill=BRICK, width=2)

    f_tag = load_font("italic", 30)
    lines = [
        "Working to be designated the",
        "official state designation tracker",
        "since 2026.",
    ]
    line_y = dy + 40
    for line in lines:
        draw.text((x, line_y), line, font=f_tag, fill=MUTED)
        line_y += 42

    f_stat = load_font("bold", 22)
    draw.text((x, line_y + 32), f"{total} ceremonial bills · {span}", font=f_stat, fill=INK)

    img.save(OUT_PNG, format="PNG", optimize=True)
    print(f"wrote {OUT_PNG.relative_to(ROOT)} ({OUT_PNG.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
