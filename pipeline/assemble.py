"""장면별 클립 생성 후 하나의 영상으로 조립 (FFmpeg)."""
from pathlib import Path

from .config import FPS
from .media import probe_duration, run_ffmpeg

ENCODE = ["-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
          "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "44100"]


def assemble(scenes: list[dict], size, workdir: Path, log) -> str:
    clips = []
    for i, scene in enumerate(scenes):
        out = workdir / f"clip_{i:02d}.mp4"
        _build_clip(scene, size, out)
        clips.append(out)
        log(f"장면 {i + 1}/{len(scenes)} 조립 완료")
    merged = _concat(clips, workdir)
    final = workdir / "final.mp4"
    _finalize(merged, final)
    _write_srt(scenes, workdir / "subtitles.srt")
    return str(final)


def _build_clip(scene: dict, size, out: Path):
    w, h = size
    dur = scene["duration"]
    fit = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={FPS}"
    if scene.get("video"):
        src = ["-stream_loop", "-1", "-i", scene["video"]]
        vf = f"[0:v]{fit}[base]"
    else:
        src = ["-loop", "1", "-i", scene["image"]]
        zoom = (f"scale={w * 2}:{h * 2},zoompan=z='min(zoom+0.0006,1.10)'"
                f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int(dur * FPS) + FPS}:s={w}x{h}:fps={FPS}")
        vf = f"[0:v]{zoom},setsar=1[base]"
    if scene.get("overlay"):
        args = [*src, "-i", scene["overlay"], "-i", scene["audio"],
                "-filter_complex", f"{vf};[base][1:v]overlay=0:0[v]",
                "-map", "[v]", "-map", "2:a"]
    else:
        args = [*src, "-i", scene["audio"],
                "-filter_complex", f"{vf};[base]null[v]",
                "-map", "[v]", "-map", "1:a"]
    run_ffmpeg([*args, "-t", f"{dur:.3f}", *ENCODE, str(out)])


def _concat(clips: list[Path], workdir: Path) -> Path:
    listfile = workdir / "concat.txt"
    listfile.write_text("\n".join(f"file '{c.name}'" for c in clips), encoding="utf-8")
    merged = workdir / "merged.mp4"
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listfile), "-c", "copy", str(merged)])
    return merged


def _finalize(merged: Path, final: Path):
    total = probe_duration(merged)
    fade = f"fade=t=in:d=0.5,fade=t=out:st={max(total - 0.7, 0):.2f}:d=0.7"
    afade = f"afade=t=out:st={max(total - 0.7, 0):.2f}:d=0.7"
    run_ffmpeg(["-i", str(merged), "-vf", fade, "-af", afade, *ENCODE, str(final)])


def _write_srt(scenes: list[dict], dest: Path):
    t, rows = 0.0, []
    for i, s in enumerate(scenes, 1):
        end = t + s["duration"]
        rows.append(f"{i}\n{_ts(t)} --> {_ts(end)}\n{s['narration']}\n")
        t = end
    dest.write_text("\n".join(rows), encoding="utf-8")


def _ts(sec: float) -> str:
    ms = int(sec * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
