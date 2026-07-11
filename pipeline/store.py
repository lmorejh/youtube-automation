"""작업 상태를 output/<id>/job.json에 저장해 서버 재시작 후에도 목록 유지."""
import json
from pathlib import Path

from .config import OUTPUT_DIR


def save_job(job: dict):
    d = OUTPUT_DIR / job["id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=1), encoding="utf-8")


def load_jobs() -> dict[str, dict]:
    jobs = {}
    for f in OUTPUT_DIR.glob("*/job.json"):
        try:
            jobs.update({(job := _load_one(f))["id"]: job})
        except Exception:
            continue
    return dict(sorted(jobs.items(), key=lambda kv: kv[1].get("created", 0)))


def _load_one(f: Path) -> dict:
    job = json.loads(f.read_text(encoding="utf-8"))
    job.setdefault("created", f.stat().st_mtime)
    if job.get("status") == "running":
        job["status"] = "error"
        job["error"] = "서버 재시작으로 작업이 중단되었습니다"
    for key in ("video", "thumbnail"):
        if job.get(key) and not Path(job[key]).exists():
            job[key] = None
    if job["status"] == "done" and not job.get("video"):
        job["status"] = "error"
        job["error"] = "영상 파일이 삭제되었습니다"
    if job.get("upload_status") == "uploading":
        job["upload_status"] = "upload_error"
    return job
