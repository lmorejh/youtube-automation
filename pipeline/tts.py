"""edge-tts로 장면별 나레이션 mp3 생성 후 길이를 측정."""
import asyncio
from pathlib import Path

from .media import probe_duration

MIN_SCENE_SEC = 2.5


def synthesize_scenes(scenes: list[dict], voice: str, workdir: Path) -> None:
    for i, scene in enumerate(scenes):
        path = workdir / f"scene_{i:02d}.mp3"
        asyncio.run(_synth(scene["narration"], voice, path))
        scene["audio"] = str(path)
        scene["duration"] = max(probe_duration(path) + 0.4, MIN_SCENE_SEC)


async def _synth(text: str, voice: str, path: Path):
    import edge_tts

    await edge_tts.Communicate(text, voice).save(str(path))
