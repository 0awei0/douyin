"""测试 FFmpeg 视频提取功能（不需要 API key）"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.services.video_analyzer import (
    get_video_meta,
    detect_scene_changes,
    extract_keyframes,
)


def main():
    videos_dir = Path(__file__).parent.parent / "videos"
    videos = list(videos_dir.glob("*.mp4"))

    if not videos:
        print("未找到视频文件")
        return

    video_path = str(videos[0])
    print(f"测试视频: {video_path}")
    print("=" * 60)

    # 1. 元信息
    meta = get_video_meta(video_path)
    print(f"\n── 视频元信息 ──")
    print(f"  时长: {meta.duration:.1f}s")
    print(f"  分辨率: {meta.resolution}")
    print(f"  帧率: {meta.fps}fps")

    # 2. 场景检测
    scenes = detect_scene_changes(video_path, threshold=0.3)
    print(f"\n── 场景切换 ({len(scenes)} 个) ──")
    for s in scenes[:10]:
        print(f"  {s['time']:.1f}s")

    # 3. 关键帧提取
    output_dir = Path(__file__).parent / "outputs" / "test_frames"
    frames = extract_keyframes(video_path, str(output_dir), max_frames=5)
    print(f"\n── 关键帧 ({len(frames)} 张) ──")
    for f in frames:
        print(f"  {f}")

    print("\n✅ FFmpeg 测试完成!")


if __name__ == "__main__":
    main()
