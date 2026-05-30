"""视频结构分析服务

流程:
1. FFprobe 提取基础元信息（时长、分辨率、帧率）
2. 豆包视频理解 API 分析完整视频，输出结构化结果
3. 整合输出 VideoStructure
"""

import json
import os
import subprocess
import uuid
from pathlib import Path

from ..models.video_structure import (
    VideoStructure, VideoMeta, ScriptSection, Shot,
    AudioStructure, BGMInfo, VoiceoverInfo, SoundEffect,
    PackagingStructure, SubtitleStyle, Transition, TextGraphic,
    CoverStyle, TransferableFeatures,
)
from .doubao_client import analyze_video_with_doubao
from .analysis_artifacts import save_analysis_artifacts
from .spatial_audit import audit_spatial_with_frames, merge_spatial_audit

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def get_video_meta(video_path: str) -> VideoMeta:
    """用 ffprobe 提取视频基础元信息"""
    result = subprocess.run(
        ["ffprobe", "-hide_banner", "-loglevel", "error",
         "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", video_path],
        capture_output=True, text=True, check=True,
    )
    info = json.loads(result.stdout)
    vs = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    fmt = info["format"]

    duration = float(fmt.get("duration", 0))
    w = int(vs.get("width", 0)) if vs else 0
    h = int(vs.get("height", 0)) if vs else 0
    fps_str = vs.get("r_frame_rate", "30/1") if vs else "30/1"
    num, den = map(int, fps_str.split("/"))
    fps = round(num / den, 2) if den else 30.0

    return VideoMeta(duration=duration, resolution=f"{w}x{h}", fps=fps)


async def analyze_video_structure(
    video_path: str,
    use_frame_audit: bool | None = None,
    analysis_context: dict | None = None,
) -> VideoStructure:
    task_id = str(uuid.uuid4())[:8]

    print(f"[{task_id}] 提取视频元信息...")
    meta = get_video_meta(video_path)

    print(f"[{task_id}] 调用豆包视频理解 API...")
    doubao_result = await analyze_video_with_doubao(video_path, meta, analysis_context=analysis_context)

    print(f"[{task_id}] 整合分析结果...")
    structure = build_video_structure(task_id, meta, doubao_result)

    print(f"[{task_id}] 保存分析中间文件...")
    sample_fps = safe_float(doubao_result.get("_analysis_sample_fps"), 0.0)
    artifact_dir = save_analysis_artifacts(task_id, video_path, structure, doubao_result, sample_fps)

    if use_frame_audit is None:
        use_frame_audit = os.environ.get("ENABLE_FRAME_SPATIAL_AUDIT", "").lower() in {"1", "true", "yes"}

    if use_frame_audit:
        print(f"[{task_id}] 使用自抽帧做空间轨迹审计...")
        audit = await audit_spatial_with_frames(video_path, structure, artifact_dir)
        structure = merge_spatial_audit(structure, audit)
        (artifact_dir / "normalized_structure.json").write_text(
            structure.model_dump_json(indent=2),
            encoding="utf-8",
        )
        (artifact_dir / "spatial_summary.md").write_text(
            spatial_summary_text(structure),
            encoding="utf-8",
        )

    return structure


# ── 工具函数 ──

def s(val) -> str:
    if isinstance(val, str): return val
    if isinstance(val, list): return ", ".join(str(v) for v in val)
    return str(val) if val else ""

def sl(val) -> list:
    return val if isinstance(val, list) else ([val] if isinstance(val, str) else [])

def safe_float(val, default=0.0) -> float:
    if isinstance(val, (int, float)): return float(val)
    if isinstance(val, str):
        try: return float(val.rstrip("s").strip())
        except ValueError: return default
    return default


def build_video_structure(task_id: str, meta: VideoMeta, r: dict) -> VideoStructure:

    sections = [
        ScriptSection(
            type=s(sec.get("type", "")),
            start_time=safe_float(sec.get("start_time")),
            end_time=safe_float(sec.get("end_time")),
            text=s(sec.get("text", "")),
            purpose=s(sec.get("purpose", "")),
            hook_type=s(sec.get("hook_type", "")) or None,
        )
        for sec in r.get("sections", [])
        if isinstance(sec, dict)
    ]

    shots = [
        Shot(
            start_time=safe_float(sh.get("start_time")),
            end_time=safe_float(sh.get("end_time")),
            type=s(sh.get("type", "medium")),
            content=s(sh.get("content", "")),
            camera_move=s(sh.get("camera_move", "静止")),
            has_subtitle=bool(sh.get("has_subtitle", False)),
            visual_effect=s(sh.get("visual_effect", "无")),
            subject_distance=s(sh.get("subject_distance", "")),
            subject_position=s(sh.get("subject_position", "")),
            subject_motion=s(sh.get("subject_motion", "")),
        )
        for sh in r.get("shots", [])
        if isinstance(sh, dict)
    ]

    # 音频
    ra = r.get("audio_structure", {}) or {}
    bgm_raw = ra.get("bgm", {})
    bgm = BGMInfo(**{k: v for k, v in bgm_raw.items() if k in BGMInfo.model_fields}) if isinstance(bgm_raw, dict) else BGMInfo()
    vo_raw = ra.get("voiceover", {})
    vo = VoiceoverInfo(**{k: v for k, v in vo_raw.items() if k in VoiceoverInfo.model_fields}) if isinstance(vo_raw, dict) else VoiceoverInfo()
    sfx = [SoundEffect(time=safe_float(x.get("time")), description=s(x.get("description", "")))
           for x in ra.get("sound_effects", []) if isinstance(x, dict)]
    rhythm_raw = ra.get("rhythm_sync", "")
    rhythm = s(rhythm_raw) if not isinstance(rhythm_raw, bool) else ("是" if rhythm_raw else "否")
    note = s(ra.get("说明", ""))
    if note: rhythm = f"{rhythm}，{note}"
    audio = AudioStructure(bgm=bgm, voiceover=vo, sound_effects=sfx, rhythm_sync=rhythm)

    # 包装
    rp = r.get("packaging_structure", {}) or {}
    sub_raw = rp.get("subtitle_style", {})
    sub = SubtitleStyle(**{k: v for k, v in sub_raw.items() if k in SubtitleStyle.model_fields}) if isinstance(sub_raw, dict) else SubtitleStyle()
    trans = [Transition(time=safe_float(t.get("time")), type=s(t.get("type", "")), description=s(t.get("description", "")))
             for t in rp.get("transitions", []) if isinstance(t, dict)]
    tg = [TextGraphic(time_range=s(x.get("time_range", "")), type=s(x.get("type", "")), content=s(x.get("content", "")), style=s(x.get("style", "")))
          for x in rp.get("text_graphics", []) if isinstance(x, dict)]
    cov_raw = rp.get("cover_style", {})
    cov = CoverStyle(main_text=s(cov_raw.get("main_text", "")), subtitle_text=s(cov_raw.get("subtitle_text", "")),
                     style=s(cov_raw.get("style", "")), colors=sl(cov_raw.get("colors", [])), layout=s(cov_raw.get("layout", ""))) if isinstance(cov_raw, dict) else CoverStyle()
    packaging = PackagingStructure(subtitle_style=sub, transitions=trans, text_graphics=tg, cover_style=cov,
                                   overall_visual_tone=s(rp.get("overall_visual_tone", "")))

    # 可迁移特征
    rt = r.get("transferable_features", {}) or {}
    tf = TransferableFeatures(
        hook_strategy=s(rt.get("hook_strategy", "")),
        narrative_pattern=s(rt.get("narrative_pattern", "")),
        pacing_pattern=s(rt.get("pacing_pattern", "")),
        spatial_pattern=s(rt.get("spatial_pattern", "")),
        subject_trajectory=s(rt.get("subject_trajectory", "")),
        composition_pattern=s(rt.get("composition_pattern", "")),
        engagement_techniques=sl(rt.get("engagement_techniques", [])),
        suitable_categories=sl(rt.get("suitable_categories", [])),
    )

    return VideoStructure(id=task_id, meta=meta, script_structure=sections, shots=shots,
                          audio_structure=audio, packaging_structure=packaging,
                          transferable_features=tf, raw_response=r.get("raw_response"))


def spatial_summary_text(structure: VideoStructure) -> str:
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
