"""YouTube Data API 업로드. 최초 1회 브라우저 OAuth 인증 후 token.json 재사용."""
from .config import YOUTUBE_CLIENT_SECRET_FILE, YOUTUBE_TOKEN_FILE

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def upload_video(video: str, thumbnail: str, meta: dict, log) -> str:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    yt = build("youtube", "v3", credentials=_credentials())
    body = {
        "snippet": {
            "title": meta["title"][:100],
            "description": meta["description"][:4900],
            "tags": meta.get("tags", [])[:30],
            "categoryId": "22",
        },
        "status": {"privacyStatus": meta.get("privacy", "private"),
                   "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(video, chunksize=8 * 1024 * 1024, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = req.next_chunk()
        if status:
            log(f"업로드 진행률 {int(status.progress() * 100)}%")
    video_id = response["id"]
    _set_thumbnail(yt, video_id, thumbnail, log)
    return f"https://www.youtube.com/watch?v={video_id}"


def _set_thumbnail(yt, video_id: str, thumbnail: str, log):
    try:
        yt.thumbnails().set(videoId=video_id, media_body=thumbnail).execute()
    except Exception as e:
        log(f"썸네일 설정 실패(채널 전화번호 인증 필요할 수 있음): {str(e)[:200]}")


def _credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if YOUTUBE_TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(YOUTUBE_TOKEN_FILE), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        if not YOUTUBE_CLIENT_SECRET_FILE.exists():
            raise RuntimeError("client_secret.json이 없습니다. README의 YouTube API 설정을 먼저 진행하세요.")
        flow = InstalledAppFlow.from_client_secrets_file(str(YOUTUBE_CLIENT_SECRET_FILE), SCOPES)
        creds = flow.run_local_server(port=0)
    YOUTUBE_TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    return creds
