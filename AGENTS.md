# AGENTS.md

## Project

This repo is a short-video structure transfer engine for the Douyin/CapCut-style competition task:

1. Analyze viral sample videos.
2. Extract transferable structure.
3. Map that structure onto a target video.
4. Generate a new demo video with FFmpeg.

The current key case uses:

- Viral source: `videos/1.mp4`
- Target material: `transfer-videos/1.mp4`
- Final output: `backend/outputs/transfer/final_transfer.mp4`
- Final timeline JSON: `backend/outputs/transfer/final_transfer.json`
- Debug package: `backend/outputs/video_analysis_debug/`

## Environment

Use the conda `cv` environment for Python backend work. This environment includes
the project backend dependencies plus CV packages used for algorithmic keyframe
selection.

```bash
conda run -n cv python ...
conda run -n cv uvicorn app.main:app --reload --port 8010
```

Do not assume the base Python has the right dependencies. The Volcengine Ark SDK,
project Python deps, and CV keyframe dependencies should be used from `cv`.

## Model Choice

Prefer the Pro model for all video analysis and structure transfer runs:

```text
doubao-seed-2-0-pro-260215
```

The backend default model should stay aligned with this preference. Only use a lite model when the user explicitly asks for a faster/cheaper test run.

## Secrets

`ARK_API_KEY` is provided via environment variables or `backend/.env`.

Never write the API key into code, prompts, logs, screenshots, docs, or committed files. If debugging requires showing it, only show a masked prefix such as `key[:8] + "..."`.

## Important Video Understanding Notes

Doubao video understanding receives the full uploaded video, but model perception is based on sampled frames controlled by `video_url.fps`. It is not reliable to assume the model tracks every frame or every tiny far-away subject.

For this project's main sample, the viral structure is not "walking/running". The core transferable structure is:

```text
near hand-gesture action -> subject moves farther / gets smaller -> environment release -> Douyin search CTA
```

For `videos/1.mp4`, the human-reviewed structure is:

- `0-6s`: near/mid subject, hand gesture/dance action is clear.
- `7-11s`: subject moves away, subject scale gets smaller.
- `12-15s`: environment/film-set release; subject is weak or out of frame.
- `16-19s`: Douyin search CTA.

For `transfer-videos/1.mp4`, the useful target ranges are:

- `0-2s`: near opening.
- `2-6s`: clear near/mid hand-gesture action.
- `10-14s`: continued mid hand-gesture action.
- `28-32s`: far view, subjects smaller.
- `48-56s`: tiny far subjects / environment release.

Avoid over-weighting `16-24s` in the target video: it contains obvious walking/running, but that is not the source sample's core viral structure.

## BGM Transfer

When generating a transfer video with `source_video_path`, the source video audio should be the main BGM track. The generator currently defaults to source BGM as the main audio, not a quiet background mix.

If target original sound needs to be retained, use the optional mixed mode in `video_generator._mix_bgm(..., keep_original_audio=True)`.

## Analysis Artifacts

Every future `analyze_video_structure(...)` run should save review artifacts under:

```text
backend/outputs/analysis_runs/<task_id>/
```

Expected contents include:

- sampled frames
- `contact_sheet.jpg`
- `raw_doubao_result.json`
- `normalized_structure.json`
- `spatial_summary.md`
- `meta.json`

There is also a manually curated debug package for the current case:

```text
backend/outputs/video_analysis_debug/
```

Use its contact sheets and JSON files before changing prompts or transfer logic.

## Prompt / Pipeline Guidance

The prompt and pipeline should treat spatial trajectory as a first-class structure:

- `subject_distance`
- `subject_position`
- `subject_motion`
- `spatial_pattern`
- `subject_trajectory`
- `composition_pattern`
- `spatial_keyframes`

For far-away people, explicitly preserve `tiny/far` observations. Do not collapse them into generic "environment" if they are part of the near-to-far trajectory.

When optimizing the pipeline, prefer a two-stage analysis:

1. General video structure analysis.
2. Algorithmic keyframe selection followed by a spatial-only audit focused on
   subject scale, position, and movement over time.

The transfer stage should map spatial roles in order:

```text
near -> mid -> far -> tiny/environment -> cta
```

## Useful Commands

```bash
# Compile backend
conda run -n cv python -m compileall backend/app/services backend/app/models backend/app/api

# Generate final video from current final timeline
conda run -n cv python - <<'PY'
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

# Inspect final video
ffprobe -v error -show_entries format=duration:stream=width,height,r_frame_rate,codec_type \
  -of default=noprint_wrappers=1 backend/outputs/transfer/final_transfer.mp4

# Check audio loudness
ffmpeg -hide_banner -i backend/outputs/transfer/final_transfer.mp4 \
  -vn -af volumedetect -f null -
```

## Safety / Git

The worktree may contain user changes. Do not revert unrelated files. Do not delete analysis/debug artifacts unless the user explicitly asks to clean them.
