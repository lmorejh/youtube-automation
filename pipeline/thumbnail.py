"""영상 중간 프레임 + 큰 제목 문구로 썸네일 생성."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import FONT_BOLD
from .media import probe_duration, run_ffmpeg


def make_thumbnail(video: str, text: str, workdir: Path, font: str | None = None) -> str:
    frame = workdir / "frame.jpg"
    mid = probe_duration(video) * 0.3
    run_ffmpeg(["-ss", f"{mid:.2f}", "-i", video, "-frames:v", "1", "-q:v", "2", str(frame)])
    dest = workdir / "thumbnail.jpg"
    _draw_text(frame, text, dest, font or FONT_BOLD)
    return str(dest)


def _draw_text(frame: Path, text: str, dest: Path, font_path: str):
    img = Image.open(frame).convert("RGB")
    w, h = img.size
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.rectangle([0, int(h * 0.55), w, h], fill=(0, 0, 0, 130))
    size = int(w * 0.09)
    font = ImageFont.truetype(font_path, size)
    while size > 20 and d.textlength(text, font=font) > w * 0.92:
        size = int(size * 0.9)
        font = ImageFont.truetype(font_path, size)
    tw = d.textlength(text, font=font)
    x, y = (w - tw) / 2, int(h * 0.66)
    d.text((x + 4, y + 4), text, font=font, fill=(0, 0, 0, 255))
    d.text((x, y), text, font=font, fill=(255, 220, 60, 255))
    Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB").save(dest, quality=92)
