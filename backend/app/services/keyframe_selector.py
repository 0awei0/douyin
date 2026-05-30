"""Algorithmic keyframe candidates for spatial video audits.

The model-facing video input is sampled internally, so this module provides a
cheap local pass that chooses the still frames we most want the model to see:
shot boundaries, motion peaks, and visually diverse moments.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageStat


@dataclass
class ProbeFrame:
    time: float
    path: Path
    hist: list[float]
    ahash: int
    luminance: float
    edge_mean: float
    diff_prev: float = 0.0
    motion_area: float = 0.0
    person_area: float = 0.0
    score: float = 0.0
    reasons: list[str] | None = None


def choose_hybrid_frame_times(
    video_path: str,
    duration: float,
    shot_ranges: Iterable[tuple[float, float]] | None = None,
    max_frames: int = 48,
    debug_dir: Path | None = None,
) -> list[float]:
    """Choose frame times using deterministic coverage plus visual signals."""
    if duration <= 0:
        return []

    shot_ranges = list(shot_ranges or [])
    fallback = _coverage_times(duration, shot_ranges, max_frames)
    if max_frames <= 0:
        return []

    with tempfile.TemporaryDirectory(prefix="keyframes_") as temp_name:
        temp_dir = Path(temp_name)
        interval = _probe_interval(duration, max_frames)
        probe_frames = _extract_probe_frames(video_path, temp_dir, duration, interval)
        if not probe_frames:
            _write_debug(debug_dir, duration, interval, fallback, [], "probe extraction failed")
            return fallback

        _score_probe_frames(probe_frames)
        selected = _select_times(duration, shot_ranges, probe_frames, max_frames)
        _write_debug(debug_dir, duration, interval, selected, probe_frames, "")
        return selected


def _probe_interval(duration: float, max_frames: int) -> float:
    target_samples = max(max_frames * 4, 72)
    target_samples = min(target_samples, 160)
    return round(max(0.5, duration / target_samples), 2)


def _extract_probe_frames(
    video_path: str,
    temp_dir: Path,
    duration: float,
    interval: float,
) -> list[ProbeFrame]:
    cv_frames = _extract_probe_frames_cv(video_path, temp_dir, duration, interval)
    if cv_frames:
        return cv_frames

    temp_dir.mkdir(parents=True, exist_ok=True)
    pattern = temp_dir / "%05d.jpg"
    fps = 1.0 / max(interval, 0.1)
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            video_path,
            "-vf",
            f"fps={fps:.6f},scale=128:-1",
            "-q:v",
            "4",
            str(pattern),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )

    frames: list[ProbeFrame] = []
    for index, path in enumerate(sorted(temp_dir.glob("*.jpg"))):
        ts = min(round(index * interval, 2), max(duration - 0.05, 0.0))
        try:
            frames.append(_probe_frame(path, ts))
        except OSError:
            continue
    return frames


def _extract_probe_frames_cv(
    video_path: str,
    temp_dir: Path,
    duration: float,
    interval: float,
) -> list[ProbeFrame]:
    """Extract probe frames with OpenCV when the cv environment is available."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []

    temp_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    hog = cv2.HOGDescriptor()
    hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    frames: list[ProbeFrame] = []
    prev_gray = None
    sample_index = 0
    ts = 0.0
    while ts <= duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, ts * 1000.0)
        ok, frame = cap.read()
        if not ok:
            break

        height, width = frame.shape[:2]
        target_width = 240
        scale = target_width / max(width, 1)
        resized = cv2.resize(frame, (target_width, max(1, int(height * scale))))
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [8, 4], [0, 180, 0, 256]).flatten()
        hist = (hist / max(float(hist.sum()), 1.0)).astype(float).tolist()
        ahash = _average_hash_cv(gray)
        luminance = float(gray.mean() / 255.0)
        edge_mean = float((cv2.Canny(gray, 80, 160) > 0).mean())

        diff_prev = 0.0
        motion_area = 0.0
        if prev_gray is not None:
            delta = cv2.absdiff(gray, prev_gray)
            diff_prev = float(delta.mean() / 255.0)
            _, mask = cv2.threshold(delta, 18, 255, cv2.THRESH_BINARY)
            kernel = np.ones((3, 3), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            motion_area = float((mask > 0).mean())
        prev_gray = gray

        person_area = _person_area_ratio(hog, resized)

        sample_index += 1
        path = temp_dir / f"{sample_index:05d}.jpg"
        cv2.imwrite(str(path), resized, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
        frames.append(
            ProbeFrame(
                time=round(ts, 2),
                path=path,
                hist=hist,
                ahash=ahash,
                luminance=luminance,
                edge_mean=edge_mean,
                diff_prev=diff_prev,
                motion_area=motion_area,
                person_area=person_area,
                reasons=["opencv_probe"],
            )
        )
        ts += interval

    cap.release()
    return frames


def _average_hash_cv(gray) -> int:
    import cv2

    small = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA)
    avg = float(small.mean())
    bits = 0
    for i, pixel in enumerate(small.flatten()):
        if float(pixel) >= avg:
            bits |= 1 << i
    return bits


def _person_area_ratio(hog, image) -> float:
    try:
        rects, weights = hog.detectMultiScale(
            image,
            winStride=(8, 8),
            padding=(8, 8),
            scale=1.08,
        )
    except Exception:
        return 0.0
    if len(rects) == 0:
        return 0.0
    frame_area = float(image.shape[0] * image.shape[1]) or 1.0
    area = 0.0
    for (x, y, w, h), weight in zip(rects, weights):
        if float(weight) < 0.1:
            continue
        area += float(w * h)
    return min(area / frame_area, 1.0)


def _probe_frame(path: Path, ts: float) -> ProbeFrame:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        gray = rgb.convert("L")
        hist = _color_histogram(rgb)
        ahash = _average_hash(gray)
        luminance = ImageStat.Stat(gray).mean[0] / 255.0
        edge_mean = ImageStat.Stat(gray.filter(ImageFilterShim.find_edges())).mean[0] / 255.0
    return ProbeFrame(
        time=ts,
        path=path,
        hist=hist,
        ahash=ahash,
        luminance=luminance,
        edge_mean=edge_mean,
        reasons=[],
    )


class ImageFilterShim:
    """Import PIL.ImageFilter lazily to keep the top-level dependency tiny."""

    @staticmethod
    def find_edges():
        from PIL import ImageFilter

        return ImageFilter.FIND_EDGES


def _color_histogram(image: Image.Image) -> list[float]:
    small = image.resize((32, 32))
    bins = [0] * 64
    for r, g, b in small.getdata():
        index = (r // 64) * 16 + (g // 64) * 4 + (b // 64)
        bins[index] += 1
    total = float(sum(bins)) or 1.0
    return [value / total for value in bins]


def _average_hash(gray: Image.Image) -> int:
    small = gray.resize((8, 8))
    pixels = list(small.getdata())
    avg = sum(pixels) / len(pixels)
    bits = 0
    for i, pixel in enumerate(pixels):
        if pixel >= avg:
            bits |= 1 << i
    return bits


def _score_probe_frames(frames: list[ProbeFrame]) -> None:
    prev_gray: list[int] | None = None
    diffs = []
    for frame in frames:
        with Image.open(frame.path) as image:
            gray = list(image.convert("L").resize((32, 56)).getdata())
        if prev_gray is not None:
            diff = sum(abs(a - b) for a, b in zip(gray, prev_gray)) / (len(gray) * 255.0)
            frame.diff_prev = diff
            diffs.append(diff)
        prev_gray = gray

    mean = sum(diffs) / len(diffs) if diffs else 0.0
    variance = sum((value - mean) ** 2 for value in diffs) / len(diffs) if diffs else 0.0
    std = math.sqrt(variance)
    threshold = mean + std * 0.8

    for frame in frames:
        motion = frame.diff_prev
        contrast = frame.edge_mean
        frame.score = (
            motion * 3.0
            + contrast * 0.7
            + frame.motion_area * 2.0
            + frame.person_area * 1.2
        )
        if motion >= threshold and motion > 0.03:
            frame.score += 1.0
            frame.reasons = [*(frame.reasons or []), "motion_peak"]


def _select_times(
    duration: float,
    shot_ranges: list[tuple[float, float]],
    frames: list[ProbeFrame],
    max_frames: int,
) -> list[float]:
    selected: list[float] = []
    min_gap = max(0.35, duration / max(max_frames * 1.8, 1))

    def add(ts: float, reason: str) -> None:
        ts = _nearest_probe_time(frames, _clamp(ts, 0.0, max(duration - 0.05, 0.0)))
        if all(abs(ts - existing) >= min_gap for existing in selected):
            selected.append(ts)
            nearest = min(frames, key=lambda frame: abs(frame.time - ts))
            nearest.reasons = [*(nearest.reasons or []), reason]

    add(0.0, "start")
    add(max(duration - 0.2, 0.0), "end")

    for start, end in shot_ranges:
        start = _clamp(float(start), 0.0, duration)
        end = _clamp(float(end), 0.0, duration)
        if end < start:
            start, end = end, start
        span = end - start
        add(start, "shot_start")
        add(start + span * 0.5, "shot_mid")
        add(max(start, end - 0.2), "shot_end")
        if span >= 8.0:
            add(start + span * 0.25, "long_shot_quarter")
            add(start + span * 0.75, "long_shot_quarter")

    coverage_slots = max(6, min(max_frames // 3, 16))
    for i in range(coverage_slots):
        ratio = i / max(coverage_slots - 1, 1)
        add(duration * ratio, "time_coverage")

    for frame in _top_separated(frames, key=lambda item: item.score, count=max_frames // 3, min_gap=min_gap):
        add(frame.time, "visual_change")

    diverse = _diverse_frames(frames, selected, count=max_frames, min_gap=min_gap)
    for frame in diverse:
        if len(selected) >= max_frames:
            break
        add(frame.time, "visual_diversity")

    return sorted(round(ts, 2) for ts in selected[:max_frames])


def _top_separated(
    frames: list[ProbeFrame],
    key,
    count: int,
    min_gap: float,
) -> list[ProbeFrame]:
    picked: list[ProbeFrame] = []
    for frame in sorted(frames, key=key, reverse=True):
        if all(abs(frame.time - existing.time) >= min_gap for existing in picked):
            picked.append(frame)
        if len(picked) >= count:
            break
    return picked


def _diverse_frames(
    frames: list[ProbeFrame],
    selected_times: list[float],
    count: int,
    min_gap: float,
) -> list[ProbeFrame]:
    picked: list[ProbeFrame] = []
    anchors = [min(frames, key=lambda frame: abs(frame.time - ts)) for ts in selected_times] or [frames[0]]
    while len(picked) < count:
        best: tuple[float, ProbeFrame] | None = None
        for frame in frames:
            if any(abs(frame.time - ts) < min_gap for ts in selected_times):
                continue
            if any(abs(frame.time - existing.time) < min_gap for existing in picked):
                continue
            distance = min(_frame_distance(frame, anchor) for anchor in anchors + picked)
            if best is None or distance > best[0]:
                best = (distance, frame)
        if best is None:
            break
        picked.append(best[1])
    return picked


def _frame_distance(a: ProbeFrame, b: ProbeFrame) -> float:
    hist_distance = sum(abs(x - y) for x, y in zip(a.hist, b.hist))
    hash_distance = (a.ahash ^ b.ahash).bit_count() / 64.0
    luminance_distance = abs(a.luminance - b.luminance)
    return hist_distance + hash_distance * 0.6 + luminance_distance * 0.4


def _coverage_times(
    duration: float,
    shot_ranges: list[tuple[float, float]],
    max_frames: int,
) -> list[float]:
    times = {0.0, max(duration - 0.2, 0.0)}
    interval = max(1.0, duration / max(max_frames - 1, 1))
    t = 0.0
    while t <= duration:
        times.add(round(t, 2))
        t += interval
    for start, end in shot_ranges:
        mid = float(start) + (float(end) - float(start)) / 2.0
        times.update({round(float(start), 2), round(mid, 2), round(max(float(start), float(end) - 0.2), 2)})
    return sorted(ts for ts in times if 0 <= ts <= duration)[:max_frames]


def _nearest_probe_time(frames: list[ProbeFrame], ts: float) -> float:
    return min(frames, key=lambda frame: abs(frame.time - ts)).time


def _write_debug(
    debug_dir: Path | None,
    duration: float,
    interval: float,
    selected: list[float],
    frames: list[ProbeFrame],
    warning: str,
) -> None:
    if not debug_dir:
        return
    debug_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "duration": round(duration, 3),
        "probe_interval": interval,
        "selected_times": selected,
        "warning": warning,
        "candidates": [
            {
                "time": frame.time,
                "score": round(frame.score, 4),
                "diff_prev": round(frame.diff_prev, 4),
                "edge_mean": round(frame.edge_mean, 4),
                "luminance": round(frame.luminance, 4),
                "motion_area": round(frame.motion_area, 4),
                "person_area": round(frame.person_area, 4),
                "selected": frame.time in selected,
                "reasons": frame.reasons or [],
            }
            for frame in frames
        ],
    }
    (debug_dir / "algorithmic_keyframes.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    contact_frames = [frame for frame in frames if frame.time in selected]
    frame_dir = debug_dir / "selected_probe_frames"
    frame_dir.mkdir(exist_ok=True)
    for frame in contact_frames:
        shutil.copy2(frame.path, frame_dir / f"{frame.time:06.2f}s.jpg")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
