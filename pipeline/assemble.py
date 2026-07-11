"""장면별 클립 생성 후 하나의 영상으로 조립 (FFmpeg). 화면 전환·효과음 지원."""
from pathlib import Path

from .config import FPS
from .media import probe_duration, run_ffmpeg

ENCODE = ["-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
          "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "44100"]

TRANSITION_SEC = 0.4  # 장면 뒤 무음 패딩(0.4초)과 맞춰 나레이션이 잘리지 않게 함

# 자체 합성 효과음 (저작권 무관)
SFX = {
    "whoosh": "anoisesrc=d=0.5:color=pink:amplitude=0.7,lowpass=f=1400,"
              "afade=t=in:st=0:d=0.15,afade=t=out:st=0.2:d=0.3",
    "ding": "sine=frequency=1318:duration=0.7,afade=t=out:st=0.05:d=0.6",
    "pop": "sine=frequency=300:duration=0.15,afade=t=out:st=0.02:d=0.12",
}


def assemble(scenes: list[dict], size, workdir: Path, log, bgm: str | None = None,
             bgm_volume: float = 0.12, transition: str = "none", sfx: str = "none") -> str:
    t = TRANSITION_SEC if transition != "none" and len(scenes) > 1 else 0.0
    clips, lengths = [], []
    for i, scene in enumerate(scenes):
        out = workdir / f"clip_{i:02d}.mp4"
        lead = t if i > 0 else 0.0
        _build_clip(scene, size, out, lead, exact_audio=bool(t))
        clips.append(out)
        lengths.append(scene["duration"] + lead)
        log(f"장면 {i + 1}/{len(scenes)} 조립 완료")
    if t:
        log(f"화면 전환 적용: {transition}")
        merged, boundaries = _merge_xfade(clips, lengths, workdir, transition, t)
    else:
        merged = _concat(clips, workdir)
        boundaries = [sum(lengths[:k + 1]) for k in range(len(lengths) - 1)]
    final = workdir / "final.mp4"
    sfx_file = _make_sfx(sfx, workdir)
    if sfx_file:
        log(f"전환 효과음 적용: {sfx}")
    _finalize(merged, final, bgm, bgm_volume, sfx_file, boundaries)
    _write_srt(scenes, workdir / "subtitles.srt")
    return str(final)


def _build_clip(scene: dict, size, out: Path, lead: float = 0.0, exact_audio: bool = False):
    w, h = size
    dur = scene["duration"] + lead
    fit = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={FPS}"
    if scene.get("video"):
        src = ["-stream_loop", "-1", "-i", scene["video"]]
        parts = [f"[0:v]{fit}[base]"]
    else:
        src = ["-loop", "1", "-i", scene["image"]]
        zoom = (f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
                f"zoompan=z='min(zoom+0.0006,1.10)'"
                f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int(dur * FPS) + FPS}:s={w}x{h}:fps={FPS}")
        parts = [f"[0:v]{zoom},setsar=1[base]"]
    if scene.get("overlay"):
        extra_in, audio_idx = ["-i", scene["overlay"]], 2
        parts.append("[base][1:v]overlay=0:0[v]")
    else:
        extra_in, audio_idx = [], 1
        parts.append("[base]null[v]")
    achain, amap = _audio_map(audio_idx, lead, exact_audio)
    parts += achain
    run_ffmpeg([*src, *extra_in, "-i", scene["audio"],
                "-filter_complex", ";".join(parts), "-map", "[v]", "-map", amap,
                "-t", f"{dur:.3f}", *ENCODE, str(out)])


def _audio_map(idx: int, lead: float, exact: bool) -> tuple[list[str], str]:
    """리드인 지연 + 무음 패딩이 필요하면 오디오 필터 체인 구성."""
    if not lead and not exact:
        return [], f"{idx}:a"
    delay = int(lead * 1000)
    chain = (f"adelay={delay}|{delay}," if delay else "") + "apad"
    return [f"[{idx}:a]{chain}[aud]"], "[aud]"


def _merge_xfade(clips: list[Path], lengths: list[float], workdir: Path,
                 transition: str, t: float) -> tuple[Path, list[float]]:
    """xfade/acrossfade 체인으로 장면을 겹치며 전환."""
    inputs = []
    for c in clips:
        inputs += ["-i", str(c)]
    fc, boundaries, off = [], [], 0.0
    vlabel, alabel = "0:v", "0:a"
    for k in range(1, len(clips)):
        off += lengths[k - 1] - t
        boundaries.append(off)
        fc.append(f"[{vlabel}][{k}:v]xfade=transition={transition}:duration={t}:offset={off:.3f}[v{k}]")
        fc.append(f"[{alabel}][{k}:a]acrossfade=d={t}[a{k}]")
        vlabel, alabel = f"v{k}", f"a{k}"
    merged = workdir / "merged.mp4"
    run_ffmpeg([*inputs, "-filter_complex", ";".join(fc),
                "-map", f"[{vlabel}]", "-map", f"[{alabel}]", *ENCODE, str(merged)])
    return merged, boundaries


def _make_sfx(kind: str, workdir: Path) -> Path | None:
    if kind not in SFX:
        return None
    path = workdir / f"sfx_{kind}.wav"
    run_ffmpeg(["-f", "lavfi", "-i", SFX[kind], "-ar", "44100", str(path)])
    return path


def _concat(clips: list[Path], workdir: Path) -> Path:
    listfile = workdir / "concat.txt"
    listfile.write_text("\n".join(f"file '{c.name}'" for c in clips), encoding="utf-8")
    merged = workdir / "merged.mp4"
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listfile), "-c", "copy", str(merged)])
    return merged


def _finalize(merged: Path, final: Path, bgm: str | None = None, bgm_volume: float = 0.12,
              sfx: Path | None = None, boundaries: list[float] | None = None):
    total = probe_duration(merged)
    fade = f"fade=t=in:d=0.5,fade=t=out:st={max(total - 0.7, 0):.2f}:d=0.7"
    afade = f"afade=t=out:st={max(total - 0.7, 0):.2f}:d=0.7"
    inputs = ["-i", str(merged)]
    fc, mix, idx = [f"[0:v]{fade}[v]"], ["[0:a]"], 1
    if bgm and bgm_volume > 0:
        inputs += ["-stream_loop", "-1", "-i", bgm]
        fc.append(f"[{idx}:a]volume={bgm_volume:.3f}[b]")
        mix.append("[b]")
        idx += 1
    if sfx and boundaries:
        inputs += ["-i", str(sfx)]
        n = len(boundaries)
        fc.append(f"[{idx}:a]asplit={n}" + "".join(f"[sf{k}]" for k in range(n)))
        for k, bt in enumerate(boundaries):
            ms = int(bt * 1000)
            fc.append(f"[sf{k}]adelay={ms}|{ms},volume=0.6[sd{k}]")
            mix.append(f"[sd{k}]")
    if len(mix) == 1:
        fc.append(f"[0:a]{afade}[a]")
    else:
        fc.append("".join(mix) + f"amix=inputs={len(mix)}:duration=first:normalize=0,{afade}[a]")
    run_ffmpeg([*inputs, "-filter_complex", ";".join(fc),
                "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}", *ENCODE, str(final)])


def _write_srt(scenes: list[dict], dest: Path):
    t, n, rows = 0.0, 0, []
    for s in scenes:
        end = t + s["duration"]
        if s.get("narration", "").strip():
            n += 1
            rows.append(f"{n}\n{_ts(t)} --> {_ts(end)}\n{s['narration']}\n")
        t = end
    dest.write_text("\n".join(rows), encoding="utf-8")


def _ts(sec: float) -> str:
    ms = int(sec * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
