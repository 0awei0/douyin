"""结构迁移 API 路由"""

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ..models.video_structure import VideoStructure
from ..services.transfer import transfer_structure
from ..services.video_analyzer import analyze_video_structure

router = APIRouter(prefix="/api/transfer", tags=["transfer"])

BASE_DIR = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = BASE_DIR / "outputs" / "transfer"


@router.post("/")
async def run_transfer(
    source_video_path: str,
    target_video_path: str,
    target_description: str | None = None,
    use_frame_audit: bool = True,
):
    """执行结构迁移

    Args:
        source_video_path: 样例视频路径
        target_video_path: 目标视频路径
        target_description: 目标内容描述（可选，不填则自动从目标视频提取）
    """
    if not os.path.exists(source_video_path):
        raise HTTPException(status_code=404, detail=f"样例视频不存在: {source_video_path}")
    if not os.path.exists(target_video_path):
        raise HTTPException(status_code=404, detail=f"目标视频不存在: {target_video_path}")

    try:
        # 1. 分析样例视频
        source = await analyze_video_structure(source_video_path, use_frame_audit=use_frame_audit)

        # 2. 分析目标视频
        target = await analyze_video_structure(target_video_path, use_frame_audit=use_frame_audit)

        # 3. 构建目标描述
        if not target_description:
            target_description = f"""目标视频内容描述:
- 时长: {target.meta.duration:.1f}秒, 分辨率: {target.meta.resolution}
- 画面内容: {target.shots[0].content if target.shots else '未知'}
- 旁白/对话: {'; '.join(sec.text for sec in target.script_structure if sec.text)}
- 整体风格: {target.packaging_structure.overall_visual_tone}"""

        # 4. 执行迁移
        result = await transfer_structure(
            source_structure=source,
            target_description=target_description,
            target_meta={"duration": target.meta.duration, "resolution": target.meta.resolution},
            target_structure=target,
        )

        # 5. 保存结果
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        import uuid
        transfer_id = str(uuid.uuid4())[:8]
        out_file = OUTPUT_DIR / f"transfer_{transfer_id}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        return JSONResponse({
            "status": "success",
            "transfer_id": transfer_id,
            "result_path": str(out_file),
            "result": result,
            "source_meta": {
                "duration": source.meta.duration,
                "resolution": source.meta.resolution,
                "script_count": len(source.script_structure),
                "shot_count": len(source.shots),
            },
            "target_meta": {
                "duration": target.meta.duration,
                "resolution": target.meta.resolution,
            },
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"迁移失败: {str(e)}")


@router.get("/{transfer_id}")
async def get_transfer(transfer_id: str):
    """获取迁移结果"""
    out_file = OUTPUT_DIR / f"transfer_{transfer_id}.json"
    if not out_file.exists():
        raise HTTPException(status_code=404, detail="迁移结果不存在")

    with open(out_file, "r", encoding="utf-8") as f:
        result = json.load(f)

    return JSONResponse({
        "status": "success",
        "transfer_id": transfer_id,
        "result": result,
    })
