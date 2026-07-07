"""유튜브 영상 자동 제작·배포 시스템 웹 서버."""
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from pipeline import runner, upload
from pipeline.config import DEFAULT_VOICE

app = FastAPI(title="YouTube 자동화")
BASE = Path(__file__).resolve().parent
JOBS: dict[str, dict] = {}


class JobRequest(BaseModel):
    topic: str
    format: str = "long"        # long | short
    style: str = "realistic"    # realistic | infographic | news
    reference_urls: list[str] = []
    extra: str = ""
    voice: str = DEFAULT_VOICE


class UploadRequest(BaseModel):
    title: str = ""
    description: str = ""
    privacy: str = "private"    # private | unlisted | public


@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")


@app.post("/api/jobs")
def create_job(req: JobRequest):
    if not req.topic.strip():
        raise HTTPException(400, "주제를 입력하세요")
    job = {"id": uuid.uuid4().hex[:12], "status": "running", "stage": "대기 중",
           "progress": 0, "log": [], "params": req.model_dump(),
           "script": None, "video": None, "thumbnail": None,
           "upload_status": None, "youtube_url": None, "error": None}
    JOBS[job["id"]] = job
    threading.Thread(target=runner.run_job, args=(job,), daemon=True).start()
    return {"id": job["id"]}


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
