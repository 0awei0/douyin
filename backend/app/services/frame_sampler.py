"""Deterministic frame sampling for review and spatial audits."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Iterable


def choose_frame_times(
    duration: float,
    shot_ranges: Iterable[tuple[float, float]] | None = None,
    base_interval: float | None = None,
    max_frames: int = 48,
) -> list[float]:
    """Choose timestamp samples that preserve time coverage and shot boundaries.

    This does not try to replace video understanding. It provides deterministic
    evidence for second-pass spatial checks, where missing a tiny/far subject is
    the most expensive failure.
    """
    if duration <= 0:
        return []

    if base_interval is None:
        if duration <= 25:
            base_interval = 1.0
        elif duration <= 70:
            base_interval = 2.0
        else:
            base_interval = max(3.0, duration / 30.0)

    times: set[float] = {0.0, max(0.0, duration - 0.2)}

    t = 0.0
    while t <= duration:
        times.add(t)
        t += base_interval

    for start, end in shot_ranges or []:
        start = _clamp(float(start), 0.0, duration)
        end = _clamp(float(end), 0.0, duration)
        if end < start:
            start, end = end, start
        mid = start + (end - start) / 2.0
        for ts in (start, mid, max(start, end - 0.2)):
            times.add(_clamp(ts, 0.0, duration))

    ordered = sorted(round(ts, 2) for ts in times if 0 <= ts <= duration)
    if len(ordered) <= max_frames:
        return ordered

    # Keep endpoints, then downsample evenly. Uniform coverage is more important
    # than scene cuts for near-to-far spatial trajectories.
    keep = {ordered[0], ordered[-1]}
    stride = (len(ordered) - 1) / max(max_frames - 1, 1)
    for i in range(max_frames):
        keep.add(ordered[round(i * stride)])
    return sorted(keep)


def extract_frames(
    video_path: str,
    output_dir: Path,
    times: list[float],
    width: int = 360,
) -> list[dict]:
    """Extract selected frames and return timestamp/path metadata."""
    output_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for index, ts in enumerate(times, start=1):
        filename = f"{index:03d}_{_label_time(ts)}s.jpg"
        output_path = output_dir / filename
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-ss", f"{ts:.3f}", "-i", video_path,
                "-frames:v", "1",
                "-vf", f"scale={width}:-1",
                "-q:v", "2",
                str(output_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if output_path.exists():
            frames.append({"index": index, "time": round(ts, 2), "path": str(output_path)})
    return frames


def write_frame_manifest(frames: list[dict], output_path: Path) -> None:
    output_path.write_text(json.dumps(frames, ensure_ascii=False, indent=2), encoding="utf-8")


def _label_time(ts: float) -> str:
    return f"{ts:.2f}".rstrip("0").rstrip(".").replace(".", "_")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
