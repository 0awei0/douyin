"""结构迁移服务

将样例视频的创作结构迁移到新内容上。
"""

import json
from pathlib import Path

from volcenginesdkarkruntime import Ark

from ..core.config import get_settings
from ..models.video_structure import VideoStructure
from .doubao_client import load_prompt, get_ark_client, parse_doubao_response
from .transfer_optimizer import optimize_transfer_result


async def transfer_structure(
    source_structure: VideoStructure,
    target_description: str,
    target_meta: dict | None = None,
    target_structure: VideoStructure | None = None,
) -> dict:
    """将样例结构迁移到新内容

    Args:
        source_structure: 样例视频的分析结果
        target_description: 目标内容描述
        target_meta: 目标视频的元信息（时长等）
        target_structure: 目标视频的分析结果（如果有）

    Returns:
        迁移后的视频方案
    """
    settings = get_settings()
    client = get_ark_client()

    system_prompt = load_prompt("structure_transfer")

    # 构建样例结构摘要
    source_summary = build_source_summary(source_structure)

    # 构建目标内容描述
    target_info = target_description
    if target_meta:
        target_info += f"\n\n目标视频时长: {target_meta['duration']:.1f}秒, 分辨率: {target_meta['resolution']}"

    if target_structure:
        target_info += "\n\n### 目标视频内容结构\n"
        for sec in target_structure.script_structure:
            target_info += f"- [{sec.type}] {sec.start_time:.1f}-{sec.end_time:.1f}s: {sec.text}\n"
        for sh in target_structure.shots:
            target_info += f"- [{sh.type}] {sh.start_time:.1f}-{sh.end_time:.1f}s: {sh.content}\n"
            spatial = []
            if sh.subject_distance:
                spatial.append(f"distance={sh.subject_distance}")
            if sh.subject_position:
                spatial.append(f"position={sh.subject_position}")
            if sh.subject_motion:
                spatial.append(f"motion={sh.subject_motion}")
            if spatial:
                target_info += f"  空间: {', '.join(spatial)}\n"

    # 构建用户消息
    user_msg = f"""## 样例视频结构

{source_summary}

## 目标内容

{target_info}

请基于样例视频的创作套路，为目标内容生成新的视频创作方案。"""

    response = client.chat.completions.create(
        model=settings.ARK_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.4,
    )

    content = response.choices[0].message.content
    result = parse_doubao_response(content)
    return optimize_transfer_result(
        result,
        source_structure=source_structure,
        target_structure=target_structure,
        target_meta=target_meta,
    )


def build_source_summary(s: VideoStructure) -> str:
    """构建样例结构的文字摘要"""
    lines = []

    lines.append(f"视频时长: {s.meta.duration:.1f}秒, 分辨率: {s.meta.resolution}")
    lines.append("")

    # 脚本结构
    lines.append("### 脚本结构")
    for sec in s.script_structure:
        lines.append(f"- [{sec.type}] {sec.start_time:.1f}-{sec.end_time:.1f}s: {sec.text}")
        lines.append(f"  作用: {sec.purpose}")
    lines.append("")

    # 镜头
    lines.append("### 镜头编排")
    for sh in s.shots:
        lines.append(f"- [{sh.type}] {sh.start_time:.1f}-{sh.end_time:.1f}s: {sh.content}")
        lines.append(f"  镜头运动: {sh.camera_move}, 字幕: {'有' if sh.has_subtitle else '无'}")
        spatial_bits = []
        if sh.subject_distance:
            spatial_bits.append(f"主体距离: {sh.subject_distance}")
        if sh.subject_position:
            spatial_bits.append(f"位置: {sh.subject_position}")
        if sh.subject_motion:
            spatial_bits.append(f"主体运动: {sh.subject_motion}")
        if spatial_bits:
            lines.append("  空间信息: " + "，".join(spatial_bits))
    lines.append("")

    inferred_spatial = infer_spatial_pattern(s)
    if inferred_spatial:
        lines.append("### 空间轨迹（必须优先迁移）")
        lines.append(f"- {inferred_spatial}")
        lines.append("")

    # 音频
    if s.audio_structure.bgm.name:
        lines.append("### 音频")
        lines.append(f"- BGM: {s.audio_structure.bgm.name}, 情绪: {s.audio_structure.bgm.mood}")
        if s.audio_structure.voiceover.has:
            lines.append(f"- 旁白: {s.audio_structure.voiceover.style}")
        lines.append(f"- 卡节拍: {s.audio_structure.rhythm_sync}")
        lines.append("")

    # 包装
    lines.append("### 包装风格")
    lines.append(f"- 字幕: {s.packaging_structure.subtitle_style.font_size}, {s.packaging_structure.subtitle_style.color}")
    lines.append(f"- 视觉调性: {s.packaging_structure.overall_visual_tone}")
    if s.packaging_structure.transitions:
        lines.append("- 转场: " + ", ".join(f"{t.type}({t.time:.1f}s)" for t in s.packaging_structure.transitions))
    lines.append("")

    # 可迁移特征
    lines.append("### 可迁移特征（核心套路）")
    lines.append(f"- 开头策略: {s.transferable_features.hook_strategy}")
    lines.append(f"- 叙事模式: {s.transferable_features.narrative_pattern}")
    lines.append(f"- 节奏模式: {s.transferable_features.pacing_pattern}")
    if s.transferable_features.spatial_pattern:
        lines.append(f"- 空间调度: {s.transferable_features.spatial_pattern}")
    if s.transferable_features.subject_trajectory:
        lines.append(f"- 主体轨迹: {s.transferable_features.subject_trajectory}")
    if s.transferable_features.composition_pattern:
        lines.append(f"- 构图模式: {s.transferable_features.composition_pattern}")
    lines.append(f"- 吸引力技巧: {', '.join(s.transferable_features.engagement_techniques)}")

    return "\n".join(lines)


def infer_spatial_pattern(s: VideoStructure) -> str:
    """Infer a compact spatial trajectory when the analyzer did not expose it."""
    non_cta = [shot for shot in s.shots if shot.type != "text-overlay"]
    if not non_cta:
        return ""

    descriptors = []
    for shot in non_cta:
        distance = shot.subject_distance or shot.type
        motion = shot.subject_motion
        content = shot.content
        if not motion:
            if any(k in content for k in ("远处", "退场", "走远", "离开", "退出", "全景", "环境")):
                motion = "远离/退场"
            elif any(k in content for k in ("近", "特写", "前景")):
                motion = "近前景停留"
        descriptors.append(f"{shot.start_time:.1f}-{shot.end_time:.1f}s {distance} {motion}".strip())

    joined = " → ".join(descriptors)
    if any(k in joined for k in ("远离", "退场", "走远", "离开", "wide")):
        return (
            "固定机位下的主体距离变化是核心结构："
            f"{joined}。迁移时优先复刻人物/主体从近处到远处、画面主体占比逐渐变小、环境占比逐渐变大的轨迹。"
        )
    return ""
