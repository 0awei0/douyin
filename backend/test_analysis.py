"""分析所有示例视频并输出 JSON"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from app.services.video_analyzer import analyze_video_structure

VIDEOS_DIR = Path(__file__).parent.parent / "videos"
OUTPUT_DIR = Path(__file__).parent / "outputs" / "analysis"


async def main():
    videos = sorted(VIDEOS_DIR.glob("*.mp4"))
    if not videos:
        print("未找到视频文件")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for v in videos:
        print(f"\n{'=' * 60}")
        print(f"分析: {v.name}")
        print("=" * 60)
        try:
            structure = await analyze_video_structure(str(v))
            result = structure.model_dump()

            # 用视频名命名输出文件
            out_file = OUTPUT_DIR / f"{v.stem}.json"
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            print(f"\n  时长: {structure.meta.duration:.1f}s")
            print(f"  脚本段落: {len(structure.script_structure)}")
            for sec in structure.script_structure:
                print(f"    [{sec.type}] {sec.start_time:.1f}-{sec.end_time:.1f}s: {sec.text[:40]}")
            print(f"  镜头: {len(structure.shots)}")
            print(f"  叙事模式: {structure.transferable_features.narrative_pattern}")
            print(f"  开头策略: {structure.transferable_features.hook_strategy}")
            print(f"  保存到: {out_file}")

        except Exception as e:
            print(f"  失败: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
