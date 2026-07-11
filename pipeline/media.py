import subprocess

from .config import FFMPEG, FFPROBE


def run_ffmpeg(args: list[str]):
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 실패: {result.stderr[-1500:]}")


def probe_streams(path) -> dict:
    """영상의 해상도와 오디오 트랙 유무."""
    import json

    cmd = [FFPROBE, "-v", "error", "-show_entries", "stream=codec_type,width,height",
           "-of", "json", str(path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe 실패: {result.stderr[-500:]}")
    streams = json.loads(result.stdout).get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    return {"width": video.get("width", 0), "height": video.get("height", 0),
            "has_audio": any(s.get("codec_type") == "audio" for s in streams)}


def probe_duration(path) -> float:
    cmd = [FFPROBE, "-v", "error", "-show_entries", "format=duration",
           "-of", "csv=p=0", str(path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe 실패: {result.stderr[-500:]}")
    return float(result.stdout.strip())
