"""Optional frame-based spatial audit.

The main analyzer sends the full video to Doubao. This module adds a second
pass that sends deterministic still frames in timestamp order and asks only for
subject scale / position / trajectory. It is deliberately narrow so it can
correct spatial misses without degrading script, audio, or packaging analysis.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from ..core.config import get_settings
from ..models.video_structure import VideoStructure
from .doubao_client import get_ark_client, parse_doubao_response
from .frame_sampler import choose_frame_times, extract_frames, write_frame_manifest


async def audit_spatial_with_frames(
    video_path: str,
    structure: VideoStructure,
    task_dir: Path,
    max_frames: int = 48,
) -> dict[str, Any]:
    """Run a frame-sequence spatial audit and persist the evidence."""
    frame_dir = task_dir / "spatial_audit_frames"
    shot_ranges = [(shot.start_time, shot.end_time) for shot in structure.shots]
    times = choose_frame_times(structure.meta.duration, shot_ranges, max_frames=max_frames)
    frames = extract_frames(video_path, frame_dir, times, width=360)
    write_frame_manifest(frames, task_dir / "spatial_audit_frames.json")

    if not frames:
        return {}

    result = await analyze_ordered_frames_with_doubao(frames, structure)
    (task_dir / "spatial_audit_raw.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (task_dir / "spatial_audit_summary.md").write_text(
        _audit_summary(result),
        encoding="utf-8",
    )
    return result


async def analyze_ordered_frames_with_doubao(
    frames: list[dict],
    structure: VideoStructure,
) -> dict[str, Any]:
    """Send ordered still frames to Doubao for a spatial-only audit."""
    settings = get_settings()
    client = get_ark_client()

    content: list[dict[str, Any]] = []
    for frame in frames:
        image_data = _encode_image_base64(frame["path"])
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{image_data}",
                },
            }
        )

    timeline = "\n".join(f"- frame {f['index']:03d}: {f['time']:.2f}s" for f in frames)
    prompt = f"""你会看到一组按时间顺序排列的视频抽帧图片。每张图对应一个 frame index，时间戳如下：

{timeline}

这不是完整视频，只用于空间轨迹审计。请不要推断音频、转场或剧情，只回答画面里主体的距离、位置、占比和空间角色。

已有视频结构摘要：
- 时长: {structure.meta.duration:.1f}s
- 分辨率: {structure.meta.resolution}
- 当前 spatial_pattern: {structure.transferable_features.spatial_pattern}
- 当前 subject_trajectory: {structure.transferable_features.subject_trajectory}

请严格返回 JSON：
{{
  "spatial_keyframes": [
    {{
      "frame_index": 1,
      "time": 0.0,
      "subject_scale": "large|medium|small|tiny|none",
      "subject_position": "画面位置",
      "spatial_role": "near|mid|far|tiny|environment|cta",
      "subject_motion_inferred": "靠近|远离|横移|静止|退出|无",
      "note": "为什么重要"
    }}
  ],
  "spatial_pattern": "按时间总结空间调度",
  "subject_trajectory": "主体距离/位置轨迹",
  "composition_pattern": "构图占比变化",
  "recommended_segments": [
    {{
      "role": "near|mid|far|tiny|environment|cta",
      "start_time": 0.0,
      "end_time": 2.0,
      "reason": "为什么适合这个角色"
    }}
  ],
  "warnings": ["可能漏判或不确定的地方"]
}}"""

    content.append({"type": "text", "text": prompt})

    response = client.chat.completions.create(
        model=settings.ARK_MODEL,
        messages=[
            {
                "role": "system",
                "content": "你是短视频空间轨迹审计员，只根据按时间顺序给出的抽帧判断主体距离、位置和空间角色。",
            },
            {"role": "user", "content": content},
        ],
        temperature=0.1,
    )
    raw = response.choices[0].message.content
    parsed = parse_doubao_response(raw)
    if not parsed:
        parsed = {"raw_response": raw}
    return parsed


def merge_spatial_audit(structure: VideoStructure, audit: dict[str, Any]) -> VideoStructure:
    """Merge audit-level spatial summaries back into VideoStructure."""
    if not audit:
        return structure

    tf = structure.transferable_features
    if audit.get("spatial_pattern"):
        tf.spatial_pattern = str(audit["spatial_pattern"])
    if audit.get("subject_trajectory"):
        tf.subject_trajectory = str(audit["subject_trajectory"])
    if audit.get("composition_pattern"):
        tf.composition_pattern = str(audit["composition_pattern"])

    for shot in structure.shots:
        matches = [
            keyframe for keyframe in audit.get("spatial_keyframes", [])
            if isinstance(keyframe, dict)
            and shot.start_time <= _safe_float(keyframe.get("time"), -1) <= shot.end_time
        ]
        if not matches:
            continue
        scales = [str(item.get("subject_scale", "")) for item in matches]
        roles = [str(item.get("spatial_role", "")) for item in matches]
        positions = [str(item.get("subject_position", "")) for item in matches if item.get("subject_position")]
        motions = [str(item.get("subject_motion_inferred", "")) for item in matches if item.get("subject_motion_inferred")]
        shot.subject_distance = _dominant(scales) or shot.subject_distance
        if _dominant(roles) in {"tiny", "environment"}:
            shot.subject_distance = _dominant(roles)
        shot.subject_position = positions[len(positions) // 2] if positions else shot.subject_position
        shot.subject_motion = _dominant(motions) or shot.subject_motion

    return structure


def _encode_image_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _audit_summary(result: dict[str, Any]) -> str:
    lines = ["# Frame Spatial Audit", ""]
    lines.append(f"- spatial_pattern: {result.get('spatial_pattern', '')}")
    lines.append(f"- subject_trajectory: {result.get('subject_trajectory', '')}")
    lines.append(f"- composition_pattern: {result.get('composition_pattern', '')}")
    lines.append("")
    lines.append("## Keyframes")
    for item in result.get("spatial_keyframes", []):
        if not isinstance(item, dict):
            continue
        lines.append(
            f"- frame {item.get('frame_index')} @ {item.get('time')}s "
            f"scale={item.get('subject_scale')} role={item.get('spatial_role')} "
            f"pos={item.get('subject_position')}"
        )
        if item.get("note"):
            lines.append(f"  {item.get('note')}")
    lines.append("")
    lines.append("## Recommended Segments")
    for item in result.get("recommended_segments", []):
        if not isinstance(item, dict):
            continue
        lines.append(
            f"- {item.get('role')}: {item.get('start_time')}-{item.get('end_time')}s "
            f"{item.get('reason', '')}"
        )
    if result.get("warnings"):
        lines.append("")
        lines.append("## Warnings")
        for warning in result.get("warnings", []):
            lines.append(f"- {warning}")
    return "\n".join(lines) + "\n"


def _dominant(values: list[str]) -> str:
    values = [value for value in values if value]
    if not values:
        return ""
    return max(set(values), key=values.count)


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
