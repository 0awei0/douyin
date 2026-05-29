"""测试视频生成 - 直接用已有迁移结果"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.services.video_generator import generate_transfer_video


def main():
    transfer_json = Path(__file__).parent / "outputs" / "transfer" / "transfer_1.json"
    target_video = Path(__file__).parent.parent / "transfer-videos" / "1.mp4"
    output_video = Path(__file__).parent / "outputs" / "transfer" / "transfer_1.mp4"

    if not transfer_json.exists():
        print(f"迁移结果不存在: {transfer_json}")
        return
    if not target_video.exists():
        print(f"目标视频不存在: {target_video}")
        return

    print(f"迁移结果: {transfer_json}")
    print(f"目标视频: {target_video}")
    print(f"输出视频: {output_video}")
    print("=" * 60)
    print("开始生成视频...")

    result = generate_transfer_video(
        transfer_result_path=str(transfer_json),
        target_video_path=str(target_video),
        output_path=str(output_video),
        use_ai_image=False,  # 快速测试不用 AI 生图
    )

    size_mb = output_video.stat().st_size / 1024 / 1024
    print(f"\n生成完成: {result}")
    print(f"文件大小: {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
