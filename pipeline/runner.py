"""영상 생성 파이프라인 실행: 참고분석 → 대본 → TTS → 비주얼 → 조립 → 썸네일."""
import json
import time
from pathlib import Path

from .assemble import assemble
from .config import OUTPUT_DIR, SIZES
from .intro_outro import build_intro, build_outro
from .reference import analyze_references
from .script_gen import generate_script
from .store import save_job
from .thumbnail import make_thumbnail
from .tts import synthesize_scenes
from .visuals import prepare_visuals, refresh_captions


def run_job(job: dict):
    try:
        _run(job)
        job["status"] = "done"
        _set(job, "완료", 100)
    except Exception as e:
        job["status"] = "error"
        job["error"] = f"{type(e).__name__}: {e}"
        _log(job, f"오류 발생: {job['error']}")
    save_job(job)


def _run(job: dict):
    p = job["params"]
    workdir = OUTPUT_DIR / job["id"]
    workdir.mkdir(parents=True, exist_ok=True)
    size = SIZES[p["format"]]

    _set(job, "참고 영상 분석 중", 5)
    refs = analyze_references(p.get("reference_urls", []))
    for r in refs:
        _log(job, f"참고 분석: {r.get('title') or r.get('error', '')}")

    _set(job, "대본 생성 중 (Claude)", 15)
    script = generate_script(p["topic"], p["format"], p["style"], refs, p.get("extra", ""),
                             p.get("source_text", ""), len(p.get("assets", [])))
    job["script"] = script
    (workdir / "script.json").write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(job, f"대본 완성: {script['title']} (장면 {len(script['scenes'])}개)")

    _set(job, "나레이션 생성 중 (TTS)", 30)
    synthesize_scenes(script["scenes"], p["voice"], workdir)
    total = sum(s["duration"] for s in script["scenes"])
    _log(job, f"나레이션 완료: 총 {total:.0f}초")

    _set(job, "비주얼 수집/생성 중", 45)
    prepare_visuals(script["scenes"], p["format"], p["style"], size, workdir,
                    lambda m: _log(job, m), p.get("assets", []), p.get("caption"))

    _set(job, "영상 조립 중 (FFmpeg)", 65)
    bgm_path, bgm_vol = bgm_settings(p)
    if bgm_path:
        _log(job, f"배경음악 적용: {Path(bgm_path).name} (볼륨 {int(bgm_vol * 100)}%)")
    job["video"] = assemble(_full_scenes(job, size, workdir), size, workdir,
                            lambda m: _log(job, m), bgm_path, bgm_vol,
                            p.get("transition", "none"), p.get("sfx", "none"),
                            watermark_settings(job, workdir))

    _set(job, "썸네일 생성 중", 92)
    job["thumbnail"] = make_job_thumbnail(job, workdir)


def rerender_job(job: dict, caption: dict, voice: str | None = None):
    """대본은 그대로 두고 자막·BGM·음성 옵션만 바꿔 영상을 다시 조립."""
    try:
        job["params"]["caption"] = caption
        job["upload_status"] = None
        job["youtube_url"] = None
        _rerender(job, caption, voice)
        job["status"] = "done"
        _set(job, "재렌더 완료", 100)
    except Exception as e:
        job["status"] = "error"
        job["error"] = f"{type(e).__name__}: {e}"
        _log(job, f"재렌더 오류: {job['error']}")
    save_job(job)


def _rerender(job: dict, caption: dict, voice: str | None = None):
    p = job["params"]
    workdir = OUTPUT_DIR / job["id"]
    size = SIZES[p["format"]]
    scenes = job["script"]["scenes"]

    if voice and voice != p.get("voice"):
        p["voice"] = voice
        _set(job, "재렌더: 나레이션 재생성 중 (TTS)", 10)
        synthesize_scenes(scenes, voice, workdir)
        _log(job, f"나레이션 음성 변경 → 총 {sum(s['duration'] for s in scenes):.0f}초")

    _set(job, "재렌더: 자막·슬라이드 재생성 중", 30)
    refresh_captions(scenes, p["style"], size, workdir, caption)

    _set(job, "재렌더: 영상 조립 중 (FFmpeg)", 45)
    bgm_path, bgm_vol = bgm_settings(p)
    if bgm_path:
        _log(job, f"배경음악: {Path(bgm_path).name} (볼륨 {int(bgm_vol * 100)}%)")
    job["video"] = assemble(_full_scenes(job, size, workdir), size, workdir,
                            lambda m: _log(job, m), bgm_path, bgm_vol,
                            p.get("transition", "none"), p.get("sfx", "none"),
                            watermark_settings(job, workdir))

    _set(job, "재렌더: 썸네일 생성 중", 92)
    job["thumbnail"] = make_job_thumbnail(job, workdir)


def _full_scenes(job: dict, size, workdir: Path) -> list[dict]:
    """대본 장면 앞뒤에 인트로/아웃트로 장면을 붙인 최종 목록."""
    intro = build_intro(job, size, workdir)
    outro = build_outro(job, size, workdir)
    if intro or outro:
        _log(job, "추가: " + " + ".join(x for x, ok in [("인트로", intro), ("아웃트로", outro)] if ok))
    return ([intro] if intro else []) + list(job["script"]["scenes"]) + ([outro] if outro else [])


def make_job_thumbnail(job: dict, workdir: Path) -> str:
    """작업의 썸네일 설정(params.thumb)을 반영해 썸네일 생성."""
    from .fonts import resolve

    p = job["params"]
    t = p.get("thumb") or {}
    text = t["text"] if "text" in t else job["script"].get("thumbnail_text", "")[:12]
    font = resolve((p.get("caption") or {}).get("font", ""))[1]
    return make_thumbnail(job["video"], text, workdir, font,
                          t.get("color", "#ffdc3c"), t.get("pos", 0.3), t.get("image"))


def watermark_settings(job: dict, workdir: Path) -> dict | None:
    """워터마크 설정 → assemble용 스펙 (이미지 경로/위치/크기 비율/투명도)."""
    from .fonts import resolve
    from .visuals import make_text_watermark

    p = job["params"]
    wm = p.get("watermark") or {}
    kind = wm.get("kind", "none")
    if kind == "logo":
        image = wm.get("image")
        if not image or not Path(image).exists():
            return None
    elif kind == "text":
        text = (p.get("channel") or "").strip()
        if not text:
            return None
        font = resolve((p.get("caption") or {}).get("font", ""))[1]
        image = str(make_text_watermark(text, font, workdir / "wm_text.png"))
    else:
        return None
    fracs = {"small": 0.08, "normal": 0.12, "large": 0.18}
    return {"image": image, "position": wm.get("position", "tr"),
            "frac": fracs.get(wm.get("size", "normal"), 0.12),
            "opacity": max(0.05, min(1.0, float(wm.get("opacity", 0.7))))}


def bgm_settings(p: dict) -> tuple[str | None, float]:
    """선택된 BGM 파일 경로와 볼륨. bgm_use 미지정 시 첫 오디오, ""면 BGM 없음."""
    entries = p.get("bgm", [])
    default = entries[0]["path"] if entries else None
    path = p.get("bgm_use", default) or None
    if path and not Path(path).exists():
        path = None
    volume = max(0.0, min(1.0, float(p.get("bgm_volume", 0.12))))
    return path, volume


def _set(job: dict, stage: str, progress: int):
    job["stage"] = stage
    job["progress"] = progress
    _log(job, stage)
    save_job(job)


def _log(job: dict, msg: str):
    job["log"].append(f"[{time.strftime('%H:%M:%S')}] {msg}")
