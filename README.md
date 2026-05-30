# 爆款结构迁移引擎

短视频结构迁移 demo：上传爆款样例视频和目标素材，后端拆解样例结构并迁移到目标视频，最后输出时间线 JSON 和可播放 mp4。

当前主要 case：

- 样例视频：`videos/1.mp4`
- 目标素材：`transfer-videos/1.mp4`
- 最终时间线：`backend/outputs/transfer/final_transfer.json`
- 最终成片：`backend/outputs/transfer/final_transfer.mp4`

## 环境准备

```bash
cp backend/.env.example backend/.env
# 填写 backend/.env 里的 ARK_API_KEY

conda create -n agent python=3.11 -y
conda run -n agent pip install -r backend/requirements.txt

cd frontend
npm install
cp .env.example .env
cd ..
```

本机还需要安装 FFmpeg：

```bash
ffmpeg -version
ffprobe -version
```

macOS 可用：

```bash
brew install ffmpeg
```

## 本地启动

终端 1：启动后端，固定用 `8010`，避免撞到本机其他 `8000` 服务。

```bash
cd backend
conda run -n agent uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

终端 2：启动前端。

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 3000
```

打开：

```text
http://127.0.0.1:3000
```

前端通过 Vite proxy 调后端。默认代理目标在 `frontend/.env.example`：

```bash
VITE_API_PROXY_TARGET=http://127.0.0.1:8010
```

## 联调验证命令

以下命令默认在项目根目录执行，并且两个服务都已启动。

### 1. 后端健康检查

```bash
curl -sS http://127.0.0.1:8010/health
```

期望返回：

```json
{"status":"ok"}
```

### 2. 验证前端代理上传

这个请求走 `3000 -> Vite proxy -> 8010`，用于确认前端上传不会误打到旧的 `8000` 服务。

```bash
curl -sS -i \
  -F 'file=@videos/1.mp4;type=video/mp4' \
  http://127.0.0.1:3000/api/analyze/upload | sed -n '1,30p'
```

期望看到 `HTTP/1.1 200 OK`，响应里包含 `file_id`、`path`、`size`。

### 3. 验证完整 pipeline

这个命令会调用 Doubao 视频理解并生成 mp4，通常需要 1-3 分钟。

```bash
curl -sS -w '\nHTTP_STATUS:%{http_code}\n' \
  -o /tmp/douyin_pipeline_response.json \
  -F 'source_video=@videos/1.mp4;type=video/mp4' \
  -F 'target_video=@transfer-videos/1.mp4;type=video/mp4' \
  -F 'target_description=三姐妹操场手势舞，迁移近到远空间结构' \
  -F 'use_frame_audit=false' \
  http://127.0.0.1:3000/api/pipeline/run
```

期望最后输出：

```text
HTTP_STATUS:200
```

查看结果摘要：

```bash
jq '{status, run_id, source_meta, target_meta, video, timeline_metrics: .transfer.timeline_metrics}' \
  /tmp/douyin_pipeline_response.json
```

检查生成的视频：

```bash
VIDEO=$(jq -r '.video.path' /tmp/douyin_pipeline_response.json)
ls -lh "$VIDEO"
ffprobe -v error \
  -show_entries format=duration:stream=width,height,r_frame_rate,codec_type \
  -of default=noprint_wrappers=1 \
  "$VIDEO"
```

## 构建检查

```bash
conda run -n agent python -m compileall backend/app/services backend/app/models backend/app/api

cd frontend
npm run build
```

## 常用产物目录

```text
backend/uploads/                  # 前端上传后保存的视频
backend/outputs/analysis_runs/    # 分析证据包：抽帧、contact sheet、模型结果、空间摘要
backend/outputs/transfer/         # 迁移时间线 JSON
backend/outputs/videos/           # pipeline 生成的视频
```

## 可选：自抽帧空间审计

默认关闭。需要二阶段空间审计时可以在后端环境变量里打开：

```bash
ENABLE_FRAME_SPATIAL_AUDIT=true
```

或在 API 表单/查询参数中传：

```bash
use_frame_audit=true
```

## 安全边界

- 不要提交真实 `backend/.env`、视频素材、上传文件或生成产物。
- `ARK_API_KEY` 只从环境变量或 `backend/.env` 读取。
- 主要后端命令使用 conda `agent` 环境运行。
