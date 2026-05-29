"""SeedDream 图片生成服务

使用豆包 SeedDream API 生成图片素材。
"""

import subprocess
import tempfile
from pathlib import Path

from volcenginesdkarkruntime import Ark

from ..core.config import get_settings


def generate_cta_image(
    text: str,
    output_path: str,
    size: str = "720x1280",
) -> str:
    """生成 CTA 引导页图片

    Args:
        text: 引导文字
        output_path: 输出图片路径
        size: 图片尺寸

    Returns:
        输出图片路径
    """
    settings = get_settings()
    client = Ark(base_url=settings.ARK_BASE_URL, api_key=settings.ARK_API_KEY)

    prompt = (
        f"设计一个抖音短视频结尾的挑战引导页面。"
        f"背景：浅蓝色到深蓝色的渐变，清新时尚。"
        f"中央有白色圆角搜索框，搜索框内显示文字「{text}」。"
        f"搜索框下方有「快来参与同款挑战」的引导文字。"
        f"整体风格：简洁、清新、有抖音品牌感。"
        f"适合竖屏 9:16 比例。"
    )

    response = client.images.generate(
        model="doubao-seedream-5-0-260128",
        prompt=prompt,
        sequential_image_generation="disabled",
        response_format="url",
        size="720x1280",
        stream=False,
        watermark=False,
    )

    # 下载图片
    url = response.data[0].url
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        ["curl", "-sL", "-o", output_path, url],
        check=True,
    )

    return output_path


def generate_hook_image(
    description: str,
    output_path: str,
) -> str:
    """生成 Hook 画面图片（用于缺素材时的占位）

    Args:
        description: 画面描述
        output_path: 输出图片路径

    Returns:
        输出图片路径
    """
    settings = get_settings()
    client = Ark(base_url=settings.ARK_BASE_URL, api_key=settings.ARK_API_KEY)

    prompt = (
        f"短视频画面截图，{description}。"
        f"手机竖屏拍摄，自然光线，生活化场景。"
        f"画面清晰、有吸引力，适合作为短视频开头画面。"
    )

    response = client.images.generate(
        model="doubao-seedream-5-0-260128",
        prompt=prompt,
        sequential_image_generation="disabled",
        response_format="url",
        size="720x1280",
        stream=False,
        watermark=False,
    )

    url = response.data[0].url
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        ["curl", "-sL", "-o", output_path, url],
        check=True,
    )

    return output_path
