"""完整流水线 API - 一键完成分析→迁移→生成"""

import json
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse

from ..services.video_analyzer import analyze_video_structure
from ..services.transfer import transfer_structure
from ..services.video_generator import generate_transfer_video

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

BASE_DIR = Path(__file__).resolve().parent.parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"


@router.post("/run")
async def run_pipeline(
    source_video: UploadFile = File(...),
    target_video: UploadFile = File(...),
    target_description: str = Form(None),
    use_frame_audit: bool = Form(False),
):
    """一键执行完整流水线

    上传样例视频 + 目标视频 → 分析 → 迁移 → 生成视频
    """
    # 保存上传文件
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    run_id = str(uuid.uuid4())[:8]

    source_ext = Path(source_video.filename or "source.mp4").suffix or ".mp4"
    target_ext = Path(target_video.filename or "target.mp4").suffix or ".mp4"
    source_path = UPLOAD_DIR / f"{run_id}_source{source_ext}"
    target_path = UPLOAD_DIR / f"{run_id}_target{target_ext}"

    with open(source_path, "wb") as f:
        f.write(await source_video.read())
    with open(target_path, "wb") as f:
        f.write(await target_video.read())

    try:
        # Step 1: 分析样例视频
        source = await analyze_video_structure(str(source_path), use_frame_audit=use_frame_audit)

        # Step 2: 分析目标视频
        target = await analyze_video_structure(str(target_path), use_frame_audit=use_frame_audit)

        # Step 3: 构建目标描述
        if not target_description:
            target_description = f"""目标视频内容描述:
- 时长: {target.meta.duration:.1f}秒, 分辨率: {target.meta.resolution}
- 画面内容: {target.shots[0].content if target.shots else '未知'}
- 旁白/对话: {'; '.join(sec.text for sec in target.script_structure if sec.text)}
- 整体风格: {target.packaging_structure.overall_visual_tone}"""

        # Step 4: 执行迁移
        transfer_result = await transfer_structure(
            source_structure=source,
            target_description=target_description,
            target_meta={"duration": target.meta.duration, "resolution": target.meta.resolution},
            target_structure=target,
        )

        # 保存迁移结果
        transfer_dir = OUTPUT_DIR / "transfer"
        os.makedirs(transfer_dir, exist_ok=True)
        transfer_file = transfer_dir / f"transfer_{run_id}.json"
        with open(transfer_file, "w", encoding="utf-8") as f:
            json.dump(transfer_result, f, ensure_ascii=False, indent=2)

        # Step 5: 生成视频（混入样例 BGM）
        video_dir = OUTPUT_DIR / "videos"
        os.makedirs(video_dir, exist_ok=True)
        video_path = str(video_dir / f"video_{run_id}.mp4")

        generate_transfer_video(
            transfer_result_path=str(transfer_file),
            target_video_path=str(target_path),
            output_path=video_path,
            use_ai_image=True,
            source_video_path=str(source_path),
        )

        size_mb = os.path.getsize(video_path) / 1024 / 1024

        return JSONResponse({
            "status": "success",
            "run_id": run_id,
            "source_meta": {
                "duration": source.meta.duration,
                "resolution": source.meta.resolution,
                "script_count": len(source.script_structure),
            },
            "target_meta": {
                "duration": target.meta.duration,
                "resolution": target.meta.resolution,
            },
            "transfer": transfer_result,
            "video": {
                "path": video_path,
                "size_mb": round(size_mb, 2),
            },
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"流水线执行失败: {str(e)}")
