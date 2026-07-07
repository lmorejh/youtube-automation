"""장면별 비주얼 준비: Pexels 스톡영상 다운로드 + Pillow로 슬라이드/자막 오버레이 렌더링."""
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont

from .config import FONT_BOLD, FONT_REGULAR, PEXELS_API_KEY

PALETTE = [((18, 32, 47), (52, 152, 219)), ((26, 20, 40), (155, 89, 182)),
           ((20, 40, 30), (46, 204, 113)), ((40, 26, 18), (230, 126, 34))]


def prepare_visuals(scenes: list[dict], fmt: str, style: str, size, workdir: Path, log):
    used_ids: set[int] = set()
    for i, scene in enumerate(scenes):
        scene["overlay"] = _make_overlay(scene, size, style, workdir / f"ov_{i:02d}.png", i)
        if style == "infographic":
            scene["image"] = _make_slide(scene, size, workdir / f"slide_{i:02d}.png", i)
            continue
        video = _fetch_stock(scene.get("visual_keywords", ""), fmt, workdir / f"stock_{i:02d}.mp4", used_ids)
        if video:
            scene["video"] = video
        else:
            log(f"장면 {i + 1}: 스톡영상 없음 → 배경 슬라이드로 대체")
            scene["image"] = _make_fallback(scene, size, workdir / f"bg_{i:02d}.png", i)


# ---------- Pexels 스톡영상 ----------

def _fetch_stock(keywords: str, fmt: str, dest: Path, used_ids: set) -> str | None:
    if not PEXELS_API_KEY or not keywords.strip():
        return None
    try:
        orientation = "portrait" if fmt == "short" else "landscape"
        r = httpx.get("https://api.pexels.com/videos/search",
                      params={"query": keywords, "orientation": orientation, "per_page": 8},
                      headers={"Authorization": PEXELS_API_KEY}, timeout=30)
        r.raise_for_status()
        return _download_best(r.json().get("videos", []), dest, used_ids)
    except Exception:
        return None


def _download_best(videos: list, dest: Path, used_ids: set) -> str | None:
    for v in videos:
        if v["id"] in used_ids:
            continue
        files = sorted(v.get("video_files", []), key=lambda f: abs((f.get("height") or 0) - 1080))
        if not files:
            continue
        with httpx.stream("GET", files[0]["link"], timeout=120, follow_redirects=True) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_bytes(1024 * 256):
                    f.write(chunk)
        used_ids.add(v["id"])
        return str(dest)
    return None


# ---------- Pillow 렌더링 ----------

def _font(path: str, px: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, px)


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        cand = f"{line} {word}".strip()
        if draw.textlength(cand, font=font) <= max_w:
            line = cand
        else:
            if line:
                lines.append(line)
            line = word
    return lines + ([line] if line else [])


def _gradient(size, c1, c2) -> Image.Image:
    w, h = size
    img = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(h - 1, 1)
        img.putpixel((0, y), tuple(int(a + (b - a) * t) for a, b in zip(c1, c2)))
    return img.resize((w, h))


def _make_slide(scene: dict, size, dest: Path, idx: int) -> str:
    """인포그래픽 슬라이드: 제목 + 불릿."""
    w, h = size
    c1, c2 = PALETTE[idx % len(PALETTE)]
    img = _gradient(size, c1, tuple(int(v * 0.4) for v in c2))
    d = ImageDraw.Draw(img)
    scale = w / 1920 if w >= h else w / 1080
    title_f, body_f = _font(FONT_BOLD, int(76 * scale)), _font(FONT_REGULAR, int(52 * scale))
    margin, y = int(w * 0.08), int(h * 0.16)
    d.rectangle([margin, y - int(20 * scale), margin + int(12 * scale), y + int(90 * scale)], fill=c2)
    for line in _wrap(d, scene.get("caption", ""), title_f, w - margin * 2 - int(40 * scale)):
        d.text((margin + int(40 * scale), y), line, font=title_f, fill=(255, 255, 255))
        y += int(100 * scale)
    y += int(50 * scale)
    for b in (scene.get("bullets") or [])[:5]:
        d.ellipse([margin, y + int(20 * scale), margin + int(18 * scale), y + int(38 * scale)], fill=c2)
        for line in _wrap(d, b, body_f, w - margin * 2 - int(50 * scale)):
            d.text((margin + int(50 * scale), y), line, font=body_f, fill=(220, 225, 235))
            y += int(70 * scale)
        y += int(20 * scale)
    img.save(dest)
    return str(dest)


def _make_fallback(scene: dict, size, dest: Path, idx: int) -> str:
    """스톡영상이 없을 때 쓰는 배경 이미지."""
    w, h = size
    c1, c2 = PALETTE[idx % len(PALETTE)]
    img = _gradient(size, c1, tuple(min(255, int(v * 0.6)) for v in c2))
    d = ImageDraw.Draw(img)
    f = _font(FONT_BOLD, int(w * 0.05))
    lines = _wrap(d, scene.get("caption", ""), f, int(w * 0.8))
    y = h // 2 - len(lines) * int(w * 0.035)
    for line in lines:
        d.text((w // 2 - d.textlength(line, font=f) / 2, y), line, font=f, fill=(255, 255, 255))
        y += int(w * 0.065)
    img.save(dest)
    return str(dest)


def _make_overlay(scene: dict, size, style: str, dest: Path, idx: int) -> str | None:
    if style == "infographic":
        return None
    w, h = size
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if style == "news":
        _draw_news_banner(d, scene, w, h)
    else:
        _draw_subtitle(d, scene, w, h)
    img.save(dest)
    return str(dest)


def _draw_subtitle(d, scene: dict, w: int, h: int):
    f = _font(FONT_BOLD, int(w * 0.038))
    lines = _wrap(d, scene.get("caption", ""), f, int(w * 0.85))
    lh = int(w * 0.052)
    y = h - int(h * 0.10) - len(lines) * lh
    for line in lines:
        tw = d.textlength(line, font=f)
        x = (w - tw) / 2
        d.rounded_rectangle([x - 24, y - 8, x + tw + 24, y + lh], radius=14, fill=(0, 0, 0, 170))
        d.text((x, y), line, font=f, fill=(255, 255, 255))
        y += lh + 10


def _draw_news_banner(d, scene: dict, w: int, h: int):
    bar_h = int(h * 0.11)
    top = h - int(h * 0.06) - bar_h
    d.rectangle([0, top, w, top + bar_h], fill=(15, 20, 35, 235))
    tag_f = _font(FONT_BOLD, int(bar_h * 0.34))
    tag_w = int(d.textlength("속보", font=tag_f)) + int(bar_h * 0.5)
    d.rectangle([0, top, tag_w, top + bar_h], fill=(200, 30, 40, 255))
    d.text((int(bar_h * 0.25), top + int(bar_h * 0.28)), "속보", font=tag_f, fill=(255, 255, 255))
    head_f = _font(FONT_BOLD, int(bar_h * 0.36))
    text = scene.get("headline") or scene.get("caption", "")
    lines = _wrap(d, text, head_f, w - tag_w - int(bar_h * 0.8))
    d.text((tag_w + int(bar_h * 0.3), top + int(bar_h * 0.27)), lines[0] if lines else "", font=head_f, fill=(255, 255, 255))
