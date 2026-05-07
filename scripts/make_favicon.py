"""
Rasterize the favicon SVG into the PNG / ICO files browsers expect.

Inputs:  assets/favicon.svg (simplified seal — no curved text)
         assets/hereby-designated-logo.svg (full logo, used for Apple touch)

Outputs: assets/favicon.ico         multi-size ICO (16, 32, 48)
         assets/favicon-32.png      legacy PNG fallback
         assets/favicon-16.png      legacy PNG fallback
         assets/apple-touch-icon.png 180x180 — iOS home-screen icon

Apple touch icon uses the FULL seal because iOS renders it at 180x180+ where
the curved text is legible and the brand reads better with it intact.

Run after editing assets/favicon.svg or the source logo:
    python scripts/make_favicon.py
"""

from __future__ import annotations

import io
from pathlib import Path

import cairosvg
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
FAVICON_SVG = ASSETS / "favicon.svg"
LOGO_SVG = ASSETS / "hereby-designated-logo.svg"


def svg_to_png(svg_path: Path, size: int) -> Image.Image:
    png_bytes = cairosvg.svg2png(
        bytestring=svg_path.read_bytes(),
        output_width=size,
        output_height=size,
    )
    return Image.open(io.BytesIO(png_bytes)).convert("RGBA")


def main() -> None:
    # Browser favicon — simplified seal, no curved text.
    img_16 = svg_to_png(FAVICON_SVG, 16)
    img_32 = svg_to_png(FAVICON_SVG, 32)
    img_48 = svg_to_png(FAVICON_SVG, 48)

    img_32.save(ASSETS / "favicon-32.png", format="PNG", optimize=True)
    img_16.save(ASSETS / "favicon-16.png", format="PNG", optimize=True)

    # Multi-resolution ICO. Browsers and Windows pick the best frame.
    img_48.save(
        ASSETS / "favicon.ico",
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48)],
    )

    # iOS home-screen icon — full logo with curved text, since 180x180 has the
    # resolution to render it legibly. iOS auto-rounds the corners.
    img_apple = svg_to_png(LOGO_SVG, 180)
    img_apple.save(ASSETS / "apple-touch-icon.png", format="PNG", optimize=True)

    for f in ("favicon.ico", "favicon-32.png", "favicon-16.png", "apple-touch-icon.png"):
        size = (ASSETS / f).stat().st_size
        print(f"wrote assets/{f} ({size:,} bytes)")


if __name__ == "__main__":
    main()
