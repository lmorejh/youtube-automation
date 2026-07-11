"""사용 가능한 한글 폰트 탐색: 시스템 폰트 + fonts/ 폴더의 사용자 폰트."""
from pathlib import Path

from .config import BASE_DIR, FONT_BOLD, FONT_REGULAR

FONTS_DIR = BASE_DIR / "fonts"
_WIN = Path("C:/Windows/Fonts")
_KNOWN = [
    ("malgun", "맑은 고딕", "malgun.ttf", "malgunbd.ttf"),
    ("hancom", "한컴 고딕", "Hancom Gothic Regular.ttf", "Hancom Gothic Bold.ttf"),
    ("notosans", "본고딕 (Noto Sans KR)", "NotoSansKR-VF.ttf", "NotoSansKR-VF.ttf"),
    ("notoserif", "본명조 (Noto Serif KR)", "NotoSerifKR-VF.ttf", "NotoSerifKR-VF.ttf"),
    ("hanbatang", "함초롬바탕", "HANBatang.ttf", "HANBatangB.ttf"),
    ("kopub", "KoPub 바탕", "KoPubWorld Batang Light.ttf", "KoPubWorld Batang Medium.ttf"),
    ("gulim", "굴림", "gulim.ttc", "gulim.ttc"),
    ("batang", "바탕", "batang.ttc", "batang.ttc"),
]


def list_fonts() -> list[dict]:
    fonts = [{"id": fid, "name": name}
             for fid, name, regular, _ in _KNOWN if (_WIN / regular).exists()]
    FONTS_DIR.mkdir(exist_ok=True)
    for f in sorted(list(FONTS_DIR.glob("*.ttf")) + list(FONTS_DIR.glob("*.otf"))):
        fonts.append({"id": f"custom:{f.name}", "name": f"{f.stem} (사용자 폰트)"})
    return fonts


def resolve(font_id: str) -> tuple[str, str]:
    """폰트 id → (일반, 굵게) 파일 경로. 못 찾으면 맑은 고딕."""
    if font_id.startswith("custom:"):
        p = FONTS_DIR / font_id[7:]
        if p.exists():
            return str(p), str(p)
    for fid, _, regular, bold in _KNOWN:
        if fid == font_id and (_WIN / regular).exists():
            bold_path = _WIN / bold if (_WIN / bold).exists() else _WIN / regular
            return str(_WIN / regular), str(bold_path)
    return FONT_REGULAR, FONT_BOLD
