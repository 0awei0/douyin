"""视频结构分析服务

流程:
1. FFmpeg 提取技术信息（时长、分辨率、帧率、场景切换、关键帧、音频）
2. 豆包视频理解 API 做语义分析（内容描述、结构判断）
3. 整合输出 VideoStructure
"""

import json
import os
import subprocess
import uuid
from pathlib import Path

from ..models.video_structure import (
    VideoStructure,
    VideoMeta,
    ScriptSection,
    Shot,
    AudioStructure,
    BGMInfo,
    VoiceoverInfo,
    SoundEffect,
    PackagingStructure,
    SubtitleStyle,
    Transition,
    TextGraphic,
    CoverStyle,
    TransferableFeatures,
)
from .doubao_client import analyze_video_with_doubao

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def run_ffmpeg(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"] + args
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def run_ffprobe(args: list[str]) -> subprocess.CompletedProcess:
    cmd = ["ffprobe", "-hide_banner", "-loglevel", "error"] + args
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


def get_video_meta(video_path: str) -> VideoMeta:
    result = run_ffprobe([
        "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", video_path,
    ])
    info = json.loads(result.stdout)
    video_stream = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    fmt = info["format"]

    duration = float(fmt.get("duration", 0))
    width = int(video_stream.get("width", 0)) if video_stream else 0
    height = int(video_stream.get("height", 0)) if video_stream else 0
    fps_str = video_stream.get("r_frame_rate", "30/1") if video_stream else "30/1"
    num, den = map(int, fps_str.split("/"))
    fps = round(num / den, 2) if den else 30.0

    return VideoMeta(duration=duration, resolution=f"{width}x{height}", fps=fps)


def detect_scene_changes(video_path: str, threshold: float = 0.3) -> list[dict]:
    result = run_ffmpeg([
        "-i", video_path,
        "-filter_complex", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null", "-"
    ], check=False)
    scenes = []
    for line in result.stderr.split("\n"):
        if "showinfo" in line and "pts_time:" in line:
            try:
                pts = float(line.split("pts_time:")[1].split()[0])
                scenes.append({"time": pts})
            except (IndexError, ValueError):
                continue
    return scenes


def extract_keyframes(video_path: str, output_dir: str, max_frames: int = 10) -> list[str]:
    os.makedirs(output_dir, exist_ok=True)
    meta = get_video_meta(video_path)
    if meta.duration <= 0:
        return []
    interval = max(meta.duration / max_frames, 1.0)
    frames = []
    for i in range(max_frames):
        t = i * interval
        if t >= meta.duration:
            break
        output_path = os.path.join(output_dir, f"frame_{i:03d}.jpg")
        run_ffmpeg(["-ss", str(t), "-i", video_path, "-frames:v", "1", "-q:v", "2", output_path], check=False)
        if os.path.exists(output_path):
            frames.append(output_path)
    return frames


def extract_audio(video_path: str, output_path: str) -> str | None:
    run_ffmpeg(["-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", output_path], check=False)
    return output_path if os.path.exists(output_path) else None


async def analyze_video_structure(video_path: str) -> VideoStructure:
    task_id = str(uuid.uuid4())[:8]
    output_dir = BASE_DIR / "outputs" / task_id
    os.makedirs(output_dir, exist_ok=True)

    print(f"[{task_id}] Step 1: 提取视频元信息...")
    meta = get_video_meta(video_path)

    print(f"[{task_id}] Step 2: 检测场景切换...")
    scenes = detect_scene_changes(video_path)

    print(f"[{task_id}] Step 3: 提取关键帧...")
    extract_keyframes(video_path, str(output_dir / "frames"), max_frames=10)

    print(f"[{task_id}] Step 4: 提取音频...")
    audio_path = str(output_dir / "audio.wav")
    extract_audio(video_path, audio_path)

    print(f"[{task_id}] Step 5: 调用豆包视频理解 API...")
    doubao_result = await analyze_video_with_doubao(
        video_path=video_path, meta=meta, scene_changes=scenes,
    )

    print(f"[{task_id}] Step 6: 整合分析结果...")
    structure = build_video_structure(task_id=task_id, meta=meta, doubao_result=doubao_result)
    return structure


# ── 工具函数 ──

def s(val) -> str:
    """安全转字符串"""
    if isinstance(val, str):
        return val
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
    return str(val) if val else ""


def sl(val) -> list:
    """安全转列表"""
    return val if isinstance(val, list) else ([val] if isinstance(val, str) else [])


def safe_float(val, default=0.0) -> float:
    """安全转 float，兼容 '2.8s' 这种格式"""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val.rstrip("s").strip())
        except ValueError:
            return default
    return default


def extract_dict(val, model_cls):
    """从 dict 中提取模型字段，忽略多余字段"""
    if not isinstance(val, dict):
        return {}
    return {k: v for k, v in val.items() if k in model_cls.model_fields}


def build_video_structure(
    task_id: str,
    meta: VideoMeta,
    doubao_result: dict,
) -> VideoStructure:

    # ── 脚本结构 ──
    sections = []
    for sec in doubao_result.get("sections", []):
        if not isinstance(sec, dict):
            continue
        sections.append(ScriptSection(
            type=s(sec.get("type", "")),
            start_time=safe_float(sec.get("start_time", 0)),
            end_time=safe_float(sec.get("end_time", 0)),
            text=s(sec.get("text", "")),
            purpose=s(sec.get("purpose", "")),
            hook_type=s(sec.get("hook_type", "")) or None,
        ))

    # ── 镜头 ──
    shots = []
    for sh in doubao_result.get("shots", []):
        if not isinstance(sh, dict):
            continue
        shots.append(Shot(
            start_time=safe_float(sh.get("start_time", 0)),
            end_time=safe_float(sh.get("end_time", 0)),
            type=s(sh.get("type", "medium")),
            content=s(sh.get("content", "")),
            camera_move=s(sh.get("camera_move", "静止")),
            has_subtitle=bool(sh.get("has_subtitle", False)),
            visual_effect=s(sh.get("visual_effect", "无")),
        ))

    # ── 音频结构 ──
    raw_audio = doubao_result.get("audio_structure", {})
    if not isinstance(raw_audio, dict):
        raw_audio = {}

    bgm_raw = raw_audio.get("bgm", {})
    bgm = BGMInfo(**extract_dict(bgm_raw, BGMInfo)) if isinstance(bgm_raw, dict) else BGMInfo()

    vo_raw = raw_audio.get("voiceover", {})
    voiceover = VoiceoverInfo(**extract_dict(vo_raw, VoiceoverInfo)) if isinstance(vo_raw, dict) else VoiceoverInfo()

    sfx_list = []
    for sfx in raw_audio.get("sound_effects", []):
        if isinstance(sfx, dict):
            sfx_list.append(SoundEffect(time=safe_float(sfx.get("time", 0)), description=s(sfx.get("description", ""))))

    rhythm_sync_raw = raw_audio.get("rhythm_sync", "")
    rhythm_sync = s(rhythm_sync_raw) if not isinstance(rhythm_sync_raw, bool) else ("是" if rhythm_sync_raw else "否")
    # 附加说明字段
    rhythm_note = s(raw_audio.get("说明", ""))
    if rhythm_note:
        rhythm_sync = f"{rhythm_sync}，{rhythm_note}"

    audio = AudioStructure(
        bgm=bgm,
        voiceover=voiceover,
        sound_effects=sfx_list,
        rhythm_sync=rhythm_sync,
    )

    # ── 包装结构 ──
    raw_pkg = doubao_result.get("packaging_structure", {})
    if not isinstance(raw_pkg, dict):
        raw_pkg = {}

    sub_raw = raw_pkg.get("subtitle_style", {})
    subtitle_style = SubtitleStyle(**extract_dict(sub_raw, SubtitleStyle)) if isinstance(sub_raw, dict) else SubtitleStyle()

    transitions = []
    for t in raw_pkg.get("transitions", []):
        if isinstance(t, dict):
            transitions.append(Transition(
                time=safe_float(t.get("time", 0)),
                type=s(t.get("type", "")),
                description=s(t.get("description", "")),
            ))

    text_graphics = []
    for tg in raw_pkg.get("text_graphics", []):
        if isinstance(tg, dict):
            text_graphics.append(TextGraphic(
                time_range=s(tg.get("time_range", "")),
                type=s(tg.get("type", "")),
                content=s(tg.get("content", "")),
                style=s(tg.get("style", "")),
            ))

    cover_raw = raw_pkg.get("cover_style", {})
    cover_style = CoverStyle(
        main_text=s(cover_raw.get("main_text", "")),
        subtitle_text=s(cover_raw.get("subtitle_text", "")),
        style=s(cover_raw.get("style", "")),
        colors=sl(cover_raw.get("colors", [])),
        layout=s(cover_raw.get("layout", "")),
    ) if isinstance(cover_raw, dict) else CoverStyle()

    packaging = PackagingStructure(
        subtitle_style=subtitle_style,
        transitions=transitions,
        text_graphics=text_graphics,
        cover_style=cover_style,
        overall_visual_tone=s(raw_pkg.get("overall_visual_tone", "")),
    )

    # ── 可迁移特征 ──
    raw_tf = doubao_result.get("transferable_features", {})
    if not isinstance(raw_tf, dict):
        raw_tf = {}
    transferable = TransferableFeatures(
        hook_strategy=s(raw_tf.get("hook_strategy", "")),
        narrative_pattern=s(raw_tf.get("narrative_pattern", "")),
        pacing_pattern=s(raw_tf.get("pacing_pattern", "")),
        engagement_techniques=sl(raw_tf.get("engagement_techniques", [])),
        suitable_categories=sl(raw_tf.get("suitable_categories", [])),
    )

    return VideoStructure(
        id=task_id,
        meta=meta,
        script_structure=sections,
        shots=shots,
        audio_structure=audio,
        packaging_structure=packaging,
        transferable_features=transferable,
        raw_response=doubao_result.get("raw_response"),
    )
