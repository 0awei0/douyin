"""视频生成 API 路由"""

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ..services.video_generator import generate_transfer_video

router = APIRouter(prefix="/api/generate", tags=["generate"])

BASE_DIR = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = BASE_DIR / "outputs" / "videos"


@router.post("/")
async def generate_video(
    transfer_id: str,
    target_video_path: str,
    use_ai_image: bool = True,
    source_video_path: str | None = None,
):
    """基于迁移结果生成视频

    Args:
        transfer_id: 迁移结果 ID
        target_video_path: 目标视频路径
        use_ai_image: 是否使用 AI 生成 CTA 图片
        source_video_path: 样例视频路径（用于提取 BGM 混入）
    """
    transfer_json = BASE_DIR / "outputs" / "transfer" / f"transfer_{transfer_id}.json"
    if not transfer_json.exists():
        raise HTTPException(status_code=404, detail=f"迁移结果不存在: {transfer_id}")
    if not os.path.exists(target_video_path):
        raise HTTPException(status_code=404, detail=f"目标视频不存在: {target_video_path}")

    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        video_id = str(uuid.uuid4())[:8]
        output_path = str(OUTPUT_DIR / f"video_{video_id}.mp4")

        generate_transfer_video(
            transfer_result_path=str(transfer_json),
            target_video_path=target_video_path,
            output_path=output_path,
            use_ai_image=use_ai_image,
            source_video_path=source_video_path,
        )

        size_mb = os.path.getsize(output_path) / 1024 / 1024

        return JSONResponse({
            "status": "success",
            "video_id": video_id,
            "video_path": output_path,
            "size_mb": round(size_mb, 2),
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"视频生成失败: {str(e)}")


@router.get("/{video_id}")
async def get_video(video_id: str):
    """获取生成的视频信息"""
    video_path = OUTPUT_DIR / f"video_{video_id}.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="视频不存在")

    size_mb = video_path.stat().st_size / 1024 / 1024

    return JSONResponse({
        "status": "success",
        "video_id": video_id,
        "video_path": str(video_path),
        "size_mb": round(size_mb, 2),
    })
