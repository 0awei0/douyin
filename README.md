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

conda create -n cv python=3.11 -y
conda run -n cv pip install -r backend/requirements.txt

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
conda run -n cv uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
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

### 3. 验证流式完整 pipeline

这个命令会调用 Doubao 视频理解并生成 mp4，通常需要 1-3 分钟。终端会持续输出 JSON 行，前端也基于同一个流展示实时进度。

```bash
curl -sS -N \
  -F 'source_video=@videos/1.mp4;type=video/mp4' \
  -F 'target_video=@transfer-videos/1.mp4;type=video/mp4' \
  -F 'target_description=三姐妹操场手势舞，迁移近到远空间结构' \
  -F 'use_frame_audit=true' \
  http://127.0.0.1:3000/api/pipeline/run/stream | tee /tmp/douyin_pipeline_stream.ndjson
```

期望先看到类似这样的进度行：

```text
{"type":"progress","step":"upload","status":"running",...}
{"type":"progress","step":"source_analysis","status":"running",...}
```

查看结果摘要：

```bash
jq -s 'map(select(.type == "result"))[-1].result' \
  /tmp/douyin_pipeline_stream.ndjson > /tmp/douyin_pipeline_response.json

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
conda run -n cv python -m compileall backend/app/services backend/app/models backend/app/api

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

## Hybrid 迁移方案

当前推荐默认使用 hybrid 流程，适合迁移到其他源视频和目标素材：

```text
用户输入视频亮点/迁移要求
  -> LLM 扩写成结构化创作约束
  -> 注入分析与迁移提示词
Doubao 直接视频理解
  -> 本地 CV 算法预选关键帧
  -> 多关键帧按时间顺序一起送入 Doubao 做空间审计
  -> transfer optimizer 按 near/mid/far/tiny/environment/cta 纠偏
  -> 用户确认迁移方案，可用自然语言继续调整
  -> FFmpeg 渲染成片
```

这套流程没有依赖固定绝对时间点。它会先分析源视频的可迁移结构，再在目标素材里寻找可承接的空间角色：

```text
near -> mid/action -> far/smaller subject -> tiny/environment release -> cta
```

本地 CV 关键帧选择会综合：

- 镜头边界和时间覆盖；
- 画面差异与运动峰值；
- 视觉多样性；
- OpenCV 探针帧中的运动面积、边缘密度和人物检测候选。

Doubao 空间审计不是逐帧单独调用，而是把这些关键帧按时间顺序放进同一个多图请求，并附上每张图的时间戳。这样模型能比较前后帧，判断主体占比、位置和空间角色变化。

上传时可以补充“创作亮点与迁移要求”，例如：

```text
开头三个人离镜头近，有手势舞，后面越跑越远，但是不要突出跑步，要突出从近到远的操场空间感。
```

后端会先把这段自然语言扩写为结构化约束，包括用户亮点、迁移优先级、不要强调的误判方向、风格关键词和 CTA 关键词。生成迁移方案后，结果页会展示分镜卡片和视频预览，用户可以通过快捷选项或自然语言继续调整方案，后端会改写 transfer JSON 并重新渲染视频。

`transfer_optimizer` 会进一步避免常见误映射：

- `near` 不应被中景动作段替代；
- `mid` 优先选择开头附近的清晰手势/动作段；
- `far` 不应落到过晚的 tiny/environment 段；
- 跑步/走路只作为“主体远离”的空间线索，不作为核心 viral 动作。

## 算法关键帧 + 自抽帧空间审计

需要二阶段空间审计时可以在后端环境变量里打开：

```bash
ENABLE_FRAME_SPATIAL_AUDIT=true
```

或在 API 表单/查询参数中传：

```bash
use_frame_audit=true
```

开启后，后端会先用本地 CV 算法预选关键帧候选，再把关键帧序列交给 Doubao 做空间轨迹审计。关键帧证据会保存到：

```text
backend/outputs/analysis_runs/<task_id>/algorithmic_keyframes/
```

当前 case 的最新对比产物：

```text
backend/outputs/strategy_compare/video_strategy_hybrid_cv_opening_gesture.mp4
backend/outputs/strategy_compare/transfer_strategy_hybrid_cv_opening_gesture.json
backend/outputs/strategy_compare/contact_hybrid_cv_opening_gesture.jpg
```

## 安全边界

- 不要提交真实 `backend/.env`、视频素材、上传文件或生成产物。
- `ARK_API_KEY` 只从环境变量或 `backend/.env` 读取。
- 主要后端命令使用 conda `cv` 环境运行。
