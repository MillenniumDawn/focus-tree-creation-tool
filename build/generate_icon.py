"""
generate_icon.py — Creates icon.ico for the HOI4 Content Maker .exe

Generates a multi-resolution .ico file with a HOI4-styled icon.
Run automatically by build.bat, or manually:  python generate_icon.py
"""

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("[generate_icon] Pillow not installed — run: pip install Pillow")
    raise SystemExit(1)

import os

# ── Colour palette (HOI4 dark theme) ──────────────────────────────────────────
BG        = (13,  17,  28)    # very dark navy
GOLD      = (212, 175,  55)   # HOI4 gold
GOLD_DIM  = (160, 130,  40)
RED       = (180,  40,  40)
WHITE     = (220, 220, 220)

def make_frame(size):
    """Draw one frame of the icon at the given pixel size."""
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad  = max(1, size // 16)
    r    = size - 1

    # Background — rounded dark square
    corner = max(2, size // 8)
    draw.rounded_rectangle([0, 0, r, r], radius=corner, fill=BG)

    # Gold border
    bw = max(1, size // 20)
    draw.rounded_rectangle([bw, bw, r-bw, r-bw], radius=corner,
                            outline=GOLD, width=bw)

    # Inner design: a simplified gear / cog shape for sizes >= 32
    cx, cy = size // 2, size // 2
    if size >= 32:
        # Outer circle (gold ring)
        margin = size // 5
        draw.ellipse([margin, margin, r-margin, r-margin],
                     outline=GOLD, width=max(1, size//16))
        # Inner circle (filled dark)
        inner_m = size // 3
        draw.ellipse([inner_m, inner_m, r-inner_m, r-inner_m], fill=BG)

        # Letter "H" in centre (HOI4 reference)
        font_size = max(8, size // 3)
        try:
            # Try to load a system font
            for fname in ("arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf",
                          "LiberationSans-Bold.ttf", "FreeSansBold.ttf"):
                try:
                    font = ImageFont.truetype(fname, font_size)
                    break
                except Exception:
                    font = None
        except Exception:
            font = None

        if font is None:
            font = ImageFont.load_default()

        text = "H"
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
        except Exception:
            tw = th = font_size

        tx = cx - tw // 2
        ty = cy - th // 2 - max(1, size // 20)
        draw.text((tx, ty), text, fill=GOLD, font=font)

    else:
        # For tiny sizes (16px) just fill with gold "H" on dark bg
        draw.rectangle([pad*2, pad*2, r-pad*2, r-pad*2], fill=GOLD_DIM)
        draw.rectangle([pad*3, pad*3, r-pad*3, r-pad*3], fill=BG)

    return img


def main():
    sizes   = [256, 128, 64, 48, 32, 16]
    frames  = [make_frame(s) for s in sizes]
    out     = "icon.ico"

    # PIL needs the largest frame as the primary image
    frames[0].save(
        out,
        format  = "ICO",
        sizes   = [(s, s) for s in sizes],
        append_images = frames[1:],
    )

    kb = os.path.getsize(out) / 1024
    print(f"[generate_icon] Created {out}  ({kb:.1f} KB)  —  sizes: {sizes}")


if __name__ == "__main__":
    main()
