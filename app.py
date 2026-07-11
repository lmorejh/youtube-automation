"""유튜브 영상 자동 제작·배포 시스템 웹 서버."""
import threading
import uuid
from pathlib import Path

import base64
import hmac

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

import time

from pipeline import editor, fonts, runner, store, upload
from pipeline.config import APP_PASSWORD, DEFAULT_VOICE, OUTPUT_DIR

app = FastAPI(title="YouTube 자동화")
BASE = Path(__file__).resolve().parent
JOBS: dict[str, dict] = store.load_jobs()  # 서버 재시작 시 이전 작업 복원


@app.middleware("http")
async def require_password(request, call_next):
    """APP_PASSWORD 설정 시 터널(외부) 경유 요청에만 Basic 인증 요구.

    Cloudflare Tunnel을 거친 요청에는 cf-connecting-ip 헤더가 붙는다.
    로컬(PC에서 직접 localhost 접속)은 인증 없이 사용.
    """
    external = "cf-connecting-ip" in request.headers
    if APP_PASSWORD and external and not _password_ok(request.headers.get("authorization", "")):
        return Response(status_code=401,
                        headers={"WWW-Authenticate": 'Basic realm="youtube-automation"'})
    return await call_next(request)


def _password_ok(header: str) -> bool:
    if not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header[6:]).decode("utf-8")
    except Exception:
        return False
    return hmac.compare_digest(decoded.split(":", 1)[-1], APP_PASSWORD)

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}


class UploadRequest(BaseModel):
    title: str = ""
    description: str = ""
    privacy: str = "private"    # private | unlisted | public


class RerenderRequest(BaseModel):
    font: str = ""
    size: str = "normal"
    color: str = "#ffffff"
    style: str = "box"


class EditorCreate(BaseModel):
    job_id: str | None = None
    fresh: bool = False         # true면 기존 세션 무시하고 새로 시작


class RenderRequest(BaseModel):
    timeline: list[dict]        # [{clip_id, start, end}]


@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")


@app.get("/api/fonts")
def list_fonts():
    return fonts.list_fonts()


@app.post("/api/jobs")
async def create_job(
    topic: str = Form(...), format: str = Form("long"), style: str = Form("realistic"),
    reference_urls: str = Form(""), extra: str = Form(""), voice: str = Form(DEFAULT_VOICE),
    source_text: str = Form(""), files: list[UploadFile] = File(default=[]),
    font: str = Form(""), caption_size: str = Form("normal"),
    caption_color: str = Form("#ffffff"), caption_style: str = Form("box"),
):
    if not topic.strip():
        raise HTTPException(400, "주제를 입력하세요")
    job_id = uuid.uuid4().hex[:12]
    visuals, bgm = await _save_assets(files, job_id)
    params = {"topic": topic, "format": format, "style": style,
              "reference_urls": [u.strip() for u in reference_urls.splitlines() if u.strip()],
              "extra": extra, "voice": voice, "source_text": source_text,
              "assets": visuals, "bgm": bgm,
              "caption": {"font": font, "size": caption_size,
                          "color": caption_color, "style": caption_style}}
    job = {"id": job_id, "created": time.time(), "status": "running", "stage": "대기 중",
           "progress": 0, "log": [], "params": params,
           "script": None, "video": None, "thumbnail": None,
           "upload_status": None, "youtube_url": None, "error": None}
    JOBS[job_id] = job
    threading.Thread(target=runner.run_job, args=(job,), daemon=True).start()
    return {"id": job_id}


async def _save_assets(files: list[UploadFile], job_id: str) -> tuple[list, list]:
    """업로드 소스 저장: 이미지/영상은 장면용, 오디오는 BGM용."""
    visuals, bgm = [], []
    assets_dir = OUTPUT_DIR / job_id / "assets"
    for i, f in enumerate(files):
        ext = Path(f.filename or "").suffix.lower()
        if ext not in IMAGE_EXT | VIDEO_EXT | AUDIO_EXT:
            raise HTTPException(400, f"지원하지 않는 파일 형식: {f.filename}")
        assets_dir.mkdir(parents=True, exist_ok=True)
        dest = assets_dir / f"{i:02d}{ext}"
        dest.write_bytes(await f.read())
        entry = {"path": str(dest), "name": f.filename,
                 "kind": "video" if ext in VIDEO_EXT else "image"}
        (bgm if ext in AUDIO_EXT else visuals).append(entry)
    return visuals, bgm


@app.get("/api/jobs")
def list_jobs():
    return [_public(j) for j in reversed(JOBS.values())]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    return _public(_find(job_id))


@app.get("/api/jobs/{job_id}/video")
def get_video(job_id: str):
    job = _find(job_id)
    if not job["video"]:
        raise HTTPException(404, "영상이 아직 없습니다")
    return FileResponse(job["video"], media_type="video/mp4")


@app.get("/api/jobs/{job_id}/thumbnail")
def get_thumbnail(job_id: str):
    job = _find(job_id)
    if not job["thumbnail"]:
        raise HTTPException(404, "썸네일이 아직 없습니다")
    return FileResponse(job["thumbnail"], media_type="image/jpeg")


@app.post("/api/jobs/{job_id}/upload")
def upload_job(job_id: str, req: UploadRequest):
    """사용자가 확인 버튼을 눌렀을 때만 실제 YouTube 업로드 실행."""
    job = _find(job_id)
    if job["status"] != "done":
        raise HTTPException(400, "영상 생성이 완료된 후 업로드할 수 있습니다")
    if job["upload_status"] == "uploading":
        raise HTTPException(400, "이미 업로드 중입니다")
    meta = {"title": req.title or job["script"]["title"],
            "description": req.description or job["script"]["description"],
            "tags": job["script"].get("tags", []), "privacy": req.privacy}
    job["upload_status"] = "uploading"
    threading.Thread(target=_do_upload, args=(job, meta), daemon=True).start()
    return {"ok": True}


def _do_upload(job: dict, meta: dict):
    try:
        log = lambda m: job["log"].append(m)
        job["youtube_url"] = upload.upload_video(job["video"], job["thumbnail"], meta, log)
        job["upload_status"] = "uploaded"
    except Exception as e:
        job["upload_status"] = "upload_error"
        job["log"].append(f"업로드 실패: {e}")
    store.save_job(job)


@app.post("/api/jobs/{job_id}/rerender")
def rerender_job(job_id: str, req: RerenderRequest):
    """자막 옵션만 바꿔 재렌더 (대본·나레이션 재사용)."""
    job = _find(job_id)
    if job["status"] == "running":
        raise HTTPException(400, "작업이 진행 중입니다")
    if not job.get("script"):
        raise HTTPException(400, "대본이 없어 재렌더할 수 없습니다")
    missing = [s for s in job["script"]["scenes"] if not Path(s.get("audio", "")).exists()]
    if missing:
        raise HTTPException(400, "나레이션 파일이 삭제되어 재렌더할 수 없습니다")
    caption = {"font": req.font, "size": req.size, "color": req.color, "style": req.style}
    job["status"] = "running"
    job["progress"] = 0
    threading.Thread(target=runner.rerender_job, args=(job, caption), daemon=True).start()
    return {"ok": True}


# ---------- 간편 편집기 ----------

@app.get("/edit")
def edit_page():
    return FileResponse(BASE / "static" / "editor.html")


@app.post("/api/editor/sessions")
def create_editor_session(req: EditorCreate):
    job = None
    if req.job_id:
        job = _find(req.job_id)
        if job["status"] != "done":
            raise HTTPException(400, "영상 생성이 완료된 작업만 편집할 수 있습니다")
        if not req.fresh:  # 같은 작업의 기존 편집 세션이 있으면 이어서 편집
            existing = [s for s in editor.SESSIONS.values() if s.get("job_id") == req.job_id]
            if existing:
                return _editor_public(max(existing, key=lambda s: s.get("updated", 0)))
    return _editor_public(editor.create_session(job))


@app.put("/api/editor/sessions/{sid}/timeline")
def save_editor_timeline(sid: str, req: RenderRequest):
    """편집 중 타임라인 자동 저장 (재시작 후 복원용)."""
    s = _esession(sid)
    if any(item.get("clip_id") not in s["clips"] for item in req.timeline):
        raise HTTPException(400, "타임라인에 알 수 없는 클립이 있습니다")
    s["timeline"] = req.timeline
    editor.save_session(s)
    return {"ok": True}


@app.get("/api/editor/sessions")
def list_editor_sessions():
    """편집 세션 목록 (최근 수정순) — 이어서 편집하기용."""
    out = []
    for s in sorted(editor.SESSIONS.values(), key=lambda x: x.get("updated", 0), reverse=True):
        tl = s.get("timeline", [])
        job = JOBS.get(s.get("job_id") or "")
        out.append({"id": s["id"], "job_id": s.get("job_id"),
                    "topic": job["params"]["topic"] if job else None,
                    "updated": s.get("updated", 0), "clip_count": len(s["clips"]),
                    "piece_count": len(tl),
                    "total": round(sum(i.get("end", 0) - i.get("start", 0) for i in tl), 1),
                    "has_result": bool(s.get("result"))})
    return out


@app.get("/api/editor/sessions/{sid}")
def get_editor_session(sid: str):
    return _editor_public(_esession(sid))


@app.post("/api/editor/sessions/{sid}/clips")
async def add_editor_clips(sid: str, files: list[UploadFile] = File(default=[])):
    s = _esession(sid)
    for f in files:
        ext = Path(f.filename or "").suffix.lower()
        if ext not in VIDEO_EXT:
            raise HTTPException(400, f"영상 파일만 추가할 수 있습니다: {f.filename}")
        dest = Path(s["workdir"]) / f"up_{len(s['clips']):03d}{ext}"
        dest.write_bytes(await f.read())
        editor.add_clip(s, str(dest), f.filename or dest.name)
    return _editor_public(s)


@app.get("/api/editor/sessions/{sid}/clips/{cid}/video")
def editor_clip_video(sid: str, cid: str):
    return FileResponse(_eclip(sid, cid)["path"], media_type="video/mp4")


@app.get("/api/editor/sessions/{sid}/clips/{cid}/thumb")
def editor_clip_thumb(sid: str, cid: str):
    return FileResponse(_eclip(sid, cid)["thumb"], media_type="image/jpeg")


@app.post("/api/editor/sessions/{sid}/render")
def render_editor(sid: str, req: RenderRequest):
    s = _esession(sid)
    if s["status"] == "rendering":
        raise HTTPException(400, "이미 렌더링 중입니다")
    if any(item.get("clip_id") not in s["clips"] for item in req.timeline):
        raise HTTPException(400, "타임라인에 알 수 없는 클립이 있습니다")
    threading.Thread(target=editor.render, args=(s, req.timeline), daemon=True).start()
    return {"ok": True}


@app.get("/api/editor/sessions/{sid}/result")
def editor_result(sid: str):
    s = _esession(sid)
    if not s["result"]:
        raise HTTPException(404, "렌더링 결과가 아직 없습니다")
    return FileResponse(s["result"], media_type="video/mp4")


@app.post("/api/editor/sessions/{sid}/apply")
def editor_apply(sid: str):
    """편집 결과를 원본 작업의 영상으로 교체 → 기존 업로드 흐름 사용."""
    s = _esession(sid)
    if not s["result"]:
        raise HTTPException(400, "렌더링을 먼저 완료하세요")
    if not s["job_id"] or s["job_id"] not in JOBS:
        raise HTTPException(400, "연결된 작업이 없습니다 (편집기에서 직접 업로드하세요)")
    job = JOBS[s["job_id"]]
    job["video"] = s["result"]
    job["upload_status"] = None
    job["log"].append("✂️ 편집본으로 영상이 교체되었습니다")
    store.save_job(job)
    return {"ok": True, "job_id": s["job_id"]}


@app.post("/api/editor/sessions/{sid}/upload")
def editor_upload(sid: str, req: UploadRequest):
    """편집 결과를 YouTube로 직접 업로드 (사용자 확인 후 호출됨)."""
    s = _esession(sid)
    if not s["result"]:
        raise HTTPException(400, "렌더링을 먼저 완료하세요")
    if s["upload_status"] == "uploading":
        raise HTTPException(400, "이미 업로드 중입니다")
    meta = {"title": req.title or "편집 영상", "description": req.description,
            "tags": [], "privacy": req.privacy}
    s["upload_status"] = "uploading"
    threading.Thread(target=_do_editor_upload, args=(s, meta), daemon=True).start()
    return {"ok": True}


def _do_editor_upload(s: dict, meta: dict):
    try:
        s["youtube_url"] = upload.upload_video(s["result"], None, meta, lambda m: None)
        s["upload_status"] = "uploaded"
    except Exception as e:
        s["upload_status"] = "upload_error"
        s["error"] = f"업로드 실패: {e}"


def _esession(sid: str) -> dict:
    if sid not in editor.SESSIONS:
        raise HTTPException(404, "편집 세션을 찾을 수 없습니다")
    return editor.SESSIONS[sid]


def _eclip(sid: str, cid: str) -> dict:
    clip = _esession(sid)["clips"].get(cid)
    if not clip:
        raise HTTPException(404, "클립을 찾을 수 없습니다")
    return clip


def _editor_public(s: dict) -> dict:
    return {"id": s["id"], "size": s["size"], "status": s["status"], "progress": s["progress"],
            "error": s["error"], "has_result": bool(s["result"]), "job_id": s["job_id"],
            "upload_status": s["upload_status"], "youtube_url": s["youtube_url"],
            "timeline": s.get("timeline", []),
            "clips": [{"id": c["id"], "name": c["name"], "duration": c["duration"]}
                      for c in s["clips"].values()]}


def _find(job_id: str) -> dict:
    if job_id not in JOBS:
        raise HTTPException(404, "작업을 찾을 수 없습니다")
    return JOBS[job_id]


def _public(job: dict) -> dict:
    return {k: v for k, v in job.items() if k not in ("video", "thumbnail")} | {
        "has_video": bool(job["video"]), "has_thumbnail": bool(job["thumbnail"])}
