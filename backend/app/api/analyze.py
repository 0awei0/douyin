"""视频分析 API 路由"""

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

from ..models.video_structure import AnalyzeResponse
from ..services.video_analyzer import analyze_video_structure

router = APIRouter(prefix="/api/analyze", tags=["analyze"])

BASE_DIR = Path(__file__).resolve().parent.parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"


@router.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    """上传视频文件"""
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="请上传视频文件")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_id = str(uuid.uuid4())[:8]
    ext = Path(file.filename or "video.mp4").suffix or ".mp4"
    save_path = UPLOAD_DIR / f"{file_id}{ext}"

    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    return JSONResponse({
        "file_id": file_id,
        "filename": file.filename,
        "path": str(save_path),
        "size": len(content),
    })


@router.post("/structure")
async def analyze_structure(video_path: str):
    """分析视频结构

    Args:
        video_path: 服务器上的视频文件路径
    """
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="视频文件不存在")

    try:
        structure = await analyze_video_structure(video_path)
        return JSONResponse({
            "status": "success",
            "structure": structure.model_dump(),
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")
