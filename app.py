"""유튜브 영상 자동 제작·배포 시스템 웹 서버."""
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from pipeline import runner, upload
from pipeline.config import DEFAULT_VOICE, OUTPUT_DIR

app = FastAPI(title="YouTube 자동화")
BASE = Path(__file__).resolve().parent
JOBS: dict[str, dict] = {}

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}


class UploadRequest(BaseModel):
    title: str = ""
    description: str = ""
    privacy: str = "private"    # private | unlisted | public


@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")


@app.post("/api/jobs")
async def create_job(
    topic: str = Form(...), format: str = Form("long"), style: str = Form("realistic"),
    reference_urls: str = Form(""), extra: str = Form(""), voice: str = Form(DEFAULT_VOICE),
    source_text: str = Form(""), files: list[UploadFile] = File(default=[]),
):
    if not topic.strip():
        raise HTTPException(400, "주제를 입력하세요")
    job_id = uuid.uuid4().hex[:12]
    visuals, bgm = await _save_assets(files, job_id)
    params = {"topic": topic, "format": format, "style": style,
              "reference_urls": [u.strip() for u in reference_urls.splitlines() if u.strip()],
              "extra": extra, "voice": voice, "source_text": source_text,
              "assets": visuals, "bgm": bgm}
    job = {"id": job_id, "status": "running", "stage": "대기 중",
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


def _find(job_id: str) -> dict:
    if job_id not in JOBS:
        raise HTTPException(404, "작업을 찾을 수 없습니다")
    return JOBS[job_id]


def _public(job: dict) -> dict:
    return {k: v for k, v in job.items() if k not in ("video", "thumbnail")} | {
        "has_video": bool(job["video"]), "has_thumbnail": bool(job["thumbnail"])}
