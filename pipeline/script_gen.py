"""Claude API로 영상 대본(JSON) 생성. API 키가 없으면 데모 대본으로 대체."""
import json

from .config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL

STYLE_NAMES = {"realistic": "실사 스톡영상", "infographic": "인포그래픽", "news": "뉴스 클립"}

SCHEMA = """{
  "title": "유튜브 제목 (한국어, 클릭을 부르는 제목)",
  "description": "유튜브 설명란 텍스트 (해시태그 포함)",
  "tags": ["태그1", "태그2"],
  "thumbnail_text": "썸네일에 크게 넣을 문구 (10자 이내)",
  "scenes": [
    {
      "narration": "이 장면에서 읽을 나레이션 (자연스러운 구어체)",
      "caption": "화면에 표시할 자막/핵심 문구 (25자 이내)",
      "headline": "뉴스 스타일일 때 하단 헤드라인 (없으면 caption과 동일)",
      "visual_keywords": "english stock footage search keywords",
      "bullets": ["인포그래픽일 때 표시할 항목 1", "항목 2"]
    }
  ]
}"""


def generate_script(topic: str, fmt: str, style: str, refs: list[dict], extra: str) -> dict:
    if not ANTHROPIC_API_KEY:
        return _demo_script(topic, fmt)
    prompt = _build_prompt(topic, fmt, style, refs, extra)
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=ANTHROPIC_MODEL, max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_json(msg.content[0].text)


def _build_prompt(topic: str, fmt: str, style: str, refs: list[dict], extra: str) -> str:
    length_rule = ("전체 나레이션 45~55초 분량, 장면 6~8개, 장면당 1~2문장. 첫 장면은 강력한 훅."
                   if fmt == "short" else
                   "전체 나레이션 4~6분 분량, 장면 12~18개. 도입 훅 → 본론 → 마무리(구독 유도) 구조.")
    ref_text = json.dumps(refs, ensure_ascii=False, indent=1) if refs else "없음"
    return f"""당신은 조회수가 잘 나오는 한국어 유튜브 대본 작가입니다. 아래 조건으로 대본을 작성하세요.

- 주제: {topic}
- 형식: {"숏폼(세로 9:16)" if fmt == "short" else "롱폼(가로 16:9)"}
- 구성 방식: {STYLE_NAMES.get(style, style)}
- 분량 규칙: {length_rule}
- 참고 영상 정보(말투/구성/소재 참고): {ref_text}
- 추가 요청사항: {extra or "없음"}

규칙:
1. narration은 TTS로 읽히므로 자연스러운 구어체로, 숫자는 한글 발음이 자연스럽게.
2. visual_keywords는 반드시 영어로, 스톡영상 검색에 적합한 2~4단어.
3. 인포그래픽 방식이면 bullets를 충실히, 그 외 방식이면 bullets는 빈 배열.
4. 아래 JSON 스키마로만 응답하세요. JSON 외 다른 텍스트 금지.

{SCHEMA}"""


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text[4:] if text.startswith("json") else text
    start, end = text.find("{"), text.rfind("}")
    script = json.loads(text[start:end + 1])
    if not script.get("scenes"):
        raise ValueError("대본에 장면이 없습니다")
    return script


def _demo_script(topic: str, fmt: str) -> dict:
    n = 4 if fmt == "short" else 6
    scenes = [{
        "narration": f"{topic}에 대한 데모 장면 {i + 1}번입니다. API 키를 설정하면 실제 대본이 생성됩니다.",
        "caption": f"데모 장면 {i + 1}",
        "headline": f"{topic} 핵심 포인트 {i + 1}",
        "visual_keywords": "city skyline aerial",
        "bullets": [f"포인트 {i + 1}-1", f"포인트 {i + 1}-2"],
    } for i in range(n)]
    return {
        "title": f"[데모] {topic}",
        "description": f"{topic} 데모 영상입니다.\n#데모",
        "tags": ["데모", topic[:20]],
        "thumbnail_text": topic[:10],
        "scenes": scenes,
    }
