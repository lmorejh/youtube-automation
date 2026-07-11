"""클립 기반 간편 편집: 트림(자르기)·분할·순서변경·이어붙이기 후 재렌더링."""
import json
import time
import uuid
from pathlib import Path

from .assemble import ENCODE, _concat, _finalize
from .config import FPS, OUTPUT_DIR, SIZES
from .media import probe_duration, probe_streams, run_ffmpeg


def save_session(session: dict):
    session["updated"] = time.time()
    path = Path(session["workdir"]) / "session.json"
    path.write_text(json.dumps(session, ensure_ascii=False, indent=1), encoding="utf-8")


def load_sessions() -> dict[str, dict]:
    sessions = {}
    for f in OUTPUT_DIR.glob("edit_*/session.json"):
        try:
            s = _load_one(f)
            if s["clips"]:
                sessions[s["id"]] = s
        except Exception:
            continue
    return sessions


def _load_one(f: Path) -> dict:
    s = json.loads(f.read_text(encoding="utf-8"))
    s["clips"] = {cid: c for cid, c in s["clips"].items() if Path(c["path"]).exists()}
    s["timeline"] = [it for it in s.get("timeline", []) if it.get("clip_id") in s["clips"]]
    if s.get("status") == "rendering":  # 재시작으로 중단된 렌더링
        s["status"] = "idle"
        s["progress"] = 0
    if s.get("result") and not Path(s["result"]).exists():
        s["result"] = None
    if s.get("upload_status") == "uploading":
        s["upload_status"] = "upload_error"
    return s


SESSIONS: dict[str, dict] = load_sessions()


def create_session(job: dict | None) -> dict:
    sid = uuid.uuid4().hex[:10]
    workdir = OUTPUT_DIR / f"edit_{sid}"
    workdir.mkdir(parents=True, exist_ok=True)
    session = {"id": sid, "workdir": str(workdir), "clips": {}, "size": None,
               "bgm": None, "job_id": None, "timeline": [], "updated": time.time(),
               "status": "idle", "progress": 0,
               "error": None, "result": None, "upload_status": None, "youtube_url": None}
    if job:
        _load_job_clips(session, job)
    SESSIONS[sid] = session
    save_session(session)
    return session


def _load_job_clips(session: dict, job: dict):
    from .runner import bgm_settings

    session["job_id"] = job["id"]
    session["size"] = list(SIZES[job["params"]["format"]])
    session["bgm"], session["bgm_volume"] = bgm_settings(job["params"])
    job_dir = Path(job["video"]).parent
    p = job["params"]
    names = (["인트로"] if p.get("intro", "none") != "none" else [])
    names += [s.get("caption") or f"장면 {i + 1}" for i, s in enumerate(job["script"]["scenes"])]
    names += (["아웃트로"] if p.get("outro", "none") != "none" else [])
    for i, name in enumerate(names):
        clip = job_dir / f"clip_{i:02d}.mp4"
        if clip.exists():
            add_clip(session, str(clip), name)


def add_clip(session: dict, path: str, name: str) -> dict:
    cid = f"c{len(session['clips']):03d}"
    info = probe_streams(path)
    if session["size"] is None:
        session["size"] = [1080, 1920] if info["height"] > info["width"] else [1920, 1080]
    dur = probe_duration(path)
    thumb = Path(session["workdir"]) / f"{cid}.jpg"
    run_ffmpeg(["-ss", f"{min(0.5, dur / 2):.2f}", "-i", path,
                "-frames:v", "1", "-vf", "scale=320:-2", str(thumb)])
    clip = {"id": cid, "path": path, "name": name, "duration": round(dur, 2),
            "thumb": str(thumb), "has_audio": info["has_audio"]}
    session["clips"][cid] = clip
    save_session(session)
    return clip


def render(session: dict, timeline: list[dict]):
    """timeline: [{clip_id, start, end}] 순서대로 잘라 이어붙여 final.mp4 생성."""
    session.update(status="rendering", progress=0, error=None, result=None, timeline=timeline)
    try:
        parts = _render_parts(session, timeline)
        if not parts:
            raise ValueError("렌더링할 구간이 없습니다 (구간 길이 0.1초 이상 필요)")
        workdir = Path(session["workdir"])
        merged = _concat(parts, workdir)
        final = workdir / "final.mp4"
        _finalize(merged, final, session["bgm"], session.get("bgm_volume", 0.12))
        session.update(result=str(final), status="done", progress=100)
    except Exception as e:
        session.update(status="error", error=f"{type(e).__name__}: {e}")
    save_session(session)


def _render_parts(session: dict, timeline: list[dict]) -> list[Path]:
    w, h = session["size"]
    fit = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={FPS}"
    parts = []
    for i, item in enumerate(timeline):
        clip = session["clips"][item["clip_id"]]
        start = max(0.0, float(item.get("start", 0)))
        end = min(clip["duration"], float(item.get("end", clip["duration"])))
        if end - start < 0.1:
            continue
        out = Path(session["workdir"]) / f"part_{i:03d}.mp4"
        run_ffmpeg([*_part_inputs(clip, start, end), "-vf", fit, *ENCODE,
                    "-t", f"{end - start:.3f}", str(out)])
        parts.append(out)
        session["progress"] = int((i + 1) / len(timeline) * 80)
    return parts


def _part_inputs(clip: dict, start: float, end: float) -> list[str]:
    src = ["-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", clip["path"]]
    if clip["has_audio"]:
        return src
    # 무음 클립에는 빈 오디오 트랙을 붙여 concat 호환 유지
    return [*src, "-f", "lavfi", "-t", f"{end - start:.3f}",
            "-i", "anullsrc=r=44100:cl=stereo", "-map", "0:v", "-map", "1:a"]
