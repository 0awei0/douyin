# 爆款结构迁移引擎

短视频结构迁移 demo：输入一个爆款样例视频和一段目标素材，系统会拆解样例的脚本、节奏、包装和空间轨迹，再把这些结构迁移到目标素材上，输出可解释的时间线 JSON 和可验证的成片 demo。

当前重点 case：

- 样例视频：`videos/1.mp4`
- 目标素材：`transfer-videos/1.mp4`
- 最终时间线：`backend/outputs/transfer/final_transfer.json`
- 最终成片：`backend/outputs/transfer/final_transfer.mp4`

## 比赛要求对齐

本项目对齐 `doc/` 中的比赛要求，优先完成 P0 闭环：

- 样例视频输入与解析：`/api/analyze/upload`、`/api/analyze/structure`
- 结构拆解：脚本结构、节奏镜头、包装结构、音频节奏、空间轨迹
- 新素材输入：支持目标视频上传和目标描述补充
- 结构迁移：`/api/transfer` 和 `/api/pipeline/run` 生成脚本、分镜、时间线和包装方案
- 素材缺口处理：迁移结果输出 `material_needs` 和 `material_coverage`
- 可展示结果：前端展示迁移过程、空间角色、素材覆盖和缺口补全，后端可生成 mp4 demo

进阶能力已覆盖一部分：

- 包装生成：字幕 PNG、CTA 搜索引导页、封面/转场建议
- 真实素材适配：目标视频二次分析，按时间段筛选可用片段
- 可调参数：目标描述、是否使用 AI 生图、是否混合原声

## AI 架构

```text
样例视频 + 目标视频
  -> ffprobe 提取元信息
  -> Doubao 视频理解拆解结构
  -> 保存分析证据包
  -> LLM 结构迁移生成脚本/分镜/素材需求
  -> transfer_optimizer 规整时间线和空间角色
  -> FFmpeg + Pillow 生成成片 demo
  -> 前端展示迁移过程和结果
```

核心模块：

- `backend/app/services/video_analyzer.py`：视频元信息和结构分析入口
- `backend/app/services/doubao_client.py`：火山方舟 Doubao 调用、抽帧率选择、JSON 解析
- `backend/app/services/analysis_artifacts.py`：保存帧、contact sheet、原始模型结果和空间摘要
- `backend/app/services/transfer.py`：构建样例摘要和目标素材上下文，调用迁移模型
- `backend/app/services/transfer_optimizer.py`：规范 storyboard、补 CTA、强化 near/mid/far/empty/cta 空间映射
- `backend/app/services/video_generator.py`：裁切、变速、字幕叠加、CTA 生成、样例 BGM 迁移
- `frontend/src/`：上传、运行 pipeline、展示脚本/分镜/素材覆盖和缺口补全

## 工具协议

主要数据协议是 `VideoStructure` 和迁移结果 JSON：

- `script_structure`：hook/demo/cta 等段落结构
- `shots`：镜头类型、时间段、画面内容、字幕、特效
- `subject_distance` / `subject_position` / `subject_motion`：空间轨迹字段
- `transferable_features`：hook、叙事、节奏、空间调度、主体轨迹、构图模式
- `storyboard`：可执行分镜，包含 `source` 时间段和 `edit` 剪辑建议
- `timeline_metrics`：成片时长、素材使用段、空间角色、CTA 补全情况
- `material_coverage`：目标素材覆盖、缺口、补全策略

分析运行会保存证据包到：

```text
backend/outputs/analysis_runs/<task_id>/
```

其中包含抽帧、`contact_sheet.jpg`、`raw_doubao_result.json`、`normalized_structure.json`、`spatial_summary.md` 和 `meta.json`。

## 本地运行

后端使用 conda `agent` 环境：

```bash
cd backend
conda run -n agent uvicorn app.main:app --reload --port 8000
```

前端：

```bash
cd frontend
npm install
npm run dev
```

打开 Vite 输出的本地地址后，上传样例视频和目标视频即可运行完整 pipeline。

## 生成当前 case

```bash
conda run -n agent python - <<'PY'
import sys
sys.path.insert(0, 'backend')
from app.services.video_generator import generate_transfer_video

generate_transfer_video(
    'backend/outputs/transfer/final_transfer.json',
    'transfer-videos/1.mp4',
    'backend/outputs/transfer/final_transfer.mp4',
    use_ai_image=False,
    source_video_path='videos/1.mp4',
)
PY
```

## 验证命令

```bash
conda run -n agent python -m compileall backend/app/services backend/app/models backend/app/api

cd frontend
npm run build
```

## 安全边界

- `ARK_API_KEY` 只从环境变量或 `backend/.env` 读取，不写入代码、日志或文档。
- 视频理解通过 `video_url.fps` 抽帧采样，模型不会稳定感知每一帧，因此系统会保存 contact sheet 供人工复核。
- 迁移目标是复用结构方法，不复制样例内容；CTA、字幕和 BGM 迁移应按比赛 demo 场景使用。
- 生成输出、上传素材和本地样例视频默认作为本地产物处理，避免把临时视频、密钥或大体积中间文件误提交。
