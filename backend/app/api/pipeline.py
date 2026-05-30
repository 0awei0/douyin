"""完整流水线 API - 一键完成分析→迁移→生成"""

from __future__ import annotations

import json
import os
import uuid
import asyncio
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from ..models.video_structure import VideoStructure
from ..services.video_analyzer import analyze_video_structure
from ..services.transfer import transfer_structure
from ..services.video_generator import generate_transfer_video

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

BASE_DIR = Path(__file__).resolve().parent.parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
VIDEO_OUTPUT_DIR = OUTPUT_DIR / "videos"


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
    try:
        result = await _execute_pipeline(
            source_video=source_video,
            target_video=target_video,
            target_description=target_description,
            use_frame_audit=use_frame_audit,
        )
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"流水线执行失败: {str(e)}")


@router.post("/run/stream")
async def run_pipeline_stream(
    source_video: UploadFile = File(...),
    target_video: UploadFile = File(...),
    target_description: str = Form(None),
    use_frame_audit: bool = Form(False),
):
    """流式执行完整流水线，逐步返回分析和迁移进度。"""

    async def events() -> AsyncIterator[str]:
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        async def on_event(event: dict[str, Any]) -> None:
            await queue.put(event)

        async def runner() -> None:
            try:
                result = await _execute_pipeline(
                    source_video=source_video,
                    target_video=target_video,
                    target_description=target_description,
                    use_frame_audit=use_frame_audit,
                    on_event=on_event,
                )
                await queue.put(_result_event(result))
            except Exception as e:
                await queue.put({
                    "type": "error",
                    "step": "error",
                    "status": "error",
                    "title": "执行失败",
                    "message": str(e),
                })
            finally:
                await queue.put(None)

        task = asyncio.create_task(runner())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield _json_line(event)
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _execute_pipeline(
    source_video: UploadFile,
    target_video: UploadFile,
    target_description: str | None,
    use_frame_audit: bool,
    on_event: Callable[[dict[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    await _emit(on_event, _progress("upload", "running", "正在上传并保存视频", "保存样例视频和目标素材到本地工作区。"))
    run_id, source_path, target_path = await _save_uploads(source_video, target_video)
    await _emit(
        on_event,
        _progress(
            "upload",
            "done",
            "上传完成",
            "视频已保存，开始进入爆款结构分析。",
            {
                "run_id": run_id,
                "source_file": source_video.filename,
                "target_file": target_video.filename,
                "source_size_mb": _file_size_mb(source_path),
                "target_size_mb": _file_size_mb(target_path),
            },
        ),
    )

    await _emit(on_event, _progress("source_analysis", "running", "正在分析样例视频结构", "提取 hook、节奏、空间轨迹和包装方式。"))
    source = await _analyze_video_structure(str(source_path), use_frame_audit=use_frame_audit)
    await _emit(
        on_event,
        _progress(
            "source_analysis",
            "done",
            "样例爆款分析完成",
            "已得到可迁移的爆款结构摘要。",
            _structure_summary(source),
        ),
    )

    await _emit(on_event, _progress("target_analysis", "running", "正在分析目标素材", "识别目标视频中可承接 near/mid/far/环境释放的片段。"))
    target = await _analyze_video_structure(str(target_path), use_frame_audit=use_frame_audit)
    await _emit(
        on_event,
        _progress(
            "target_analysis",
            "done",
            "目标素材分析完成",
            "已提取可复用镜头和空间变化。",
            _structure_summary(target),
        ),
    )

    target_description = target_description or _target_description_from_structure(target)

    await _emit(on_event, _progress("transfer", "running", "正在迁移结构", "把样例的节奏、空间角色和 CTA 结构映射到目标素材。"))
    transfer_result = await _transfer_structure(
        source_structure=source,
        target_description=target_description,
        target_meta={"duration": target.meta.duration, "resolution": target.meta.resolution},
        target_structure=target,
    )

    transfer_dir = OUTPUT_DIR / "transfer"
    os.makedirs(transfer_dir, exist_ok=True)
    transfer_file = transfer_dir / f"transfer_{run_id}.json"
    with open(transfer_file, "w", encoding="utf-8") as f:
        json.dump(transfer_result, f, ensure_ascii=False, indent=2)

    await _emit(
        on_event,
        _progress(
            "transfer",
            "done",
            "结构迁移完成",
            "已生成可执行分镜、素材覆盖和补全策略。",
            _transfer_summary(transfer_result, str(transfer_file)),
        ),
    )

    os.makedirs(VIDEO_OUTPUT_DIR, exist_ok=True)
    video_filename = f"video_{run_id}.mp4"
    video_path = str(VIDEO_OUTPUT_DIR / video_filename)

    await _emit(on_event, _progress("render", "running", "正在生成视频", "FFmpeg 正在裁切、变速、叠字幕和混入样例 BGM。"))
    await asyncio.to_thread(
        generate_transfer_video,
        transfer_result_path=str(transfer_file),
        target_video_path=str(target_path),
        output_path=video_path,
        use_ai_image=True,
        source_video_path=str(source_path),
    )
    size_mb = os.path.getsize(video_path) / 1024 / 1024
    await _emit(
        on_event,
        _progress(
            "render",
            "done",
            "视频生成完成",
            "成片已写入本地输出目录。",
            {
                "video_path": video_path,
                "video_url": _video_url(video_filename),
                "size_mb": round(size_mb, 2),
            },
        ),
    )

    return {
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
            "url": _video_url(video_filename),
            "filename": video_filename,
            "size_mb": round(size_mb, 2),
        },
    }


@router.get("/videos/{filename}")
async def get_pipeline_video(filename: str):
    """Serve generated videos for browser preview and download."""
    if Path(filename).name != filename or not filename.endswith(".mp4"):
        raise HTTPException(status_code=400, detail="非法视频文件名")

    video_path = VIDEO_OUTPUT_DIR / filename
    if not video_path.exists() or not video_path.is_file():
        raise HTTPException(status_code=404, detail="视频文件不存在")

    return FileResponse(video_path, media_type="video/mp4")


async def _save_uploads(source_video: UploadFile, target_video: UploadFile) -> tuple[str, Path, Path]:
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

    return run_id, source_path, target_path


async def _analyze_video_structure(video_path: str, use_frame_audit: bool) -> VideoStructure:
    return await asyncio.to_thread(
        lambda: asyncio.run(analyze_video_structure(video_path, use_frame_audit=use_frame_audit))
    )


async def _transfer_structure(
    source_structure: VideoStructure,
    target_description: str,
    target_meta: dict[str, Any],
    target_structure: VideoStructure,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        lambda: asyncio.run(
            transfer_structure(
                source_structure=source_structure,
                target_description=target_description,
                target_meta=target_meta,
                target_structure=target_structure,
            )
        )
    )


def _target_description_from_structure(target: VideoStructure) -> str:
    return f"""目标视频内容描述:
- 时长: {target.meta.duration:.1f}秒, 分辨率: {target.meta.resolution}
- 画面内容: {target.shots[0].content if target.shots else '未知'}
- 旁白/对话: {'; '.join(sec.text for sec in target.script_structure if sec.text)}
- 整体风格: {target.packaging_structure.overall_visual_tone}"""


def _structure_summary(structure: VideoStructure) -> dict[str, Any]:
    tf = structure.transferable_features
    return {
        "duration": round(structure.meta.duration, 2),
        "resolution": structure.meta.resolution,
        "script_count": len(structure.script_structure),
        "shot_count": len(structure.shots),
        "hook_strategy": tf.hook_strategy,
        "pacing_pattern": tf.pacing_pattern,
        "spatial_pattern": tf.spatial_pattern,
        "subject_trajectory": tf.subject_trajectory,
        "key_shots": [
            {
                "time": f"{shot.start_time:.1f}-{shot.end_time:.1f}s",
                "type": shot.type,
                "content": shot.content,
                "distance": shot.subject_distance,
                "motion": shot.subject_motion,
            }
            for shot in structure.shots[:5]
        ],
    }


def _transfer_summary(transfer_result: dict[str, Any], transfer_path: str) -> dict[str, Any]:
    timeline = transfer_result.get("timeline_metrics") or {}
    coverage = transfer_result.get("material_coverage") or {}
    return {
        "transfer_path": transfer_path,
        "storyboard_count": len(transfer_result.get("storyboard") or []),
        "script_count": len(transfer_result.get("script") or []),
        "spatial_roles": timeline.get("spatial_roles") or [],
        "total_duration": timeline.get("total_duration"),
        "coverage_ratio": coverage.get("coverage_ratio"),
        "filling_summary": coverage.get("filling_summary"),
    }


def _progress(
    step: str,
    status: str,
    title: str,
    message: str,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": "progress",
        "step": step,
        "status": status,
        "title": title,
        "message": message,
        "detail": detail or {},
    }


def _result_event(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "result",
        "step": "complete",
        "status": "done",
        "title": "全部完成",
        "message": "爆款分析、结构迁移和视频生成已完成。",
        "result": result,
    }


def _json_line(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


async def _emit(on_event: Callable[[dict[str, Any]], Any] | None, event: dict[str, Any]) -> None:
    if on_event:
        maybe_awaitable = on_event(event)
        if hasattr(maybe_awaitable, "__await__"):
            await maybe_awaitable
        await asyncio.sleep(0)


def _file_size_mb(path: Path) -> float:
    return round(path.stat().st_size / 1024 / 1024, 2)


def _video_url(filename: str) -> str:
    return f"/api/pipeline/videos/{filename}"
