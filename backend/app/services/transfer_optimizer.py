"""Post-process structure transfer results before rendering.

The LLM is good at creative mapping, but the renderer needs a stricter
timeline: bounded source ranges, short punchy shots, a CTA when the source
sample has one, and edit hints for reframing / retiming.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from ..models.video_structure import VideoStructure


SOURCE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*s?", re.I)


def optimize_transfer_result(
    result: dict[str, Any],
    source_structure: VideoStructure,
    target_structure: VideoStructure | None = None,
    target_meta: dict | None = None,
) -> dict[str, Any]:
    """Make a transfer JSON executable and closer to viral short-video rhythm."""
    optimized = copy.deepcopy(result or {})
    storyboard = _get_storyboard(optimized)

    if not storyboard:
        storyboard = _fallback_storyboard(target_structure, source_structure)

    duration = _target_duration(target_structure, target_meta)
    storyboard = _normalize_storyboard(storyboard, duration)

    cta_added = False
    if _source_has_cta(source_structure) and not any(_is_cta(shot) for shot in storyboard):
        storyboard.append(_make_cta_shot(source_structure))
        cta_added = True

    _apply_source_spatial_pattern(storyboard, source_structure, target_structure)
    _enforce_near_to_far_target_windows(storyboard, target_structure)
    _drop_redundant_walk_far_shots(storyboard)
    _drop_overlapping_far_shots(storyboard)

    for i, shot in enumerate(storyboard, start=1):
        shot["shot_number"] = i

    script = _sanitize_script_for_spatial(_normalize_script(optimized.get("script"), storyboard))
    _rewrite_viewer_subtitles(storyboard, script)
    _sync_cta_subtitles(storyboard, script)

    optimized["storyboard"] = storyboard
    optimized["script"] = script
    optimized["material_needs"] = _material_needs_from_storyboard(storyboard, optimized.get("material_needs"))
    optimized["timeline_metrics"] = _timeline_metrics(storyboard, duration, cta_added)
    optimized["material_coverage"] = _material_coverage(storyboard)
    return optimized


def _get_storyboard(result: dict[str, Any]) -> list[dict[str, Any]]:
    keys = ("storyboard", "新分镜 (storyboard)", "新分镜")
    for key in keys:
        value = result.get(key)
        if isinstance(value, list):
            return [shot for shot in value if isinstance(shot, dict)]
    return []


def _target_duration(target_structure: VideoStructure | None, target_meta: dict | None) -> float:
    if target_structure:
        return float(target_structure.meta.duration)
    if target_meta and target_meta.get("duration"):
        return float(target_meta["duration"])
    return 0.0


def _normalize_storyboard(storyboard: list[dict[str, Any]], target_duration: float) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    next_start = 0.0

    for i, raw in enumerate(storyboard, start=1):
        shot = copy.deepcopy(raw)
        shot["shot_number"] = int(shot.get("shot_number") or i)
        shot_type = str(shot.get("type") or "medium")
        shot["type"] = shot_type

        desired = _safe_float(shot.get("duration"), 3.0)
        if _is_cta(shot):
            desired = _clamp(desired, 2.5, 4.0)
        elif "hook" in str(shot.get("content", "")).lower():
            desired = _clamp(desired, 1.5, 3.0)
        else:
            desired = _clamp(desired, 1.5, 5.0)
        shot["duration"] = round(desired, 2)

        source = str(shot.get("source", ""))
        start, end = parse_source_range(source)
        if start is None or end is None:
            if _is_cta(shot):
                shot["source"] = "需生成"
            else:
                start = next_start
                end = min(start + desired, target_duration) if target_duration else start + desired
                shot["source"] = f"目标视频 {start:.1f}-{end:.1f}s"
        elif target_duration:
            start = _clamp(start, 0.0, target_duration)
            end = _clamp(end, start + 0.3, target_duration)
            shot["source"] = f"目标视频 {start:.1f}-{end:.1f}s"

        edit = shot.get("edit") if isinstance(shot.get("edit"), dict) else {}
        edit.setdefault("crop", _crop_for_type(shot_type))
        edit["crop"] = _adjust_crop_for_content(str(edit.get("crop", "")), shot_type, str(shot.get("content", "")))
        edit.setdefault("pace", "fast-cut" if desired <= 3.0 else "hold")
        if start is not None and end is not None:
            source_duration = max(end - start, 0.3)
            edit["speed"] = round(_clamp(source_duration / desired, 0.5, 2.4), 3)
            next_start = end
        else:
            edit.setdefault("speed", 1.0)
        shot["edit"] = edit

        subtitle = str(shot.get("subtitle", "")).strip()
        if subtitle:
            shot["subtitle"] = _shorten_subtitle(subtitle)
        normalized.append(shot)

    return normalized


def parse_source_range(source: str) -> tuple[float | None, float | None]:
    if not source:
        return None, None
    match = SOURCE_RE.search(source)
    if not match:
        return None, None
    return float(match.group(1)), float(match.group(2))


def _fallback_storyboard(
    target_structure: VideoStructure | None,
    source_structure: VideoStructure,
) -> list[dict[str, Any]]:
    if not target_structure or target_structure.meta.duration <= 0:
        return [_make_cta_shot(source_structure)]

    duration = target_structure.meta.duration
    windows = _candidate_windows(target_structure)
    if not windows:
        windows = [(0.0, min(3.0, duration), "medium", "目标素材亮点")]

    picked = _pick_spread(windows, max_count=4)
    subtitles = ["先别划走", "近处手势舞", "位置逐渐拉远", "校园感拉满"]
    storyboard = []
    for i, (start, end, shot_type, content) in enumerate(picked, start=1):
        storyboard.append(
            {
                "shot_number": i,
                "type": shot_type,
                "content": content,
                "duration": min(max(end - start, 1.8), 4.0),
                "camera_move": "硬切",
                "subtitle": subtitles[min(i - 1, len(subtitles) - 1)],
                "source": f"目标视频 {start:.1f}-{end:.1f}s",
            }
        )
    if _source_has_cta(source_structure):
        storyboard.append(_make_cta_shot(source_structure))
    return storyboard


def _candidate_windows(target: VideoStructure) -> list[tuple[float, float, str, str]]:
    windows: list[tuple[float, float, str, str]] = []
    for shot in target.shots:
        start = float(shot.start_time)
        end = min(float(shot.end_time), target.meta.duration)
        if end <= start:
            continue
        span = end - start
        step = 3.0 if span > 8 else span
        pos = start
        while pos < end - 0.4:
            chunk_end = min(pos + step, end)
            windows.append((pos, chunk_end, shot.type or "medium", shot.content))
            pos += step
    return sorted(windows, key=lambda w: _window_score(w), reverse=True)


def _window_score(window: tuple[float, float, str, str]) -> float:
    start, end, shot_type, content = window
    text = f"{shot_type} {content}"
    score = 0.0
    for keyword in ("跳", "舞", "笑", "转身", "特写", "手势", "动作"):
        if keyword in text:
            score += 2.0
    for keyword in ("远景", "远处", "全景", "tiny", "小"):
        if keyword in text:
            score += 1.2
    if shot_type in {"close-up", "medium"} and start < 15:
        score += 1.5
    if shot_type == "wide" and start > 12:
        score += 1.5
    score += min(end - start, 4.0) * 0.2
    return score


def _pick_spread(
    windows: list[tuple[float, float, str, str]],
    max_count: int,
) -> list[tuple[float, float, str, str]]:
    picked: list[tuple[float, float, str, str]] = []
    for window in windows:
        if all(abs(window[0] - existing[0]) >= 4.0 for existing in picked):
            picked.append(window)
        if len(picked) >= max_count:
            break
    return sorted(picked, key=lambda w: w[0])


def _normalize_script(script: Any, storyboard: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(script, list) and script:
        normalized = []
        for seg in script:
            if not isinstance(seg, dict):
                continue
            item = copy.deepcopy(seg)
            item["duration"] = round(_safe_float(item.get("duration"), 3.0), 2)
            normalized.append(item)
        if normalized:
            return normalized

    total = sum(_safe_float(shot.get("duration"), 0.0) for shot in storyboard)
    return [
        {"type": "hook", "text": "开头抓眼", "purpose": "用高光画面快速停留", "duration": round(min(total, 3.0), 2)},
        {"type": "demo", "text": "节奏展示", "purpose": "按样例节奏重组素材", "duration": round(max(total - 6.0, 0.0), 2)},
        {"type": "cta", "text": "搜索同款挑战", "purpose": "承接样例的挑战引导", "duration": 3.0},
    ]


def _timeline_metrics(storyboard: list[dict[str, Any]], target_duration: float, cta_added: bool) -> dict[str, Any]:
    used_ranges = []
    for shot in storyboard:
        start, end = parse_source_range(str(shot.get("source", "")))
        if start is not None and end is not None:
            used_ranges.append([round(start, 2), round(end, 2)])

    return {
        "total_duration": round(sum(_safe_float(shot.get("duration"), 0) for shot in storyboard), 2),
        "source_range_count": len(used_ranges),
        "source_ranges": used_ranges,
        "target_duration": round(target_duration, 2) if target_duration else None,
        "cta_added": cta_added,
        "spatial_roles": [
            shot.get("edit", {}).get("spatial_role")
            for shot in storyboard
            if isinstance(shot.get("edit"), dict) and shot.get("edit", {}).get("spatial_role")
        ],
    }


def _sync_cta_subtitles(storyboard: list[dict[str, Any]], script: list[dict[str, Any]]) -> None:
    cta_text = _cta_text_from_script(script)
    if not cta_text:
        cta_text = _cta_text_from_storyboard(storyboard)
    if not cta_text:
        return

    for shot in storyboard:
        if _is_cta(shot):
            shot["subtitle"] = cta_text
            break


def _rewrite_viewer_subtitles(storyboard: list[dict[str, Any]], script: list[dict[str, Any]]) -> None:
    """Replace internal spatial labels with viewer-facing short-video captions."""
    cta_text = _cta_text_from_script(script) or _cta_text_from_storyboard(storyboard)
    for shot in storyboard:
        if _is_cta(shot):
            continue

        role = shot.get("edit", {}).get("spatial_role", "") if isinstance(shot.get("edit"), dict) else ""
        current = str(shot.get("subtitle", "")).strip()
        if current and not _looks_like_internal_subtitle(current):
            continue

        shot["subtitle"] = _viewer_subtitle_for_role(role, shot, cta_text)


def _looks_like_internal_subtitle(text: str) -> bool:
    return text in {
        "近处开场",
        "位置拉开",
        "变远变小",
        "远处手势舞",
        "环境接住节奏",
        "近处手势舞",
        "位置逐渐拉远",
        "校园感拉满",
    }


def _viewer_subtitle_for_role(role: str, shot: dict[str, Any], cta_text: str) -> str:
    content = str(shot.get("content", ""))
    if role == "near":
        return "开拍开拍"
    if role == "mid":
        if any(key in content for key in ("笑场", "不协调", "翻车")):
            return "这段太真实"
        return "手势先跟上"
    if role == "far":
        return "操场版来了"
    if role == "empty":
        return "越来越有感觉"
    if role == "cta":
        return cta_text or "搜同款挑战"
    return _shorten_subtitle(str(shot.get("subtitle", "")) or "这段太真实")


def _cta_text_from_script(script: list[dict[str, Any]]) -> str:
    for seg in script:
        if str(seg.get("type", "")).lower() != "cta":
            continue
        cleaned = _clean_cta_text(str(seg.get("text", "")))
        if cleaned and not _is_generic_cta_text(cleaned):
            return cleaned
    return ""


def _cta_text_from_storyboard(storyboard: list[dict[str, Any]]) -> str:
    for shot in storyboard:
        if not _is_cta(shot):
            continue
        text = f"{shot.get('content', '')} {shot.get('subtitle', '')}"
        for pattern in (r"带有([^，。、“”\"「」]{2,24}挑战)", r"[「\"]([^」\"]{2,24}挑战)[」\"]"):
            match = re.search(pattern, text)
            if match:
                cleaned = _clean_cta_text(match.group(1))
                if cleaned and not _is_generic_cta_text(cleaned):
                    return cleaned
    return ""


def _clean_cta_text(text: str) -> str:
    cleaned = re.sub(r"\s+", "", text)
    cleaned = cleaned.replace("大家都在抖音搜索", "")
    cleaned = re.sub(r"^(抖音)?(搜索|搜)", "", cleaned)
    cleaned = cleaned.replace("关键词", "")
    return _shorten_subtitle(cleaned, max_chars=18)


def _is_generic_cta_text(text: str) -> bool:
    return text in {"同款挑战", "参与挑战", "同款参与挑战", "搜同款参与挑战", "来参与同款挑战"}


def _material_needs_from_storyboard(storyboard: list[dict[str, Any]], existing: Any) -> dict[str, Any]:
    required = []
    for shot in storyboard:
        role = shot.get("edit", {}).get("spatial_role", "") if isinstance(shot.get("edit"), dict) else ""
        start, end = parse_source_range(str(shot.get("source", "")))
        if start is not None and end is not None:
            required.append(
                {
                    "type": "实拍素材",
                    "description": f"{shot.get('source')} 的{_role_label(role)}片段",
                    "purpose": _role_purpose(role),
                }
            )
        elif _is_cta(shot):
            required.append(
                {
                    "type": "图文素材",
                    "description": f"抖音搜索 CTA 页面：{shot.get('subtitle', '同款挑战')}",
                    "purpose": "补齐样例结尾搜索引导，承接挑战参与动作。",
                }
            )

    optional = []
    if isinstance(existing, dict):
        raw_optional = existing.get("可选素材列表", [])
        if isinstance(raw_optional, list):
            optional = [item for item in raw_optional if isinstance(item, dict)]

    return {"必需素材列表": required, "可选素材列表": optional}


def _role_label(role: str) -> str:
    return {
        "near": "近景开场",
        "mid": "中景手势动作",
        "far": "远景主体变小",
        "empty": "环境释放",
        "cta": "搜索引导",
    }.get(role, "可用")


def _role_purpose(role: str) -> str:
    return {
        "near": "作为开场 hook，保留目标素材原本的近距离亲近感。",
        "mid": "承接近景，展示清晰手势动作和人物关系。",
        "far": "迁移样例主体变远、画面占比变小的空间轨迹。",
        "empty": "让操场环境接住节奏，形成释放感。",
        "cta": "引导用户搜索并参与同款挑战。",
    }.get(role, "支撑迁移后分镜。")


def _material_coverage(storyboard: list[dict[str, Any]]) -> dict[str, Any]:
    """Explain which structure slots reuse target footage and which are filled."""
    matches = []
    gaps = []

    for shot in storyboard:
        shot_number = int(_safe_float(shot.get("shot_number"), 0))
        source = str(shot.get("source", ""))
        role = ""
        if isinstance(shot.get("edit"), dict):
            role = str(shot["edit"].get("spatial_role") or "")

        start, end = parse_source_range(source)
        if start is not None and end is not None:
            matches.append(
                {
                    "shot_number": shot_number,
                    "source": source,
                    "time_range": [round(start, 2), round(end, 2)],
                    "spatial_role": role,
                    "match_quality": "direct_reuse",
                    "note": "复用目标视频片段，并按 edit 建议裁切、变速、叠字幕。",
                }
            )
            continue

        cta = _is_cta(shot)
        gaps.append(
            {
                "shot_number": shot_number,
                "gap_type": "结尾 CTA 镜头" if cta else "缺少可直接复用素材",
                "severity": "可控" if cta else "关键",
                "spatial_role": role or ("cta" if cta else ""),
                "filling_strategy": (
                    "生成抖音搜索引导页，并用样例视频音频作为主 BGM。"
                    if cta
                    else "用字幕包装、局部放大、素材重组或 AIGC 图片补足。"
                ),
                "note": str(shot.get("content", "")),
            }
        )

    total = len(storyboard)
    matched = len(matches)
    generated = len(gaps)
    return {
        "source_material_slots": total,
        "matched_source_slots": matched,
        "generated_or_packaging_slots": generated,
        "coverage_ratio": round(matched / total, 2) if total else 0.0,
        "matches": matches,
        "gaps": gaps,
        "filling_summary": (
            "目标素材可覆盖主体镜头；缺口通过 CTA 生成、字幕包装和样例 BGM 迁移补齐。"
            if gaps
            else "所有分镜都能直接从目标素材取材。"
        ),
    }


def _apply_source_spatial_pattern(
    storyboard: list[dict[str, Any]],
    source_structure: VideoStructure,
    target_structure: VideoStructure | None = None,
) -> None:
    if not _source_moves_away(source_structure):
        return

    video_shots = [shot for shot in storyboard if not _is_cta(shot)]
    if not video_shots:
        return

    role_sets = {
        1: ["near"],
        2: ["near", "far"],
        3: ["near", "mid", "far"],
        4: ["near", "mid", "far", "empty"],
    }
    roles = role_sets.get(len(video_shots), ["near", "mid"] + ["far"] * max(0, len(video_shots) - 3) + ["empty"])
    subtitles = {
        "near": "近处开场",
        "mid": "位置拉开",
        "far": "变远变小",
        "empty": "环境接住节奏",
    }

    for shot, role in zip(video_shots, roles):
        edit = shot.get("edit") if isinstance(shot.get("edit"), dict) else {}
        edit["spatial_role"] = role
        shot["edit"] = edit
        shot["subtitle"] = subtitles.get(role, shot.get("subtitle", ""))
        content = str(shot.get("content", ""))
        content = content.replace("笑着", "")
        content = content.replace("大笑", "")
        content = content.replace("奔跑", "向远处移动")
        content = content.replace("跑开", "远离镜头")
        if role in {"near", "mid"} and "手势舞" not in content and "跳舞" in content:
            content = content.replace("跳舞", "跳手势舞")
        if role == "far":
            content = _deemphasize_walking(content)
        if role == "empty":
            content = _deemphasize_walking(content).replace("边跳手势舞边", "")
        shot["content"] = content

    _prefer_far_action_over_walk(video_shots, target_structure)

    for shot in storyboard:
        if _is_cta(shot):
            edit = shot.get("edit") if isinstance(shot.get("edit"), dict) else {}
            edit["spatial_role"] = "cta"
            shot["edit"] = edit


def _prefer_far_action_over_walk(
    video_shots: list[dict[str, Any]],
    target_structure: VideoStructure | None,
) -> None:
    if not target_structure:
        return

    far_action_ranges = []
    for target_shot in target_structure.shots:
        content = target_shot.content
        if target_shot.type == "wide" and any(k in content for k in ("手势舞", "跳", "舞")):
            start = float(target_shot.start_time)
            end = float(target_shot.end_time)
            # Some analyzers describe a whole far shot as "run there, stop, dance".
            # In that case, bias the usable window toward the latter action part.
            if any(k in content for k in ("停下", "转身面向", "挥手", "做舞蹈", "手势舞")) and any(k in content for k in ("跑", "奔跑", "走")):
                start = start + (end - start) * 0.35
            far_action_ranges.append((start, end, content))

    if not far_action_ranges:
        return

    used = 0
    for shot in video_shots:
        role = shot.get("edit", {}).get("spatial_role") if isinstance(shot.get("edit"), dict) else ""
        text = f"{shot.get('content', '')} {shot.get('source', '')}"
        if role == "far" and any(k in text for k in ("跑", "奔跑", "走", "转身背对")):
            start, end, content = far_action_ranges[min(used, len(far_action_ranges) - 1)]
            duration = _safe_float(shot.get("duration"), 3.0)
            source_end = min(end, start + max(duration * 1.8, duration + 1.0))
            shot["source"] = f"目标视频 {start:.1f}-{source_end:.1f}s"
            shot["content"] = f"远景主体继续做手势舞，人物占比变小，复刻近到远的空间关系。{content}"
            shot["subtitle"] = "远处手势舞"
            edit = shot.get("edit") if isinstance(shot.get("edit"), dict) else {}
            edit["speed"] = round(_clamp((source_end - start) / duration, 0.5, 2.4), 3)
            shot["edit"] = edit
            used += 1


def _enforce_near_to_far_target_windows(
    storyboard: list[dict[str, Any]],
    target_structure: VideoStructure | None,
) -> None:
    """Keep the transfer focused on scale/position, not running as an action."""
    if not target_structure:
        return

    for shot in storyboard:
        role = shot.get("edit", {}).get("spatial_role") if isinstance(shot.get("edit"), dict) else ""
        duration = _safe_float(shot.get("duration"), 3.0)
        if role == "near" and _should_replace_near(shot):
            replacement = _best_spatial_window(target_structure, "near", duration)
            if replacement:
                _apply_spatial_window(shot, replacement, duration, "near")
        elif role == "mid" and _should_replace_mid(shot):
            replacement = _best_spatial_window(target_structure, "mid", duration)
            if replacement:
                _apply_spatial_window(shot, replacement, duration, "mid")
        elif role == "far" and (_should_replace_far_walk(shot) or _far_is_too_late_for_transition(shot, target_structure)):
            replacement = _best_spatial_window(target_structure, "far", duration)
            if replacement:
                _apply_spatial_window(shot, replacement, duration, "far")
        elif role == "empty":
            replacement = _best_spatial_window(target_structure, "empty", duration)
            if replacement:
                _apply_spatial_window(shot, replacement, duration, "empty")


def _should_replace_far_walk(shot: dict[str, Any]) -> bool:
    text = f"{shot.get('content', '')} {shot.get('source', '')}"
    return _is_transition_walk({"content": text}) and not _has_stable_far_pose(text)


def _far_is_too_late_for_transition(shot: dict[str, Any], target_structure: VideoStructure) -> bool:
    start, _ = parse_source_range(str(shot.get("source", "")))
    if start is None or target_structure.meta.duration <= 0:
        return False
    return start / target_structure.meta.duration >= 0.65


def _should_replace_near(shot: dict[str, Any]) -> bool:
    text = f"{shot.get('content', '')} {shot.get('source', '')}"
    return not any(k in text for k in ("近景", "特写", "半张脸", "前景", "近处"))


def _should_replace_mid(shot: dict[str, Any]) -> bool:
    text = f"{shot.get('content', '')} {shot.get('source', '')}"
    if _is_running_text(text) or any(k in text for k in ("转身背对", "往远处", "拉开", "远离镜头")):
        return True
    return not any(k in text for k in ("手势", "舞", "动作", "互动", "站在画面中心", "并排"))


def _best_spatial_window(
    target_structure: VideoStructure,
    role: str,
    duration: float,
) -> tuple[float, float, str] | None:
    scored: list[tuple[float, float, float, str]] = []
    target_duration = max(float(target_structure.meta.duration), 1.0)
    for shot in target_structure.shots:
        if shot.type == "text-overlay":
            continue
        start = float(shot.start_time)
        end = min(float(shot.end_time), target_duration)
        if end <= start:
            continue
        progress = start / target_duration
        end_progress = end / target_duration
        content = shot.content
        text = f"{shot.type} {shot.subject_distance} {shot.subject_position} {shot.subject_motion} {content}"
        score = 0.0

        if role == "near":
            if shot.subject_distance in {"near", "large"}:
                score += 5.0
            if shot.type == "close-up":
                score += 3.0
            if any(k in text for k in ("特写", "半张脸", "前景", "近景", "近处")):
                score += 4.0
            if progress <= 0.2:
                score += 3.0
            if _is_running_text(text):
                score -= 8.0
        elif role == "mid":
            if shot.subject_distance in {"mid", "medium"}:
                score += 4.0
            if shot.type == "medium":
                score += 3.0
            if any(k in text for k in ("手势", "舞", "动作", "互动", "站定", "并排", "画面居中")):
                score += 4.0
            if any(k in text for k in ("手势舞", "手势", "舞蹈", "同步做")):
                score += 3.0
            if any(k in text for k in ("整理衣服", "整理头发", "准备开始")):
                score -= 1.0
            if progress <= 0.35:
                score += 2.0
            if 0.02 <= progress <= 0.09:
                score += 6.0
            if _is_running_text(text) or any(k in text for k in ("转身背对", "往远处", "拉开距离")):
                score -= 8.0
        elif role == "far":
            if shot.subject_distance == "far":
                score += 5.0
            elif shot.subject_distance == "tiny":
                score += 2.0
            if shot.type == "wide":
                score += 2.0
            if any(k in text for k in ("远处", "身影", "占比", "小", "全景")):
                score += 2.0
            if any(k in text for k in ("停下", "站定", "调整站位", "商量拍摄位置")):
                score += 5.0
            if progress >= 0.35:
                score += 3.0
            if progress >= 0.45:
                score += 1.0
            if progress >= 0.65:
                score -= 5.0
            if _is_running_text(text) and not _has_stable_far_pose(text):
                score -= 8.0
        else:
            if shot.subject_distance in {"tiny", "none"}:
                score += 5.0
            if shot.type == "wide":
                score += 2.0
            if any(k in text for k in ("开阔", "全景", "天空", "云层", "环境", "操场")):
                score += 3.0
            if progress >= 0.6:
                score += 4.0
            if end_progress >= 0.85:
                score += 2.0
            if _is_running_text(text) and not _has_stable_far_pose(text):
                score -= 2.0

        if score <= 0:
            continue
        scored.append((score, start, end, content))

    if not scored:
        return None

    _, start, end, content = max(scored, key=lambda item: item[0])
    if role in {"near", "mid"}:
        source_span = min(end - start, max(duration * 1.8, duration + 1.0))
        source_start = start
        source_end = min(end, source_start + source_span)
    elif role == "far":
        source_span = min(end - start, max(duration * 1.7, 4.0))
        source_start = max(start, end - source_span)
        source_end = end
    else:
        source_span = min(end - start, max(duration * 1.8, 6.0))
        preferred = target_structure.meta.duration * 0.8 if end / target_structure.meta.duration >= 0.85 else end - source_span
        source_start = _clamp(preferred, start, max(start, end - source_span))
        source_end = min(end, source_start + source_span)
    return round(source_start, 1), round(source_end, 1), content


def _is_running_text(text: str) -> bool:
    return any(k in text for k in ("奔跑", "往跑道远处跑", "往更远处跑", "跑到", "跑向", "转身背对"))


def _has_stable_far_pose(text: str) -> bool:
    return any(k in text for k in ("停下", "站定", "调整站位", "商量拍摄位置", "远处站", "保持队形"))


def _apply_spatial_window(
    shot: dict[str, Any],
    window: tuple[float, float, str],
    duration: float,
    role: str,
) -> None:
    start, end, content = window
    shot["source"] = f"目标视频 {start:.1f}-{end:.1f}s"
    if role == "near":
        shot["content"] = f"近景开场先抓住人物，保留画面前景的近距离关系。{content}"
        shot["subtitle"] = "开拍开拍"
    elif role == "mid":
        shot["content"] = f"中景主体站定做手势舞动作，承接开场并保持动作清晰。{_deemphasize_walking(content)}"
        shot["subtitle"] = "手势先跟上"
    elif role == "far":
        shot["content"] = f"远景主体已经变小，人物停在跑道远处调整队形，延续近到远的位置变化。{_deemphasize_walking(content)}"
        shot["subtitle"] = "操场版来了"
    else:
        shot["content"] = f"开阔操场全景接住节奏，人物成为远处很小的环境元素，释放空间感。{_deemphasize_walking(content)}"
        shot["subtitle"] = "越来越有感觉"

    edit = shot.get("edit") if isinstance(shot.get("edit"), dict) else {}
    edit["speed"] = round(_clamp((end - start) / max(duration, 0.3), 0.5, 2.4), 3)
    if role in {"near", "mid"}:
        edit["crop"] = _crop_for_type("close-up" if role == "near" else "medium")
        edit["pace"] = "fast-cut" if duration <= 3.0 else "hold"
    else:
        edit["crop"] = "none"
        edit["pace"] = "hold"
    shot["edit"] = edit


def _drop_redundant_walk_far_shots(storyboard: list[dict[str, Any]]) -> None:
    """Drop transition-only walk/run far shots when a far action shot exists."""
    better_far_exists = any(
        _is_far_role(shot) and not _is_transition_walk(shot)
        for shot in storyboard
    )
    if not better_far_exists:
        return

    filtered = []
    dropped = False
    for shot in storyboard:
        if (
            not dropped
            and _is_far_role(shot)
            and _is_transition_walk(shot)
            and not _has_dance_action(shot)
        ):
            dropped = True
            continue
        filtered.append(shot)

    if dropped:
        storyboard[:] = filtered


def _drop_overlapping_far_shots(storyboard: list[dict[str, Any]]) -> None:
    kept: list[dict[str, Any]] = []
    for shot in storyboard:
        if not _is_far_role(shot):
            kept.append(shot)
            continue

        start, end = parse_source_range(str(shot.get("source", "")))
        duplicate = False
        if start is not None and end is not None:
            for existing in kept:
                if not _is_far_role(existing):
                    continue
                ex_start, ex_end = parse_source_range(str(existing.get("source", "")))
                if ex_start is None or ex_end is None:
                    continue
                overlap = max(0.0, min(end, ex_end) - max(start, ex_start))
                shorter = max(min(end - start, ex_end - ex_start), 0.1)
                if overlap / shorter >= 0.55:
                    duplicate = True
                    break
        if not duplicate:
            kept.append(shot)

    storyboard[:] = kept


def _is_far_role(shot: dict[str, Any]) -> bool:
    return isinstance(shot.get("edit"), dict) and shot["edit"].get("spatial_role") == "far"


def _is_transition_walk(shot: dict[str, Any]) -> bool:
    text = f"{shot.get('content', '')}"
    return any(k in text for k in ("奔跑", "往远处跑", "跑向", "转身背对", "远处移动", "拉开距离", "继续往"))


def _has_dance_action(shot: dict[str, Any]) -> bool:
    text = f"{shot.get('content', '')} {shot.get('subtitle', '')}"
    return any(k in text for k in ("手势舞", "舞蹈", "跳", "动作"))


def _source_moves_away(source_structure: VideoStructure) -> bool:
    tf = source_structure.transferable_features
    text = " ".join(
        [
            tf.spatial_pattern,
            tf.subject_trajectory,
            tf.composition_pattern,
            *[shot.content for shot in source_structure.shots],
            *[shot.subject_motion for shot in source_structure.shots],
        ]
    )
    return any(key in text for key in ("远离", "退场", "走远", "离开", "退出", "占比变小", "全景", "环境空镜"))


def _deemphasize_walking(content: str) -> str:
    replacements = {
        "轻快向远处移动": "在远处保持队形",
        "往跑道远处轻快向远处移动": "在跑道远处保持队形",
        "往跑道远处": "在跑道远处",
        "向远处移动": "拉开距离",
        "慢慢往画面右侧走远": "处在画面远端",
        "走远": "变远",
        "奔跑": "位置拉远",
        "跑": "拉远",
        "拉远道": "跑道",
    }
    for old, new in replacements.items():
        content = content.replace(old, new)
    return content


def _sanitize_script_for_spatial(script: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for seg in script:
        for key in ("text", "purpose"):
            value = str(seg.get(key, ""))
            value = value.replace("越跑越远", "位置越拉越远")
            value = value.replace("跑向操场远端", "位置拉到操场远端")
            value = value.replace("奔跑远离", "位置远离")
            value = value.replace("奔跑", "拉远")
            value = value.replace("跑远", "拉远")
            seg[key] = value
    return script


def _make_cta_shot(source_structure: VideoStructure) -> dict[str, Any]:
    text = _cta_text(source_structure)
    return {
        "shot_number": 999,
        "type": "text-overlay",
        "content": "深色渐变背景的抖音搜索引导页，居中搜索框和挑战入口",
        "duration": 3.2,
        "camera_move": "静止",
        "subtitle": text,
        "source": "需生成",
        "edit": {"crop": "none", "pace": "cta", "speed": 1.0},
    }


def _cta_text(source_structure: VideoStructure) -> str:
    cover = source_structure.packaging_structure.cover_style
    candidates = [
        cover.main_text,
        cover.subtitle_text,
        *(tg.content for tg in source_structure.packaging_structure.text_graphics),
        *(sec.text for sec in source_structure.script_structure if sec.type == "cta"),
    ]
    for text in candidates:
        text = str(text).strip()
        if text:
            cleaned = re.sub(r"\s+", "", text)
            cleaned = cleaned.replace("大家都在抖音搜索", "")
            return _shorten_subtitle(cleaned, max_chars=18)
    return "搜索同款挑战"


def _source_has_cta(source_structure: VideoStructure) -> bool:
    return any(sec.type == "cta" for sec in source_structure.script_structure) or any(
        shot.type == "text-overlay" for shot in source_structure.shots
    )


def _is_cta(shot: dict[str, Any]) -> bool:
    text = f"{shot.get('type', '')} {shot.get('content', '')} {shot.get('source', '')}"
    return "text-overlay" in text or "CTA" in text.upper() or "引导" in text or "搜索" in text or "需生成" in text


def _crop_for_type(shot_type: str) -> str:
    if shot_type == "close-up":
        return "tight"
    if shot_type == "medium":
        return "medium"
    return "none"


def _adjust_crop_for_content(crop: str, shot_type: str, content: str) -> str:
    if shot_type == "close-up" and any(key in content for key in ("半张脸", "前景左侧", "前景是女生")):
        return "none"
    return crop


def _shorten_subtitle(text: str, max_chars: int = 15) -> str:
    text = re.sub(r"\s+", "", text)
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
