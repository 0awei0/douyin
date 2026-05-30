"""豆包 API 客户端

使用火山方舟 SDK 调用 Doubao-Seed-2.0-lite 的视频理解能力。
"""

import base64
import json
import os
from pathlib import Path

from volcenginesdkarkruntime import Ark

from ..core.config import get_settings
from ..models.video_structure import VideoMeta

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "prompts"

KEY_MAP = {
    # 视频分析
    "脚本结构": "sections",
    "节奏结构": "shots",
    "音频结构": "audio_structure",
    "包装结构": "packaging_structure",
    "可迁移特征": "transferable_features",
    "script_structure": "sections",
    "rhythm_structure": "shots",
    # 结构迁移
    "新脚本 (script)": "script",
    "新分镜 (storyboard)": "storyboard",
    "包装方案 (packaging)": "packaging",
    "素材需求 (material_needs)": "material_needs",
    "新脚本": "script",
    "新分镜": "storyboard",
    "包装方案": "packaging",
    "素材需求": "material_needs",
}


def load_prompt(name: str) -> str:
    """从 prompts 目录加载 md 文件"""
    path = PROMPTS_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8")


def get_ark_client() -> Ark:
    settings = get_settings()
    return Ark(base_url=settings.ARK_BASE_URL, api_key=settings.ARK_API_KEY)


def encode_video_base64(video_path: str) -> str:
    with open(video_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


async def analyze_video_with_doubao(
    video_path: str,
    meta: VideoMeta,
    analysis_context: dict | None = None,
) -> dict:
    """调用豆包视频理解 API 分析视频"""
    settings = get_settings()
    client = get_ark_client()

    system_prompt = load_prompt("video_analysis")
    video_data = encode_video_base64(video_path)

    fps = choose_analysis_fps(meta)

    user_text = f"""请分析这个短视频的结构。

视频信息：
- 时长: {meta.duration:.1f}秒
- 分辨率: {meta.resolution}
- 帧率: {meta.fps}fps
- 抽帧率: {fps}fps（共约 {int(meta.duration * fps)} 帧）

分析要求：
1. 仔细观察每个时间段的画面变化，特别是人物位置、景别、动作的变化
2. 如果视频有空间渐进（如从近到远、从局部到全景、主体从前景退到远景/退出画面），要拆分成多个镜头
3. 单独判断 subject_distance / subject_position / subject_motion；不要把"远离镜头"误写成普通剧情动作
4. transferable_features 里必须总结 spatial_pattern、subject_trajectory、composition_pattern
5. 输出 spatial_keyframes 数组：逐项说明关键时间点、主体画面占比、主体位置、空间角色（near/mid/far/tiny/environment/cta）
6. 如果人物远到很小，也必须记录为 tiny/far，不要忽略为普通环境
7. 每个镜头的时长建议 2-6 秒，不要把明显不同的画面合并成一个长镜头"""

    if analysis_context:
        user_text += f"""

用户补充的创作意图/观察提示（必须优先参考，尤其是亮点、不要强调的误判方向和迁移优先级）：
{json.dumps(analysis_context, ensure_ascii=False, indent=2)}"""

    response = client.chat.completions.create(
        model=settings.ARK_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "video_url",
                        "video_url": {
                            "url": f"data:video/mp4;base64,{video_data}",
                            "fps": fps,
                        },
                    },
                    {"type": "text", "text": user_text},
                ],
            },
        ],
        temperature=0.3,
    )

    content = response.choices[0].message.content
    result = parse_doubao_response(content)
    result["_analysis_sample_fps"] = fps
    if not result.get("sections") and not result.get("shots"):
        result["raw_response"] = content
    return result


def choose_analysis_fps(meta: VideoMeta) -> float:
    """Choose a denser sampling rate for short videos and spatial movement."""
    override = os.environ.get("VIDEO_ANALYSIS_FPS")
    if override:
        try:
            return max(0.2, min(5.0, float(override)))
        except ValueError:
            pass

    # Short viral videos often hinge on subtle body-size changes. Use denser
    # sampling there; cap longer videos to keep request size predictable.
    if meta.duration <= 25:
        return 4.0
    if meta.duration <= 70:
        return 3.0
    return max(1.0, min(3.0, 180.0 / max(meta.duration, 1.0)))


def parse_doubao_response(content: str) -> dict:
    """解析豆包返回的 JSON，兼容中英文 key"""
    if "```json" in content:
        json_str = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        json_str = content.split("```")[1].split("```")[0].strip()
    else:
        json_str = content.strip()

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return {"sections": [], "shots": [], "audio_structure": {},
                "packaging_structure": {}, "transferable_features": {},
                "raw_response": content}

    return {KEY_MAP.get(k, k): v for k, v in data.items()}
