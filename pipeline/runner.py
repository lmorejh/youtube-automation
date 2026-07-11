"""영상 생성 파이프라인 실행: 참고분석 → 대본 → TTS → 비주얼 → 조립 → 썸네일."""
import json
import time
from pathlib import Path

from .assemble import assemble
from .config import OUTPUT_DIR, SIZES
from .reference import analyze_references
from .script_gen import generate_script
from .store import save_job
from .thumbnail import make_thumbnail
from .tts import synthesize_scenes
from .visuals import prepare_visuals


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
                    lambda m: _log(job, m), p.get("assets", []))

    _set(job, "영상 조립 중 (FFmpeg)", 65)
    bgm = p.get("bgm", [])
    if bgm:
        _log(job, f"배경음악 적용: {bgm[0]['name']}")
    job["video"] = assemble(script["scenes"], size, workdir, lambda m: _log(job, m),
                            bgm[0]["path"] if bgm else None)

    _set(job, "썸네일 생성 중", 92)
    job["thumbnail"] = make_thumbnail(job["video"], script.get("thumbnail_text", "")[:12], workdir)


def _set(job: dict, stage: str, progress: int):
    job["stage"] = stage
    job["progress"] = progress
    _log(job, stage)
    save_job(job)


def _log(job: dict, msg: str):
    job["log"].append(f"[{time.strftime('%H:%M:%S')}] {msg}")
