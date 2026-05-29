"""测试所有视频"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from app.services.video_analyzer import analyze_video_structure


async def main():
    videos = list(Path(__file__).parent.parent.joinpath("videos").glob("*.mp4"))
    for v in videos:
        sep = "=" * 60
        print(f"\n{sep}")
        print(f"视频: {v.name}")
        print(sep)
        try:
            s = await analyze_video_structure(str(v))
            print(f"  时长: {s.meta.duration:.1f}s | 分辨率: {s.meta.resolution}")
            print(f"  脚本段落: {len(s.script_structure.sections)}")
            for sec in s.script_structure.sections:
                print(f"    [{sec.type.value}] {sec.start_time:.1f}-{sec.end_time:.1f}s: {sec.text[:60]}")
            print(f"  镜头数: {len(s.rhythm_structure.shots)}")
            if s.rhythm_structure.climax_position:
                print(f"  高潮位置: {s.rhythm_structure.climax_position:.0%}")
            out = Path(__file__).parent / "outputs" / f"{s.id}_structure.json"
            out.parent.mkdir(exist_ok=True)
            with open(out, "w") as f:
                json.dump(s.model_dump(), f, ensure_ascii=False, indent=2)
            print(f"  已保存: {out}")
        except Exception as e:
            print(f"  失败: {e}")

asyncio.run(main())
