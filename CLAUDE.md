# 爆款结构迁移引擎

AI 短视频创作系统：上传样例视频 → 拆解结构 → 迁移到新内容 → 生成新视频。

## 项目结构

```
douyin/
├── backend/          # FastAPI 后端 (Python 3.11, conda agent 环境)
│   ├── app/
│   │   ├── core/config.py      # 配置管理（读 .env）
│   │   ├── models/             # Pydantic 数据模型
│   │   ├── services/           # 业务逻辑（视频分析、豆包 API）
│   │   └── api/                # FastAPI 路由
│   ├── uploads/                # 上传的视频
│   └── outputs/                # 分析结果输出
├── frontend/         # React + TypeScript 前端
├── videos/           # 测试视频素材
└── doc/              # 比赛文档
```

## 技术栈

- **后端**: Python 3.11 + FastAPI + volcengine-python-sdk
- **前端**: React + TypeScript + TailwindCSS
- **视频解析**: FFmpeg + ffprobe
- **AI**: 豆包 Doubao-Seed-2.0-lite (火山方舟 API)
- **环境**: conda `agent` 环境

## 常用命令

```bash
# 后端运行
cd backend && conda run -n agent uvicorn app.main:app --reload --port 8000

# 测试视频分析
cd backend && conda run -n agent python test_analysis.py

# 测试 FFmpeg 提取
cd backend && conda run -n agent python test_ffmpeg.py
```

## 安全限制

- **禁止在代码、日志、输出中打印完整的 API Key**
- `.env` 文件不提交到 git
- API Key 仅通过环境变量或 `.env` 文件读取，代码中最多显示前 10 位用于调试
- 任何涉及 API Key 的地方使用 `key[:10] + "..."` 做脱敏处理

## 视频结构协议 (VideoStructure)

系统的核心数据模型，定义在 `backend/app/models/video_structure.py`：

- **script_structure**: 脚本段落（hook/problem/solution/demo/cta）
- **rhythm_structure**: 节奏（镜头列表、节奏点、高潮位置）
- **packaging_structure**: 包装（字幕样式、转场、封面风格）

## 分析流程

```
视频 → FFmpeg(元信息+场景检测+关键帧+音频分离)
     → 豆包视频理解 API(语义分析)
     → 整合为 VideoStructure JSON
```
