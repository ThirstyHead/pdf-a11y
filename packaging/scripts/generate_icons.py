"""Generate multi-format icons (.png, .ico, .icns) from SVG or Pillow rendering."""
import os
import shutil
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw

def render_master_image(size: int = 512) -> Image.Image:
    """Render a crisp master icon using Pillow."""
    img = Image.new("RGBA", (size, size), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded background
    rx = int(size * 0.22)
    margin = int(size * 0.04)
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=rx,
        fill=(30, 41, 59, 255),
        outline=(51, 65, 85, 255),
        width=int(size * 0.02),
    )

    # Document sheet
    doc_x0, doc_y0 = int(size * 0.22), int(size * 0.16)
    doc_x1, doc_y1 = int(size * 0.78), int(size * 0.84)
    draw.rounded_rectangle(
        [doc_x0, doc_y0, doc_x1, doc_y1],
        radius=int(size * 0.05),
        fill=(248, 250, 252, 255),
    )

    # Red PDF badge
    badge_x0, badge_y0 = int(size * 0.18), int(size * 0.25)
    badge_x1, badge_y1 = int(size * 0.46), int(size * 0.35)
    draw.rounded_rectangle(
        [badge_x0, badge_y0, badge_x1, badge_y1],
        radius=int(size * 0.02),
        fill=(220, 38, 38, 255),
    )

    # Outer accessibility ring
    cx, cy = int(size * 0.5), int(size * 0.58)
    radius = int(size * 0.18)
    draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        outline=(2, 132, 199, 255),
        width=int(size * 0.03),
    )

    # Accessibility figure head
    head_r = int(size * 0.04)
    head_y = cy - int(radius * 0.5)
    draw.ellipse(
        [cx - head_r, head_y - head_r, cx + head_r, head_y + head_r],
        fill=(2, 132, 199, 255),
    )

    # Arms
    arm_y = cy - int(radius * 0.1)
    arm_span = int(radius * 0.65)
    draw.line(
        [(cx - arm_span, arm_y), (cx + arm_span, arm_y)],
        fill=(2, 132, 199, 255),
        width=int(size * 0.028),
    )

    # Torso & Legs
    draw.line(
        [(cx, arm_y), (cx, cy + int(radius * 0.3))],
        fill=(2, 132, 199, 255),
        width=int(size * 0.028),
    )
    draw.line(
        [(cx, cy + int(radius * 0.3)), (cx - int(arm_span * 0.5), cy + int(radius * 0.7))],
        fill=(2, 132, 199, 255),
        width=int(size * 0.028),
    )
    draw.line(
        [(cx, cy + int(radius * 0.3)), (cx + int(arm_span * 0.5), cy + int(radius * 0.7))],
        fill=(2, 132, 199, 255),
        width=int(size * 0.028),
    )

    return img

def main():
    icons_dir = Path(__file__).resolve().parent.parent / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)

    master = render_master_image(size=1024)
    
    # Save standard PNG
    png_path = icons_dir / "pdf-a11y.png"
    master.resize((512, 512), Image.Resampling.LANCZOS).save(png_path, format="PNG")
    print(f"Generated {png_path}")

    # Save Windows ICO
    ico_path = icons_dir / "pdf-a11y.ico"
    master.save(
        ico_path,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"Generated {ico_path}")

    # Build macOS .icns
    icns_path = icons_dir / "pdf-a11y.icns"
    iconutil = shutil.which("iconutil")
    if iconutil:
        iconset_dir = icons_dir / "pdf-a11y.iconset"
        iconset_dir.mkdir(exist_ok=True)
        sizes = [
            (16, "icon_16x16.png"),
            (32, "icon_16x16@2x.png"),
            (32, "icon_32x32.png"),
            (64, "icon_32x32@2x.png"),
            (128, "icon_128x128.png"),
            (256, "icon_128x128@2x.png"),
            (256, "icon_256x256.png"),
            (512, "icon_256x256@2x.png"),
            (512, "icon_512x512.png"),
            (1024, "icon_512x512@2x.png"),
        ]
        for s, name in sizes:
            resized = master.resize((s, s), Image.Resampling.LANCZOS)
            resized.save(iconset_dir / name, format="PNG")
        subprocess.run([iconutil, "-c", "icns", str(iconset_dir), "-o", str(icns_path)], check=True)
        shutil.rmtree(iconset_dir)
        print(f"Generated {icns_path} via iconutil")
    else:
        # Fallback for non-macOS environments
        master.save(icns_path, format="ICNS")
        print(f"Generated {icns_path} via Pillow fallback")

if __name__ == "__main__":
    main()
