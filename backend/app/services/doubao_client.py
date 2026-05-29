"""豆包 API 客户端

使用火山方舟 SDK 调用 Doubao-Seed-2.0-lite 的视频理解能力。
"""

import base64
import json
from pathlib import Path

from volcenginesdkarkruntime import Ark

from ..core.config import get_settings
from ..models.video_structure import VideoMeta

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "prompts"

KEY_MAP = {
    "脚本结构": "sections",
    "节奏结构": "shots",
    "音频结构": "audio_structure",
    "包装结构": "packaging_structure",
    "可迁移特征": "transferable_features",
    "script_structure": "sections",
    "rhythm_structure": "shots",
}


def load_prompt(name: str) -> str:
    """从 prompts 目录加载 md 文件"""
    path = PROMPTS_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8")


def get_ark_client() -> Ark:
    settings = get_settings()
    return Ark(api_key=settings.ARK_API_KEY)


def encode_video_base64(video_path: str) -> str:
    with open(video_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


async def analyze_video_with_doubao(
    video_path: str,
    meta: VideoMeta,
) -> dict:
    """调用豆包视频理解 API 分析视频"""
    settings = get_settings()
    client = get_ark_client()

    system_prompt = load_prompt("video_analysis")
    video_data = encode_video_base64(video_path)

    user_text = f"请分析这个短视频的结构。\n视频时长: {meta.duration:.1f}秒, 分辨率: {meta.resolution}, 帧率: {meta.fps}fps"

    response = client.chat.completions.create(
        model=settings.ARK_ENDPOINT,
        messages=[
            {"role": "system", "content": system_prompt},
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
                    {"type": "text", "text": user_text},
                ],
            },
        ],
        temperature=0.3,
    )

    content = response.choices[0].message.content
    result = parse_doubao_response(content)
    if not result.get("sections") and not result.get("shots"):
        result["raw_response"] = content
    return result


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
