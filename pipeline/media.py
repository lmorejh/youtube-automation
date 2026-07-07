import subprocess

from .config import FFMPEG, FFPROBE


def run_ffmpeg(args: list[str]):
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 실패: {result.stderr[-1500:]}")


def probe_duration(path) -> float:
    cmd = [FFPROBE, "-v", "error", "-show_entries", "format=duration",
           "-of", "csv=p=0", str(path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe 실패: {result.stderr[-500:]}")
    return float(result.stdout.strip())
