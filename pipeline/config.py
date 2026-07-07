import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
load_dotenv(BASE_DIR / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
YOUTUBE_CLIENT_SECRET_FILE = BASE_DIR / os.getenv("YOUTUBE_CLIENT_SECRET_FILE", "client_secret.json")
YOUTUBE_TOKEN_FILE = BASE_DIR / "token.json"
DEFAULT_VOICE = os.getenv("DEFAULT_VOICE", "ko-KR-SunHiNeural")
APP_PASSWORD = os.getenv("APP_PASSWORD", "")  # 설정 시 웹 UI에 비밀번호 인증 적용

FONT_REGULAR = "C:/Windows/Fonts/malgun.ttf"
FONT_BOLD = "C:/Windows/Fonts/malgunbd.ttf"

def _find_tool(name: str) -> str:
    import shutil

    found = shutil.which(name)
    if found:
        return found
    winget = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet"
    for candidate in [winget / "Links" / f"{name}.exe",
                      *sorted(winget.glob(f"Packages/Gyan.FFmpeg*/**/bin/{name}.exe"), reverse=True)]:
        if candidate.exists():
            return str(candidate)
    return name


FFMPEG = os.getenv("FFMPEG_PATH") or _find_tool("ffmpeg")
FFPROBE = os.getenv("FFPROBE_PATH") or _find_tool("ffprobe")

# 형식별 해상도: 롱폼 16:9, 숏폼 9:16
SIZES = {"long": (1920, 1080), "short": (1080, 1920)}
FPS = 30
