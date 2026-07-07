"""파이프라인 데모 테스트 (API 키 없이 실행 가능)."""
import sys

from pipeline import runner

fmt = sys.argv[1] if len(sys.argv) > 1 else "short"
style = sys.argv[2] if len(sys.argv) > 2 else "infographic"

job = {"id": f"test_{fmt}_{style}", "status": "running", "stage": "", "progress": 0,
       "log": [], "script": None, "video": None, "thumbnail": None, "error": None,
       "params": {"topic": "아침 루틴으로 하루를 바꾸는 방법", "format": fmt, "style": style,
                  "voice": "ko-KR-SunHiNeural", "extra": "", "reference_urls": []}}
runner.run_job(job)
print("\n".join(job["log"]))
print("STATUS:", job["status"], "| VIDEO:", job["video"])
if job["status"] == "error":
    sys.exit(1)
