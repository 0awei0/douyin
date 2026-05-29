from __future__ import annotations
from pydantic import BaseModel
from typing import Optional


# ── 脚本段落 ──
class ScriptSection(BaseModel):
    type: str  # hook / pain / solution / demo / proof / cta
    start_time: float
    end_time: float
    text: str
    purpose: str
    hook_type: Optional[str] = None  # 仅 hook 段：提问式/悬念式/冲突式/利益式/共鸣式


# ── 镜头 ──
class Shot(BaseModel):
    start_time: float
    end_time: float
    type: str  # close-up / medium / wide / text-overlay / screen-record / transition
    content: str
    camera_move: str = "静止"
    has_subtitle: bool = False
    visual_effect: str = "无"


# ── BGM ──
class BGMInfo(BaseModel):
    name: str = ""
    mood: str = ""  # 欢快/紧张/温馨/燃/伤感
    bpm_range: str = ""  # 快/中/慢


# ── 旁白 ──
class VoiceoverInfo(BaseModel):
    has: bool = False
    style: str = ""  # 甜美/磁性/搞笑/专业/童声
    language: str = ""


# ── 音效 ──
class SoundEffect(BaseModel):
    time: float
    description: str


# ── 音频结构 ──
class AudioStructure(BaseModel):
    bgm: BGMInfo = BGMInfo()
    voiceover: VoiceoverInfo = VoiceoverInfo()
    sound_effects: list[SoundEffect] = []
    rhythm_sync: str = ""  # 是否卡节拍 + 说明


# ── 字幕样式 ──
class SubtitleStyle(BaseModel):
    font_size: str = ""
    color: str = ""
    position: str = ""
    animation: str = ""
    outline: str = ""


# ── 转场 ──
class Transition(BaseModel):
    time: float
    type: str
    description: str


# ── 文字图形 ──
class TextGraphic(BaseModel):
    time_range: str = ""
    type: str = ""  # 标题条/卖点卡/弹幕/标签
    content: str = ""
    style: str = ""


# ── 封面风格 ──
class CoverStyle(BaseModel):
    main_text: str = ""
    subtitle_text: str = ""
    style: str = ""
    colors: list[str] = []
    layout: str = ""


# ── 包装结构 ──
class PackagingStructure(BaseModel):
    subtitle_style: SubtitleStyle = SubtitleStyle()
    transitions: list[Transition] = []
    text_graphics: list[TextGraphic] = []
    cover_style: CoverStyle = CoverStyle()
    overall_visual_tone: str = ""


# ── 可迁移特征 ──
class TransferableFeatures(BaseModel):
    hook_strategy: str = ""
    narrative_pattern: str = ""
    pacing_pattern: str = ""
    engagement_techniques: list[str] = []
    suitable_categories: list[str] = []


# ── 视频元信息 ──
class VideoMeta(BaseModel):
    duration: float
    resolution: str
    fps: float
    cover_frame: Optional[str] = None


# ── 完整视频结构 ──
class VideoStructure(BaseModel):
    id: str
    meta: VideoMeta
    script_structure: list[ScriptSection] = []
    shots: list[Shot] = []
    audio_structure: AudioStructure = AudioStructure()
    packaging_structure: PackagingStructure = PackagingStructure()
    transferable_features: TransferableFeatures = TransferableFeatures()
    raw_response: Optional[str] = None


# ── 分析请求/响应 ──
class AnalyzeRequest(BaseModel):
    video_path: str


class AnalyzeResponse(BaseModel):
    task_id: str
    status: str
    structure: Optional[VideoStructure] = None
    error: Optional[str] = None
