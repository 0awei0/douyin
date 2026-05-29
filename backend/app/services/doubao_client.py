"""豆包 API 客户端

使用火山方舟 SDK 调用 Doubao-Seed-2.0-lite 的视频理解能力。
支持直接传入本地视频文件进行分析。
"""

import base64
import json
from pathlib import Path

from volcenginesdkarkruntime import Ark

from ..core.config import get_settings
from ..models.video_structure import VideoMeta

SYSTEM_PROMPT = """你是一个专业的短视频结构分析师。你的任务是深度拆解视频的"创作方法论"，输出结果将直接用于结构迁移——即把样例视频的套路搬到新内容上。

分析维度：

**1. 脚本结构 (sections)**：逐段拆解视频的叙事逻辑
   - type: hook(开头吸睛) / pain(痛点/问题) / solution(解决方案) / demo(演示展示) / proof(背书/证据) / cta(行动号召)
   - start_time, end_time: 精确到秒，必须覆盖视频全部时长，不要遗漏尾部
   - text: 该段的语音/字幕原文（逐字，不要概括）
   - purpose: 该段在"说服链"中的作用（20字以内）
   - hook_type: 仅 hook 段需要，说明开头手法类型（如：提问式/悬念式/冲突式/利益式/共鸣式）

**2. 节奏结构 (shots)**：逐镜头拆解画面编排
   - start_time, end_time: 精确到秒，覆盖全部时长
   - type: close-up(特写) / medium(中景) / wide(全景) / text-overlay(纯文字画面) / screen-record(录屏) / transition(过渡)
   - content: 画面内容的详细描述（主体、动作、背景、光线、构图）
   - camera_move: 镜头运动（静止/推/拉/摇/移/跟/升降/手持晃动）
   - has_subtitle: 是否有字幕叠加
   - visual_effect: 视觉特效（滤镜、调色、速度变化、分屏等，无则填"无"）

**3. 音频结构 (audio)**：拆解音频节奏
   - bgm: {name: 曲名或风格描述, mood: 情绪(欢快/紧张/温馨/燃/伤感), bpm_range: "快/中/慢"}
   - voiceover: {has: 是否有旁白, style: 风格(甜美/磁性/搞笑/专业/童声), language: 语言}
   - sound_effects: 关键音效列表 [{time, description}]
   - rhythm_sync: 镜头切换是否卡BGM节拍(true/false), 说明

**4. 包装结构 (packaging)**：字幕、转场、视觉风格
   - subtitle_style: {font_size: "大/中/小", color: 颜色, position: 位置, animation: 动画效果, outline: 描边样式}
   - transitions: [{time, type: "硬切/淡入淡出/缩放/滑动/遮罩", description}]
   - text_graphics: 文字图形元素 [{time_range, type: "标题条/卖点卡/弹幕/标签", content, style}]
   - cover_style: {main_text, subtitle_text, style: 风格关键词, colors: [主色调], layout: 布局描述}
   - overall_visual_tone: 整体视觉调性（明亮清新/暗黑高级/复古温暖/赛博朋克等，20字以内）

**5. 可迁移特征 (transferable_features)**：提炼出可直接复用的创作方法
   - hook_strategy: 开头策略总结（30字以内）
   - narrative_pattern: 叙事模式（如"痛点→方案→证明→行动"）
   - pacing_pattern: 节奏模式（如"快开场→慢展示→快收尾"）
   - engagement_techniques: 吸引力技巧列表（如["反转","悬念","拟人","对比"]）
   - suitable_categories: 适合迁移的内容类别（如["宠物","搞笑","生活"]）

严格返回 JSON，不要有多余文字。所有字段都必须填写，不要用 null。如果某项确实不存在，填空字符串""或空列表[]。"""


def get_ark_client() -> Ark:
    settings = get_settings()
    return Ark(api_key=settings.ARK_API_KEY)


def encode_video_base64(video_path: str) -> str:
    """将本地视频编码为 base64"""
    with open(video_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


async def analyze_video_with_doubao(
    video_path: str,
    meta: VideoMeta,
    scene_changes: list[dict],
) -> dict:
    """调用豆包视频理解 API 分析视频

    Args:
        video_path: 本地视频文件路径
        meta: FFmpeg 提取的视频元信息
        scene_changes: FFmpeg 检测到的场景切换点

    Returns:
        结构化的分析结果 dict
    """
    settings = get_settings()
    client = get_ark_client()

    # 构建补充信息
    scene_info = ""
    if scene_changes:
        scene_times = [f"{s['time']:.1f}s" for s in scene_changes[:20]]
        scene_info = f"\n\nFFmpeg 检测到的场景切换时间点: {', '.join(scene_times)}"

    meta_info = f"""
视频元信息（FFmpeg 提取）:
- 时长: {meta.duration:.1f}秒
- 分辨率: {meta.resolution}
- 帧率: {meta.fps}fps{scene_info}"""

    # 读取视频文件并编码
    video_data = encode_video_base64(video_path)

    # 调用 API - 使用 video_url 类型传入 base64 视频
    response = client.chat.completions.create(
        model=settings.ARK_ENDPOINT,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "video_url",
                        "video_url": {
                            "url": f"data:video/mp4;base64,{video_data}",
                            "fps": 1.0,
                        },
                    },
                    {
                        "type": "text",
                        "text": f"请分析这个短视频的结构。{meta_info}",
                    },
                ],
            },
        ],
        temperature=0.3,
    )

    # 解析响应
    content = response.choices[0].message.content
    result = parse_doubao_response(content)
    # 保存原始响应用于调试
    if not result.get("sections") and not result.get("shots"):
        result["raw_response"] = content
    return result


KEY_MAP = {
    "脚本结构": "sections",
    "节奏结构": "shots",
    "音频结构": "audio_structure",
    "包装结构": "packaging_structure",
    "可迁移特征": "transferable_features",
    # 有时 API 返回英文 key 但名称不同
    "script_structure": "sections",
    "rhythm_structure": "shots",
}


def parse_doubao_response(content: str) -> dict:
    """解析豆包返回的 JSON 结果，兼容中英文 key"""
    if "```json" in content:
        json_str = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        json_str = content.split("```")[1].split("```")[0].strip()
    else:
        json_str = content.strip()

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return {"sections": [], "shots": [], "audio_structure": {}, "packaging_structure": {}, "transferable_features": {}, "raw_response": content}

    # 中文 key → 英文 key
    result = {}
    for k, v in data.items():
        mapped = KEY_MAP.get(k, k)
        result[mapped] = v

    return result
