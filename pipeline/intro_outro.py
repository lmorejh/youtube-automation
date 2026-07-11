"""인트로/아웃트로 장면 생성: 템플릿 카드(Pillow) 또는 사용자 업로드 영상."""
from pathlib import Path

from PIL import Image, ImageDraw

from .fonts import resolve
from .media import probe_duration, probe_streams, run_ffmpeg
from .visuals import _font, _gradient, _wrap

DURATIONS = {"intro": 2.5, "outro": 3.5}


def build_intro(job: dict, size, workdir: Path) -> dict | None:
    return _build("intro", job, size, workdir)


def build_outro(job: dict, size, workdir: Path) -> dict | None:
    return _build("outro", job, size, workdir)


def _build(role: str, job: dict, size, workdir: Path) -> dict | None:
    p = job["params"]
    kind = p.get(role, "none")
    if kind == "none":
        return None
    if kind == "custom":
        video = p.get(f"{role}_video")
        return _video_scene(video, workdir, role) if video and Path(video).exists() else None
    dest = workdir / f"{role}_card.png"
    _render_card(role, kind, job, size, dest)
    dur = DURATIONS[role]
    return {"image": str(dest), "audio": str(_silence(dur, workdir, role)),
            "duration": dur, "narration": "", "overlay": None}


def _video_scene(video: str, workdir: Path, role: str) -> dict:
    """업로드 영상: 소리가 있으면 유지, 없으면 무음."""
    dur = round(probe_duration(video), 2)
    if probe_streams(video)["has_audio"]:
        audio = workdir / f"{role}_audio.wav"
        run_ffmpeg(["-i", video, "-vn", "-ar", "44100", str(audio)])
    else:
        audio = _silence(dur, workdir, role)
    return {"video": video, "audio": str(audio), "duration": dur,
            "narration": "", "overlay": None}


def _silence(dur: float, workdir: Path, role: str) -> Path:
    path = workdir / f"{role}_silence.wav"
    run_ffmpeg(["-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={dur:.2f}", str(path)])
    return path


# ---------- 템플릿 카드 렌더링 ----------

def _render_card(role: str, kind: str, job: dict, size, dest: Path):
    p = job["params"]
    channel = (p.get("channel") or "").strip()
    title = job["script"].get("title", "")
    regular, bold = resolve((p.get("caption") or {}).get("font", ""))
    if role == "intro" and kind == "minimal":
        img = _card_minimal(size, channel or title, bold)
    elif role == "intro":
        img = _card_title(size, channel, title, regular, bold)
    elif kind == "thanks":
        img = _card_thanks(size, channel, regular, bold)
    else:
        img = _card_subscribe(size, channel, regular, bold)
    img.save(dest)


def _center(d, text: str, font, w: int, y: float, fill) -> float:
    d.text(((w - d.textlength(text, font=font)) / 2, y), text, font=font, fill=fill)
    return y + font.size * 1.35


def _card_minimal(size, text: str, bold: str) -> Image.Image:
    w, h = size
    img = Image.new("RGB", size, (12, 14, 20))
    d = ImageDraw.Draw(img)
    f = _font(bold, int(w * 0.07))
    lines = _wrap(d, text, f, int(w * 0.82))
    y = h / 2 - len(lines) * f.size * 0.7
    for line in lines:
        y = _center(d, line, f, w, y, (245, 245, 250))
    d.rectangle([w / 2 - int(w * 0.05), y + 18, w / 2 + int(w * 0.05), y + 24], fill=(255, 71, 87))
    return img


def _card_title(size, channel: str, title: str, regular: str, bold: str) -> Image.Image:
    w, h = size
    img = _gradient(size, (24, 28, 46), (52, 24, 60))
    d = ImageDraw.Draw(img)
    y = h * 0.36
    if channel:
        y = _center(d, channel, _font(regular, int(w * 0.032)), w, y, (170, 178, 200)) + h * 0.015
    tf = _font(bold, int(w * 0.058))
    for line in _wrap(d, title, tf, int(w * 0.82)):
        y = _center(d, line, tf, w, y, (255, 255, 255))
    d.rectangle([w / 2 - int(w * 0.06), y + 20, w / 2 + int(w * 0.06), y + 27], fill=(255, 71, 87))
    return img


def _card_thanks(size, channel: str, regular: str, bold: str) -> Image.Image:
    w, h = size
    img = _gradient(size, (30, 22, 40), (12, 10, 18))
    d = ImageDraw.Draw(img)
    y = _center(d, "시청해 주셔서", _font(regular, int(w * 0.04)), w, h * 0.40, (200, 205, 220))
    y = _center(d, "감사합니다", _font(bold, int(w * 0.075)), w, y + h * 0.01, (255, 255, 255))
    if channel:
        _center(d, channel, _font(regular, int(w * 0.03)), w, y + h * 0.04, (150, 158, 180))
    return img


def _card_subscribe(size, channel: str, regular: str, bold: str) -> Image.Image:
    w, h = size
    img = Image.new("RGB", size, (16, 18, 26))
    d = ImageDraw.Draw(img)
    y = _center(d, "시청해 주셔서 감사합니다", _font(bold, int(w * 0.045)), w, h * 0.36, (255, 255, 255))
    y += h * 0.03
    bf = _font(bold, int(w * 0.032))
    pad, gap = int(w * 0.025), int(w * 0.02)
    sub_w = d.textlength("구독", font=bf) + pad * 2
    like_w = d.textlength("좋아요", font=bf) + pad * 2
    total = sub_w + gap + like_w
    x = (w - total) / 2
    btn_h = bf.size + pad * 1.2
    d.rounded_rectangle([x, y, x + sub_w, y + btn_h], radius=int(btn_h / 2), fill=(204, 30, 30))
    d.text((x + pad, y + pad * 0.55), "구독", font=bf, fill=(255, 255, 255))
    x2 = x + sub_w + gap
    d.rounded_rectangle([x2, y, x2 + like_w, y + btn_h], radius=int(btn_h / 2),
                        outline=(220, 224, 235), width=3)
    d.text((x2 + pad, y + pad * 0.55), "좋아요", font=bf, fill=(220, 224, 235))
    if channel:
        _center(d, channel, _font(regular, int(w * 0.028)), w, y + btn_h + h * 0.05, (150, 158, 180))
    return img
