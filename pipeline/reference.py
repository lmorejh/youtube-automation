"""참고 영상 URL에서 제목/설명/태그를 추출해 대본 생성 컨텍스트로 사용."""


def analyze_references(urls: list[str]) -> list[dict]:
    infos = []
    for url in urls:
        url = url.strip()
        if not url:
            continue
        try:
            infos.append(_extract(url))
        except Exception as e:
            infos.append({"url": url, "error": str(e)[:200]})
    return infos


def _extract(url: str) -> dict:
    import yt_dlp

    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        "url": url,
        "title": info.get("title", ""),
        "description": (info.get("description") or "")[:600],
        "duration_sec": info.get("duration"),
        "tags": (info.get("tags") or [])[:15],
        "channel": info.get("channel", ""),
    }
