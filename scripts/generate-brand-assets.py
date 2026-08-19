#!/usr/bin/env python3
"""Generate the favicon set and the Open Graph share image.

Run BY HAND, on a developer machine, when the brand changes:

    python scripts/generate-brand-assets.py

The outputs are committed as binaries. Pillow is deliberately NOT in
requirements.txt, requirements-ml.lock, frontend/Dockerfile, or any CI job:
nothing in the build imports this script, and a tool that only ever runs on a
developer's machine must not become something the build depends on. That
mistake has cost this project twice already — httpx in Phase E and a nearly
shipped pyyaml check in Phase F — both times because the dev environment
happened to carry a package the production image did not.

Colours come from frontend/src/index.css, so the icons match the running app:

    --background: 220 20% 7%    near-black
    --primary:    142 72% 50%   green
"""

from __future__ import annotations

import colorsys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC = REPO_ROOT / "frontend" / "public"

PRODUCT_NAME = "AI Code Review"
TAGLINE = "Security, quality and dependency analysis for any Git repository."


def hsl(hue: float, saturation: float, lightness: float) -> tuple[int, int, int]:
    """CSS hsl() triple -> RGB, so the values above can be copied verbatim."""
    red, green, blue = colorsys.hls_to_rgb(hue / 360, lightness / 100, saturation / 100)
    return round(red * 255), round(green * 255), round(blue * 255)


BACKGROUND = hsl(220, 20, 7)
PRIMARY = hsl(142, 72, 50)
FOREGROUND = (250, 250, 250)
MUTED = (150, 158, 170)


def load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Best available system font, falling back to Pillow's bitmap default.

    The fallback keeps this script runnable on a machine with no DejaVu or
    Arial, at the cost of ugly output — which is visible immediately, unlike a
    crash halfway through writing four files.
    """
    candidates = (
        ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf"),
        ("arialbd.ttf", "arial.ttf"),
        ("segoeuib.ttf", "segoeui.ttf"),
    )
    for bold_name, regular_name in candidates:
        try:
            return ImageFont.truetype(bold_name if bold else regular_name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def rounded_mark(size: int) -> Image.Image:
    """The icon: a rounded square in the app's near-black, with a green glyph.

    The glyph is a magnifier over a code bracket — the app scans repositories,
    and Search is already the icon the sidebar uses for the landing route.
    """
    scale = 4  # supersample, then downscale, so the curves are not jagged
    canvas = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    edge = size * scale

    draw.rounded_rectangle(
        (0, 0, edge - 1, edge - 1),
        radius=int(edge * 0.22),
        fill=(*BACKGROUND, 255),
    )

    stroke = max(2, int(edge * 0.055))
    centre = edge * 0.45
    radius = edge * 0.20

    # Magnifier lens.
    draw.ellipse(
        (centre - radius, centre - radius, centre + radius, centre + radius),
        outline=(*PRIMARY, 255),
        width=stroke,
    )
    # Handle.
    draw.line(
        (
            centre + radius * 0.72,
            centre + radius * 0.72,
            centre + radius * 1.75,
            centre + radius * 1.75,
        ),
        fill=(*PRIMARY, 255),
        width=stroke,
    )

    return canvas.resize((size, size), Image.LANCZOS)


def write_favicon_svg() -> None:
    """Vector favicon, hand-written so it stays crisp and tiny."""
    background = "#%02x%02x%02x" % BACKGROUND
    primary = "#%02x%02x%02x" % PRIMARY
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="{PRODUCT_NAME}">
  <rect width="64" height="64" rx="14" fill="{background}"/>
  <circle cx="29" cy="29" r="13" fill="none" stroke="{primary}" stroke-width="4"/>
  <line x1="38" y1="38" x2="49" y2="49" stroke="{primary}" stroke-width="4" stroke-linecap="round"/>
</svg>
"""
    (PUBLIC / "favicon.svg").write_text(svg, encoding="utf-8")


def write_og_image() -> None:
    """1200x630 share card.

    twitter:card is summary_large_image, so without this file every shared link
    renders a blank card.
    """
    width, height = 1200, 630
    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)

    # A green rule at the top, echoing the sidebar's active-item accent.
    draw.rectangle((0, 0, width, 8), fill=PRIMARY)

    mark = rounded_mark(120)
    image.paste(mark, (80, 150), mark)

    draw.text((228, 168), PRODUCT_NAME, font=load_font(76, bold=True), fill=FOREGROUND)
    draw.text((80, 330), TAGLINE, font=load_font(30), fill=MUTED)

    image.save(PUBLIC / "og-image.png", "PNG", optimize=True)


def main() -> None:
    PUBLIC.mkdir(parents=True, exist_ok=True)

    write_favicon_svg()

    apple = rounded_mark(180)
    apple_flat = Image.new("RGB", apple.size, BACKGROUND)
    apple_flat.paste(apple, mask=apple)
    apple_flat.save(PUBLIC / "apple-touch-icon.png", "PNG", optimize=True)

    icon = rounded_mark(64)
    icon.save(PUBLIC / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])

    write_og_image()

    for name in ("favicon.svg", "favicon.ico", "apple-touch-icon.png", "og-image.png"):
        path = PUBLIC / name
        print(f"wrote {path.relative_to(REPO_ROOT)} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
