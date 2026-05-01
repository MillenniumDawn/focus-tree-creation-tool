"""
generate_icon.py — Creates icon.ico for the HOI4 Content Maker .exe

Generates a multi-resolution .ico file with a watermelon icon.
Run automatically by build.bat, or manually:  python generate_icon.py
"""

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("[generate_icon] Pillow not installed — run: pip install Pillow")
    raise SystemExit(1)

import math
import os

# ── Colour palette (watermelon) ───────────────────────────────────────────────
GREEN_DARK   = (28,  88,  28)   # outer rind
GREEN_LIGHT  = (80, 160,  50)   # rind stripes
WHITE_RIND   = (220, 242, 205)  # inner white rind
FLESH        = (210,  38,  38)  # red flesh
SEED         = (22,   14,   6)  # seeds


def make_frame(size):
    """Draw one watermelon cross-section frame at the given pixel size."""
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad = max(1, size // 14)
    r   = size - 1
    cx  = cy = size // 2

    # ── 1. Outer dark-green circle (rind) ─────────────────────────────────────
    draw.ellipse([pad, pad, r - pad, r - pad], fill=GREEN_DARK)

    # ── 2. Light-green stripes on the rind (skip for tiny sizes) ──────────────
    rind_w = max(2, size // 7)
    if size >= 24:
        num_stripes = 3 if size >= 48 else 2
        stripe_w    = max(1, rind_w // (num_stripes * 2 + 1))
        for i in range(num_stripes):
            offset = pad + stripe_w * (2 * i + 1)
            draw.ellipse([offset, offset, r - offset, r - offset],
                         outline=GREEN_LIGHT, width=max(1, stripe_w))

    # ── 3. White inner-rind ring ───────────────────────────────────────────────
    wi = pad + rind_w
    draw.ellipse([wi, wi, r - wi, r - wi], fill=WHITE_RIND)

    # ── 4. Red flesh ───────────────────────────────────────────────────────────
    white_w = max(1, size // 20)
    fi = wi + white_w
    draw.ellipse([fi, fi, r - fi, r - fi], fill=FLESH)

    # ── 5. Seeds (only for sizes >= 32) ───────────────────────────────────────
    if size >= 32:
        flesh_r = cx - fi          # radius of the flesh circle
        seed_r  = flesh_r * 0.55   # orbit radius for seeds
        sw      = max(1, size // 22)   # seed half-width
        sh      = max(2, size // 14)   # seed half-height

        # 5 seeds at evenly-spaced angles; fewer at smaller sizes
        angles = [-90, -18, 54, 126, 198]
        if size < 64:
            angles = angles[:3]

        for deg in angles:
            rad = math.radians(deg)
            sx  = int(cx + math.cos(rad) * seed_r)
            sy  = int(cy + math.sin(rad) * seed_r)
            draw.ellipse([sx - sw, sy - sh // 2,
                          sx + sw, sy + sh // 2], fill=SEED)

    return img


def main():
    sizes  = [256, 128, 64, 48, 32, 16]
    frames = [make_frame(s) for s in sizes]
    out    = "icon.ico"

    frames[0].save(
        out,
        format        = "ICO",
        sizes         = [(s, s) for s in sizes],
        append_images = frames[1:],
    )

    kb = os.path.getsize(out) / 1024
    print(f"[generate_icon] Created {out}  ({kb:.1f} KB)  —  sizes: {sizes}")


if __name__ == "__main__":
    main()
