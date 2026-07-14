
import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT_DIR = Path("assets")
OUT_DIR.mkdir(exist_ok=True)

SIZE = 1024


def lerp_colour(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(4))


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2
    r  = size // 2

    bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bg_d = ImageDraw.Draw(bg)
    steps = 120
    for i in range(steps, 0, -1):
        t   = i / steps
        ri  = int(r * t)
        col = lerp_colour((7, 24, 40, 255), (3, 12, 20, 255), 1 - t)
        bg_d.ellipse([cx - ri, cy - ri, cx + ri, cy + ri], fill=col)
    img.alpha_composite(bg)

    for ring_r in [r * 0.35, r * 0.58, r * 0.78, r * 0.93]:
        ri = int(ring_r)
        d.ellipse(
            [cx - ri, cy - ri, cx + ri, cy + ri],
            outline=(0, 120, 200, 22), width=max(1, size // 128)
        )

    pw = int(r * 1.18)
    ph = int(r * 0.52)
    margin = int(r * 0.1)
    px, py = cx, cy + int(r * 0.02)

    rock_pts = _ellipse_points(px, py, pw + margin, ph + margin, 128)
    d.polygon(rock_pts, fill=(18, 28, 42, 240))

    pass_pts = _ellipse_points(px, py, pw, ph, 128)
    d.polygon(pass_pts, fill=(8, 18, 32, 255))

    passage_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pd = ImageDraw.Draw(passage_img)
    grad_steps = 48
    for gi in range(grad_steps):
        t = gi / grad_steps
        sub_ph = int(ph * (1 - t))
        sub_py = py - int(ph * t * 0.5)
        alpha  = int(28 * (1 - t))
        col    = (0, 140 - int(60 * t), 200 - int(80 * t), alpha)
        sub_pts = _ellipse_points(px, sub_py, pw - int(pw * t * 0.05), sub_ph, 64)
        if len(sub_pts) >= 3:
            pd.polygon(sub_pts, fill=col)
    img.alpha_composite(passage_img)

    for inset in [2, 4, 7]:
        inset_px = int(size / 512 * inset)
        alpha = max(12, 30 - inset * 3)
        inset_pts = _ellipse_points(px, py, pw - inset_px, ph - inset_px // 2, 64)
        if len(inset_pts) >= 3:
            d.polygon(inset_pts, outline=(0, 100, 200, alpha), width=1)

    n_stations = 11
    station_xs = [int(px - pw * 0.88 + pw * 2 * 0.88 * i / (n_stations - 1))
                  for i in range(n_stations)]

    def station_y(i):
        phase = i / (n_stations - 1)
        return int(py + math.sin(phase * math.pi * 1.8) * ph * 0.22)

    station_ys = [station_y(i) for i in range(n_stations)]
    stations   = list(zip(station_xs, station_ys))

    lw = max(2, size // 128)

    for i in range(len(stations) - 1):
        d.line([stations[i], stations[i + 1]],
               fill=(0, 180, 255, 45), width=lw * 7)

    for i in range(len(stations) - 1):
        d.line([stations[i], stations[i + 1]],
               fill=(0, 210, 255, 90), width=lw * 3)

    for i in range(len(stations) - 1):
        d.line([stations[i], stations[i + 1]],
               fill=(0, 230, 255, 230), width=lw)

    dot_r  = max(3, size // 80)
    halo_r = dot_r * 3

    for i, (sx, sy) in enumerate(stations):
        d.ellipse([sx - halo_r, sy - halo_r, sx + halo_r, sy + halo_r],
                  fill=(0, 210, 255, 30))
        t   = i / (n_stations - 1)
        dot_col = lerp_colour((100, 220, 255, 255), (30, 120, 210, 255), t)
        d.ellipse([sx - dot_r, sy - dot_r, sx + dot_r, sy + dot_r],
                  fill=dot_col)
        cr = max(1, dot_r // 2)
        d.ellipse([sx - cr, sy - cr, sx + cr, sy + cr],
                  fill=(220, 240, 255, 200))

    bar_x  = px + pw - int(pw * 0.12)
    bar_y1 = py - ph + int(ph * 0.22)
    bar_y2 = py + ph - int(ph * 0.22)
    bar_w  = max(2, size // 200)
    bar_steps = 16
    for bi in range(bar_steps):
        t   = bi / bar_steps
        by1 = bar_y1 + int((bar_y2 - bar_y1) * t)
        by2 = bar_y1 + int((bar_y2 - bar_y1) * (bi + 1) / bar_steps)
        col = lerp_colour((0, 150, 220, 120), (0, 50, 130, 120), t)
        d.rectangle([bar_x, by1, bar_x + bar_w, by2], fill=col)

    font_size = max(8, size // 9)
    try:
        font      = ImageFont.truetype("/System/Library/Fonts/SFNSMono.ttf", font_size)
        sub_font  = ImageFont.truetype("/System/Library/Fonts/SFNSMono.ttf", max(4, size // 28))
    except Exception:
        try:
            font      = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
            sub_font  = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", max(4, size // 28))
        except Exception:
            font     = ImageFont.load_default()
            sub_font = font

    text    = "TEHOM"
    bbox    = d.textbbox((0, 0), text, font=font)
    tw, th  = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx      = cx - tw // 2
    ty      = cy + int(r * 0.62)

    glow_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd       = ImageDraw.Draw(glow_img)
    for off in [(2, 2), (-2, -2), (2, -2), (-2, 2), (0, 3), (0, -3), (3, 0), (-3, 0)]:
        gd.text((tx + off[0], ty + off[1]), text, font=font, fill=(0, 150, 255, 60))
    glow_img = glow_img.filter(ImageFilter.GaussianBlur(size // 128))
    img.alpha_composite(glow_img)

    d.text((tx, ty), text, font=font, fill=(200, 235, 255, 240))

    sub_text = "UNDERWATER CAVE SAR"
    sub_bbox = d.textbbox((0, 0), sub_text, font=sub_font)
    sw       = sub_bbox[2] - sub_bbox[0]
    d.text((cx - sw // 2, ty + th + max(4, size // 80)), sub_text,
           font=sub_font, fill=(0, 140, 200, 160))

    mask = Image.new("L", (size, size), 0)
    md   = ImageDraw.Draw(mask)
    md.ellipse([0, 0, size - 1, size - 1], fill=255)
    img.putalpha(mask)

    return img


def _ellipse_points(cx, cy, rx, ry, n=64):
    pts = []
    for i in range(n):
        angle = 2 * math.pi * i / n
        x = cx + rx * math.cos(angle)
        y = cy + ry * math.sin(angle)
        pts.append((x, y))
    return pts


def build_iconset(base: Image.Image) -> Path:
    iconset = OUT_DIR / "TEHOM.iconset"
    iconset.mkdir(exist_ok=True)

    sizes = [16, 32, 64, 128, 256, 512, 1024]
    for s in sizes:
        img = base.resize((s, s), Image.LANCZOS)
        img.save(iconset / f"icon_{s}x{s}.png")
        if s <= 512:
            img2x = base.resize((s * 2, s * 2), Image.LANCZOS)
            img2x.save(iconset / f"icon_{s}x{s}@2x.png")

    return iconset


def main():
    print("Generating TEHOM icon...")
    base = draw_icon(SIZE)

    ref_path = OUT_DIR / "icon_512.png"
    base.resize((512, 512), Image.LANCZOS).save(ref_path)
    print(f"  Saved: {ref_path}")

    iconset = build_iconset(base)
    print(f"  Built iconset: {iconset}")

    icns_path = OUT_DIR / "TEHOM.icns"
    ret = os.system(f'iconutil -c icns "{iconset}" -o "{icns_path}"')
    if ret == 0:
        print(f"  Created: {icns_path}  ({icns_path.stat().st_size // 1024} KB)")
    else:
        print("  iconutil failed — iconset is still available")

    print("\nDone.")


if __name__ == "__main__":
    main()
