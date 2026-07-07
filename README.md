# 🎬 유튜브 영상 자동 제작·배포 시스템

주제·형식·구성 방식·참고 URL을 입력하면 **대본 → 나레이션(TTS) → 비주얼 → 영상 조립 → 썸네일**까지 자동 생성하고,
사용자 확인 후 YouTube에 업로드하는 시스템입니다.

## 실행 방법

`run.bat` 더블클릭 → 브라우저에서 http://localhost:8600 자동 열림

## 파이프라인

| 단계 | 사용 기술 | 비고 |
|---|---|---|
| 참고 영상 분석 | yt-dlp | 제목/설명/태그 추출 → 대본 스타일 참고 |
| 소스 자료 | 텍스트 입력 + 파일 업로드 | 텍스트는 대본의 최우선 근거, 이미지/영상은 장면 순서대로 사용, 오디오는 BGM(자동 볼륨 12%) |
| 대본 생성 | Claude API | 키 없으면 데모 대본으로 동작 |
| 나레이션 | edge-tts (무료) | 한국어 남/여 음성 선택 |
| 비주얼 | Pexels API(스톡영상 기반) / Pillow(그래픽 기반) | Pexels 키 없으면 슬라이드로 대체 |
| 영상 조립 | FFmpeg | 롱폼 1920×1080 / 숏폼 1080×1920, 자막 번인, SRT 별도 생성 |
| 썸네일 | Pillow | 영상 프레임 + 제목 문구 |
| 업로드 | YouTube Data API v3 | **버튼 클릭 + 확인 후에만 실행**, 기본 비공개 |

## 구성 방식 (8종)

**스톡영상 기반** (Pexels 영상 + 오버레이):
| 방식 | 화면 구성 |
|---|---|
| 실사 | 스톡영상 + 하단 자막 |
| 다큐/스토리텔링 | 시네마틱 레터박스(상하 블랙바) + 중앙 자막, 서정적 나레이션 |
| 뉴스 클립 | 하단 헤드라인 자막바("속보" 태그), 보도체 나레이션 |
| 랭킹 Top N | 좌상단 "TOP 3" 뱃지, 카운트다운 구성(마지막이 1위) |
| 튜토리얼 | 좌상단 "STEP 1" 뱃지, 단계별 하우투 구성 |

**그래픽 기반** (Pillow 자동 생성 슬라이드, Pexels 불필요):
| 방식 | 화면 구성 |
|---|---|
| 인포그래픽 | 제목 + 불릿 요약 슬라이드 |
| 카드뉴스 | 밝은 배경 + 중앙 대형 문구 카드 |
| 명언/감성 | 어두운 배경 + 큰따옴표 + 중앙 문구 |

## API 키 설정 (.env)

`.env.example`을 복사해 `.env` 생성 후 키 입력:

```
copy .env.example .env
```

### 1. Anthropic (대본 생성 — 필수에 가까움)
- https://console.anthropic.com → API Keys 발급 → `ANTHROPIC_API_KEY=`
- 없으면 데모 대본으로 파이프라인 테스트만 가능

### 2. Pexels (실사/뉴스 스톡영상 — 무료)
- https://www.pexels.com/api/ 가입 → 키 발급 → `PEXELS_API_KEY=`
- 없으면 그라디언트 슬라이드 배경으로 대체됨

### 3. YouTube 업로드 (OAuth)
1. https://console.cloud.google.com → 프로젝트 생성
2. "API 및 서비스" → **YouTube Data API v3** 사용 설정
3. "OAuth 동의 화면" → 외부 → 본인 계정을 **테스트 사용자**로 추가
4. "사용자 인증 정보" → OAuth 클라이언트 ID → **데스크톱 앱** → JSON 다운로드
5. 다운로드한 파일을 프로젝트 폴더에 `client_secret.json`으로 저장
6. 첫 업로드 시 브라우저 인증 1회 → 이후 `token.json` 자동 재사용

> 참고: 신규 OAuth 앱(테스트 모드)으로 업로드한 영상은 심사 전까지 **비공개로 잠길 수 있습니다.**
> 썸네일 설정은 채널 전화번호 인증이 되어 있어야 합니다.
> API 기본 할당량으로 하루 약 6개까지 업로드 가능합니다(영상 1개 = 1600 유닛 / 10000 유닛).

## 결과물 위치

`output/<작업ID>/` — `final.mp4`, `thumbnail.jpg`, `script.json`, `subtitles.srt`

## 구조

```
app.py               # FastAPI 서버 + API
static/index.html    # 웹 UI
pipeline/
  runner.py          # 파이프라인 오케스트레이션
  reference.py       # 참고 영상 분석 (yt-dlp)
  script_gen.py      # 대본 생성 (Claude)
  tts.py             # 나레이션 (edge-tts)
  visuals.py         # 스톡영상/슬라이드/자막 오버레이
  assemble.py        # FFmpeg 조립
  thumbnail.py       # 썸네일
  upload.py          # YouTube 업로드
```
