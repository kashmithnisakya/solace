"""Build docs/demo.gif from the screenshots in docs/demo/frames.

    uv run --with pillow python scripts/make_demo_gif.py

Needs ffmpeg for a small, good-looking GIF. To refresh the demo after a UI change, capture new
375x812 light-mode screenshots of each scene listed in docs/demo/scenes.json (see docs/demo/README.md),
replace the files in docs/demo/frames, and run this script.
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "docs" / "demo"
OUT = ROOT / "docs" / "demo.gif"

WIDTH, HEIGHT = 375, 812  # phone screenshot size
BAND = 64  # caption band above each screen
FPS = 12
HOLD, FADE = 2.4, 0.4  # seconds per scene, seconds of crossfade


def font(size: int) -> ImageFont.ImageFont:
    for path in (
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def scene(frame: Path, caption: str, step: int, total: int) -> Image.Image:
    canvas = Image.new("RGB", (WIDTH, HEIGHT + BAND), "#f2f2f7")
    draw = ImageDraw.Draw(canvas)
    title = font(19)
    w = draw.textlength(caption, font=title)
    draw.text(((WIDTH - w) / 2, 16), caption, fill="#000000", font=title)
    # progress dots
    gap, r = 12, 3
    x0 = (WIDTH - (total - 1) * gap) / 2
    for i in range(total):
        colour = "#007aff" if i == step else "#c7c7cc"
        cx = x0 + i * gap
        draw.ellipse((cx - r, 46 - r, cx + r, 46 + r), fill=colour)
    shot = Image.open(frame).convert("RGB").resize((WIDTH, HEIGHT), Image.LANCZOS)
    canvas.paste(shot, (0, BAND))
    return canvas


def main() -> int:
    if not shutil.which("ffmpeg"):
        print("ffmpeg is required (brew install ffmpeg / apt install ffmpeg).", file=sys.stderr)
        return 1
    scenes = json.loads((DEMO / "scenes.json").read_text())
    images = [scene(DEMO / "frames" / s["frame"], s["caption"], i, len(scenes)) for i, s in enumerate(scenes)]
    hold, fade = int(HOLD * FPS), int(FADE * FPS)
    with tempfile.TemporaryDirectory() as tmp:
        n = 0
        for i, img in enumerate(images):
            nxt = images[(i + 1) % len(images)]
            for _ in range(hold):
                img.save(f"{tmp}/{n:05d}.png")
                n += 1
            for k in range(1, fade + 1):
                Image.blend(img, nxt, k / (fade + 1)).save(f"{tmp}/{n:05d}.png")
                n += 1
        scale = "scale=320:-1:flags=lanczos"
        subprocess.run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-y",
                "-framerate",
                str(FPS),
                "-i",
                f"{tmp}/%05d.png",
                "-vf",
                f"{scale},palettegen=stats_mode=diff",
                f"{tmp}/palette.png",
            ],
            check=True,
        )
        subprocess.run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-y",
                "-framerate",
                str(FPS),
                "-i",
                f"{tmp}/%05d.png",
                "-i",
                f"{tmp}/palette.png",
                "-lavfi",
                f"{scale}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle",
                "-loop",
                "0",
                str(OUT),
            ],
            check=True,
        )
    print(f"Wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB, {len(scenes)} scenes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
