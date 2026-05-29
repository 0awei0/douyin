"""Persist video-analysis evidence for review and debugging."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from ..models.video_structure import VideoStructure

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def save_analysis_artifacts(
    task_id: str,
    video_path: str,
    structure: VideoStructure,
    raw_result: dict,
    sample_fps: float,
) -> Path:
    """Save frames, contact sheet, raw result and normalized structure."""
    out_dir = BASE_DIR / "outputs" / "analysis_runs" / task_id
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    _extract_review_frames(video_path, frames_dir, structure.meta.duration)
    _make_contact_sheet(frames_dir, out_dir / "contact_sheet.jpg")

    (out_dir / "meta.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "video_path": video_path,
                "duration": structure.meta.duration,
                "resolution": structure.meta.resolution,
                "fps": structure.meta.fps,
                "analysis_sample_fps": sample_fps,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (out_dir / "raw_doubao_result.json").write_text(
        json.dumps(raw_result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "normalized_structure.json").write_text(
        structure.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (out_dir / "spatial_summary.md").write_text(
        _spatial_summary(structure),
        encoding="utf-8",
    )
    return out_dir


def _extract_review_frames(video_path: str, frames_dir: Path, duration: float) -> None:
    if duration <= 20:
        times = [float(i) for i in range(0, int(duration) + 1)]
    else:
        step = 2.0 if duration <= 70 else max(3.0, duration / 30)
        times = []
        t = 0.0
        while t <= duration:
            times.append(round(t, 2))
            t += step

    for ts in times:
        label = str(ts).replace(".", "_")
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-ss", str(ts), "-i", video_path,
                "-frames:v", "1",
                "-vf", "scale=360:-1",
                "-q:v", "2",
                str(frames_dir / f"{label}s.jpg"),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


def _make_contact_sheet(frames_dir: Path, output_path: Path) -> None:
    frames = sorted(frames_dir.glob("*.jpg"), key=_frame_time)
    if not frames:
        return

    images = []
    for frame in frames:
        image = Image.open(frame).convert("RGB")
        draw = ImageDraw.Draw(image)
        label = frame.stem.replace("_", ".")
        draw.rectangle([0, 0, 84, 28], fill=(0, 0, 0))
        draw.text((7, 6), label, fill=(255, 255, 255))
        images.append(image)

    w, h = images[0].size
    cols = 5 if len(images) <= 20 else 7
    rows = (len(images) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * h), (24, 24, 24))
    for i, image in enumerate(images):
        sheet.paste(image, ((i % cols) * w, (i // cols) * h))
    sheet.save(output_path, quality=92)


def _frame_time(path: Path) -> float:
    try:
        return float(path.stem[:-1].replace("_", "."))
    except ValueError:
        return 0.0


def _spatial_summary(structure: VideoStructure) -> str:
    lines = ["# Spatial Summary", ""]
    tf = structure.transferable_features
    lines.append(f"- spatial_pattern: {tf.spatial_pattern}")
    lines.append(f"- subject_trajectory: {tf.subject_trajectory}")
    lines.append(f"- composition_pattern: {tf.composition_pattern}")
    lines.append("")
    lines.append("## Shots")
    for shot in structure.shots:
        lines.append(
            f"- {shot.start_time:.1f}-{shot.end_time:.1f}s "
            f"[{shot.type}] distance={shot.subject_distance or '-'}, "
            f"position={shot.subject_position or '-'}, motion={shot.subject_motion or '-'}"
        )
        lines.append(f"  {shot.content}")
    return "\n".join(lines) + "\n"
