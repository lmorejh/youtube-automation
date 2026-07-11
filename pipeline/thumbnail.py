"""영상 프레임(또는 업로드 이미지) + 큰 문구로 썸네일 생성."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import FONT_BOLD
from .media import probe_duration, probe_streams, run_ffmpeg


def make_thumbnail(video: str, text: str, workdir: Path, font: str | None = None,
                   color: str = "#ffdc3c", pos: float = 0.3, image: str | None = None) -> str:
    dest = workdir / "thumbnail.jpg"
    if image and Path(image).exists():
        frame = _fit_image(image, video, workdir)
    else:
        frame = workdir / "frame.jpg"
        ts = probe_duration(video) * min(max(pos, 0.0), 0.95)
        run_ffmpeg(["-ss", f"{ts:.2f}", "-i", video, "-frames:v", "1", "-q:v", "2", str(frame)])
    if not text.strip():
        Image.open(frame).convert("RGB").save(dest, quality=92)
        return str(dest)
    _draw_text(frame, text, dest, font or FONT_BOLD, _parse_hex(color))
    return str(dest)


def _fit_image(image: str, video: str, workdir: Path) -> Path:
    """업로드 이미지를 영상 해상도에 맞춰 비율 유지 크롭."""
    info = probe_streams(video)
    w, h = info["width"] or 1280, info["height"] or 720
    img = Image.open(image).convert("RGB")
    scale = max(w / img.width, h / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)))
    left, top = (img.width - w) // 2, (img.height - h) // 2
    frame = workdir / "frame.jpg"
    img.crop((left, top, left + w, top + h)).save(frame, quality=92)
    return frame


def _draw_text(frame: Path, text: str, dest: Path, font_path: str, color: tuple):
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
    d.text((x, y), text, font=font, fill=(*color, 255))
    Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB").save(dest, quality=92)


def _parse_hex(h: str) -> tuple:
    try:
        h = h.lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return (255, 220, 60)
