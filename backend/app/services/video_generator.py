"""视频生成服务

基于迁移结果，使用 Pillow 生成文字图层 + FFmpeg 合成最终视频。
保留原始音频。
"""

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def generate_transfer_video(
    transfer_result_path: str,
    target_video_path: str,
    output_path: str,
    use_ai_image: bool = True,
    source_video_path: str | None = None,
) -> str:
    """生成迁移后的视频

    Args:
        transfer_result_path: 迁移结果 JSON 路径
        target_video_path: 目标视频路径
        output_path: 输出视频路径
        use_ai_image: 是否使用 AI 生成 CTA 图片
        source_video_path: 样例视频路径（用于提取 BGM）
    """
    with open(transfer_result_path, "r", encoding="utf-8") as f:
        result = json.load(f)

    storyboard = result.get("storyboard") or result.get("新分镜 (storyboard)") or result.get("新分镜", [])
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    vw, vh, fps = _get_video_info(target_video_path)

    segments = []
    for i, shot in enumerate(storyboard):
        source = shot.get("source", "")
        start, end = _parse_source_range(source)
        segments.append({
            "index": i,
            "start": start,
            "end": end,
            "duration": float(shot.get("duration", 3)),
            "type": shot["type"],
            "subtitle": shot.get("subtitle", ""),
            "content": shot.get("content", ""),
            "source": source,
            "edit": shot.get("edit", {}) if isinstance(shot.get("edit"), dict) else {},
        })

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        clip_files = []

        for seg in segments:
            clip_path = str(tmp / f"clip_{seg['index']}.mp4")

            if seg["type"] == "text-overlay":
                _create_cta_clip(
                    output_path=clip_path,
                    duration=seg["duration"],
                    text=seg["subtitle"],
                    content=seg["content"],
                    width=vw, height=vh, fps=fps,
                    use_ai_image=use_ai_image,
                    tmp_dir=str(tmp),
                )
            else:
                _create_video_clip(
                    video_path=target_video_path,
                    output_path=clip_path,
                    seg=seg,
                    width=vw, height=vh, fps=fps,
                    tmp_dir=str(tmp),
                )

            clip_files.append(clip_path)

        # 拼接视频
        concat_path = str(tmp / "concat.mp4")
        _concat_clips(clip_files, concat_path, fps)

        # 如果有样例视频，提取 BGM 并混入
        if source_video_path and Path(source_video_path).exists():
            _mix_bgm(
                video_path=concat_path,
                source_video_path=source_video_path,
                output_path=output_path,
                tmp_dir=str(tmp),
            )
        else:
            shutil.move(concat_path, output_path)

    return output_path


def _create_video_clip(
    video_path: str,
    output_path: str,
    seg: dict,
    width: int, height: int, fps: int,
    tmp_dir: str,
):
    """从目标视频提取片段（保留音频），叠加字幕"""
    start = seg["start"]
    end = seg["end"]
    subtitle = seg["subtitle"]
    desired_duration = max(float(seg.get("duration") or 3), 0.3)

    if start is not None and end is not None:
        source_duration = max(end - start, 0.3)
    else:
        source_duration = desired_duration
        start = 0

    speed = _resolve_speed(seg, source_duration, desired_duration)
    vf = _build_video_filter(seg, width, height, fps, speed)
    af = _build_audio_filter(speed)

    # 提取片段，按 storyboard duration 重定速，并保留音频
    raw_clip = str(Path(tmp_dir) / f"raw_{seg['index']}.mp4")
    if _has_audio_stream(video_path):
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start), "-t", str(source_duration), "-i", video_path,
            "-filter_complex", f"[0:v]{vf}[v];[0:a]{af}[a]",
            "-map", "[v]", "-map", "[a]",
            "-t", str(desired_duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            raw_clip,
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start), "-t", str(source_duration), "-i", video_path,
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-filter_complex", f"[0:v]{vf}[v]",
            "-map", "[v]", "-map", "1:a",
            "-t", str(desired_duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            raw_clip,
        ]
    subprocess.run(cmd, check=True, capture_output=True)

    if subtitle:
        # 生成字幕 PNG 并叠加（保留音频）
        sub_png = str(Path(tmp_dir) / f"sub_{seg['index']}.png")
        _make_subtitle_png(subtitle, sub_png, width, height)
        _overlay_image_with_audio(raw_clip, sub_png, output_path)
    else:
        shutil.move(raw_clip, output_path)


def _create_cta_clip(
    output_path: str,
    duration: float,
    text: str,
    content: str,
    width: int, height: int, fps: int,
    use_ai_image: bool,
    tmp_dir: str,
):
    """生成 CTA 引导片段（带静音音频）"""
    img_path = str(Path(tmp_dir) / "cta.png")

    if use_ai_image and not _looks_like_search_cta(text, content):
        try:
            from .image_generator import generate_cta_image
            generate_cta_image(text or "快来参与同款挑战", img_path)
        except Exception:
            _make_cta_png(text, img_path, width, height)
    else:
        _make_cta_png(text, img_path, width, height)

    # 图片转视频 + 静音音频轨
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-loop", "1", "-i", img_path,
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", str(duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p", "-r", str(fps),
            "-shortest",
            output_path,
        ],
        check=True, capture_output=True,
    )


def _mix_bgm(
    video_path: str,
    source_video_path: str,
    output_path: str,
    tmp_dir: str,
    bgm_volume: float = 0.85,
    keep_original_audio: bool = False,
):
    """从样例视频提取 BGM 应用到迁移视频

    Args:
        video_path: 迁移视频路径
        source_video_path: 样例视频路径（提取 BGM）
        output_path: 输出路径
        tmp_dir: 临时目录
        bgm_volume: BGM 音量比例
        keep_original_audio: 是否保留目标原声。默认 False，让爆款 BGM 成为主音轨。
    """
    # 提取样例视频音频
    bgm_raw = str(Path(tmp_dir) / "bgm_raw.aac")
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", source_video_path,
            "-vn", "-c:a", "aac", "-b:a", "128k",
            bgm_raw,
        ],
        check=True, capture_output=True,
    )

    # 获取迁移视频时长
    duration_str = subprocess.check_output(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", video_path],
    ).decode().strip()
    duration = float(duration_str)

    if keep_original_audio and _has_audio_stream(video_path):
        audio_filter = (
            f"[0:a]volume=0.18[orig];"
            f"[1:a]volume={bgm_volume}[bgm];"
            "[orig][bgm]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
            "alimiter=limit=0.90[outa]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-stream_loop", "-1", "-i", bgm_raw,
            "-t", str(duration),
            "-filter_complex", audio_filter,
            "-map", "0:v", "-map", "[outa]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
            "-movflags", "+faststart",
            output_path,
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-stream_loop", "-1", "-i", bgm_raw,
            "-t", str(duration),
            "-map", "0:v", "-map", "1:a:0",
            "-filter:a", f"volume={bgm_volume},alimiter=limit=0.90",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
            "-shortest",
            "-movflags", "+faststart",
            output_path,
        ]

    subprocess.run(cmd, check=True, capture_output=True)


def _overlay_image_with_audio(video_path: str, image_path: str, output_path: str):
    """在视频上叠加透明图片，保留音频"""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", video_path,
            "-loop", "1", "-i", image_path,
            "-filter_complex", "[0:v][1:v]overlay=0:0:shortest=1[outv]",
            "-map", "[outv]", "-map", "0:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            output_path,
        ],
        check=True, capture_output=True,
    )


def _concat_clips(clip_files: list[str], output_path: str, fps: int = 29):
    """拼接所有片段（视频+音频），并做音量归一化"""
    tmp_dir = Path(output_path).parent / "_concat_tmp"
    tmp_dir.mkdir(exist_ok=True)

    # 统一编码参数
    normalized = []
    for i, clip in enumerate(clip_files):
        out = str(tmp_dir / f"n{i}.mp4")
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", clip,
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
                "-pix_fmt", "yuv420p", "-r", str(fps),
                "-video_track_timescale", "90000",
                out,
            ],
            check=True, capture_output=True,
        )
        normalized.append(out)

    concat_file = str(tmp_dir / "concat.txt")
    with open(concat_file, "w") as f:
        for clip in normalized:
            f.write(f"file '{clip}'\n")

    # 先拼接
    raw_concat = str(tmp_dir / "raw_concat.mp4")
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            raw_concat,
        ],
        check=True, capture_output=True,
    )

    # 音量归一化（loudnorm 滤镜，目标 -16 LUFS）
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", raw_concat,
            "-af", "loudnorm=I=-16:LRA=11:TP=-1.5",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            output_path,
        ],
        check=True, capture_output=True,
    )

    shutil.rmtree(tmp_dir, ignore_errors=True)


def _build_video_filter(seg: dict, width: int, height: int, fps: int, speed: float) -> str:
    """Build video filters for reframing and retiming a clip."""
    crop_mode = str(seg.get("edit", {}).get("crop") or "")
    shot_type = str(seg.get("type") or "")
    crop_factor = 1.0
    if crop_mode == "tight" or shot_type == "close-up":
        crop_factor = 0.78
    elif crop_mode == "medium" or shot_type == "medium":
        crop_factor = 0.90

    filters = []
    if crop_factor < 1.0:
        filters.append(
            f"crop=iw*{crop_factor}:ih*{crop_factor}:(iw-iw*{crop_factor})/2:(ih-ih*{crop_factor})/2"
        )
    filters.extend(
        [
            f"scale={width}:{height}:force_original_aspect_ratio=increase",
            f"crop={width}:{height}",
            f"fps={fps}",
            "setsar=1",
            f"setpts=PTS/{speed:.5f}",
        ]
    )
    return ",".join(filters)


def _build_audio_filter(speed: float) -> str:
    parts = []
    remaining = speed
    while remaining > 2.0:
        parts.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        parts.append("atempo=0.5")
        remaining /= 0.5
    parts.append(f"atempo={remaining:.5f}")
    parts.append("volume=0.9")
    return ",".join(parts)


def _resolve_speed(seg: dict, source_duration: float, desired_duration: float) -> float:
    edit_speed = seg.get("edit", {}).get("speed") if isinstance(seg.get("edit"), dict) else None
    try:
        speed = float(edit_speed)
    except (TypeError, ValueError):
        speed = source_duration / desired_duration
    return max(0.5, min(2.4, speed))


def _has_audio_stream(video_path: str) -> bool:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", video_path],
    ).decode().strip()
    return bool(out)


def _wrap_text(text: str, max_chars: int = 10) -> list[str]:
    clean = re.sub(r"\s+", "", text or "")
    if not clean:
        return []
    return [clean[i:i + max_chars] for i in range(0, len(clean), max_chars)][:2]


def _normalize_cta_text(text: str) -> str:
    clean = re.sub(r"\s+", "", text or "")
    clean = clean.replace("大家都在抖音搜索", "").replace("抖音", "")
    return clean or "同款校园手势舞挑战"


def _looks_like_search_cta(text: str, content: str) -> bool:
    joined = f"{text} {content}"
    return any(key in joined for key in ("抖音", "搜索", "挑战", "CTA", "引导"))


def _fit_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> str:
    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return text
    fitted = text
    while fitted and draw.textbbox((0, 0), fitted + "…", font=font)[2] > max_width:
        fitted = fitted[:-1]
    return fitted + "…" if fitted else text[:4]


def _make_subtitle_png(text: str, output_path: str, width: int = 720, height: int = 1280):
    """生成短视频字幕透明 PNG（大字描边，不挡主体）"""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font = _get_font(max(28, min(46, width // 17)))
    lines = _wrap_text(text, max_chars=10)
    line_boxes = [draw.textbbox((0, 0), line, font=font, stroke_width=3) for line in lines]
    line_heights = [box[3] - box[1] for box in line_boxes]
    y = height - max(170, int(height * 0.14))

    for line, box, lh in zip(lines, line_boxes, line_heights):
        tw = box[2] - box[0]
        x = (width - tw) // 2 - box[0]
        # Soft shadow gives readability without the heavy black banner.
        draw.text((x + 2, y + 3), line, font=font, fill=(0, 0, 0, 150), stroke_width=4, stroke_fill=(0, 0, 0, 150))
        draw.text((x, y), line, font=font, fill=(255, 248, 210, 255), stroke_width=3, stroke_fill=(30, 35, 45, 230))
        y += lh + 8

    img.save(output_path)


def _make_cta_png(text: str, output_path: str, width: int = 720, height: int = 1280):
    """用 Pillow 生成接近爆款样例的抖音搜索 CTA PNG"""
    img = Image.new("RGB", (width, height), (10, 14, 26))
    draw = ImageDraw.Draw(img)

    for y in range(height):
        ratio = y / max(height - 1, 1)
        r = int(9 + 18 * ratio)
        g = int(13 + 22 * ratio)
        b = int(29 + 36 * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    main_font = _get_font(max(34, width // 15))
    logo_font = _get_font(max(46, width // 11))
    small_font = _get_font(max(20, width // 30))
    search_font = _get_font(max(26, width // 22))

    main_text = _normalize_cta_text(text)
    card_w = int(width * 0.62)
    card_h = int(height * 0.26)
    card_x = (width - card_w) // 2
    card_y = int(height * 0.24)
    draw.rounded_rectangle([card_x, card_y, card_x + card_w, card_y + card_h], radius=28, outline=(95, 105, 130), width=3)

    top = "大家都在"
    bbox = draw.textbbox((0, 0), top, font=small_font)
    draw.text(((width - (bbox[2] - bbox[0])) // 2, card_y + 42), top, font=small_font, fill=(245, 245, 248))

    logo_text = "抖音"
    bbox = draw.textbbox((0, 0), logo_text, font=logo_font)
    logo_x = (width - (bbox[2] - bbox[0])) // 2
    logo_y = card_y + 84
    draw.text((logo_x - 3, logo_y), logo_text, font=logo_font, fill=(0, 245, 235))
    draw.text((logo_x + 3, logo_y), logo_text, font=logo_font, fill=(255, 35, 90))
    draw.text((logo_x, logo_y), logo_text, font=logo_font, fill=(255, 255, 255))

    search_h = max(58, int(height * 0.055))
    search_w = int(width * 0.80)
    search_x = (width - search_w) // 2
    search_y = card_y + card_h - search_h // 2
    draw.rounded_rectangle([search_x, search_y, search_x + search_w, search_y + search_h], radius=12, fill=(255, 255, 255))
    draw.text((search_x + 26, search_y + 16), "搜索", font=small_font, fill=(20, 20, 24))

    safe_text = _fit_text(main_text, search_font, search_w - 160, draw)
    draw.text((search_x + 120, search_y + 14), safe_text, font=search_font, fill=(28, 28, 32))
    draw.ellipse([search_x + search_w - 52, search_y + 18, search_x + search_w - 30, search_y + 40], outline=(55, 55, 60), width=3)
    draw.line([search_x + search_w - 34, search_y + 38, search_x + search_w - 24, search_y + 48], fill=(55, 55, 60), width=3)

    chip_y = int(height * 0.74)
    chip_w = int(width * 0.50)
    chip_h = 80
    chip_x = int(width * 0.09)
    draw.rounded_rectangle([chip_x, chip_y, chip_x + chip_w, chip_y + chip_h], radius=18, fill=(42, 50, 67))
    draw.text((chip_x + 26, chip_y + 15), "截图保存到相册", font=small_font, fill=(210, 218, 232))
    draw.text((chip_x + 26, chip_y + 45), "抖音搜索页扫一扫", font=small_font, fill=(170, 182, 202))

    qr = max(96, width // 6)
    qr_x = width - chip_x - qr
    qr_y = chip_y - 6
    draw.ellipse([qr_x, qr_y, qr_x + qr, qr_y + qr], fill=(245, 246, 250))
    draw.ellipse([qr_x + 22, qr_y + 22, qr_x + qr - 22, qr_y + qr - 22], outline=(25, 28, 34), width=6)
    play = [
        (qr_x + qr * 0.43, qr_y + qr * 0.35),
        (qr_x + qr * 0.43, qr_y + qr * 0.65),
        (qr_x + qr * 0.68, qr_y + qr * 0.50),
    ]
    draw.polygon(play, fill=(15, 16, 20))

    img.save(output_path)


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    """获取中文字体"""
    font_paths = [
        "/System/Library/AssetsV2/com_apple_MobileAsset_Font8/86ba2c91f017a3749571a82f2c6d890ac7ffb2fb.asset/AssetData/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
    ]
    for fp in font_paths:
        if Path(fp).exists():
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _get_video_info(video_path: str) -> tuple[int, int, int]:
    """获取视频分辨率和帧率"""
    out = subprocess.check_output(
        ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate",
         "-of", "csv=p=0", video_path],
    ).decode().strip()
    parts = out.split(",")
    w, h = int(parts[0]), int(parts[1])
    fps_str = parts[2] if len(parts) > 2 else "29/1"
    if "/" in fps_str:
        num, den = fps_str.split("/")
        fps = int(int(num) / int(den))
    else:
        fps = int(float(fps_str))
    return w, h, fps


def _parse_source_range(source: str) -> tuple[float | None, float | None]:
    """从 source 字段解析时间范围，如 '目标视频 0-6s' -> (0, 6)"""
    if not source:
        return None, None
    m = re.search(r'(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)\s*s?', source)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None, None
