"""测试结构迁移"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.services.video_analyzer import analyze_video_structure
from app.services.transfer import transfer_structure
from app.services.video_generator import generate_transfer_video


async def main():
    videos_dir = Path(__file__).parent.parent / "videos"
    transfer_dir = Path(__file__).parent.parent / "transfer-videos"

    # 1. 分析样例视频
    source_path = str(videos_dir / "1.mp4")
    print(f"{'='*60}")
    print(f"Step 1: 分析样例视频 {source_path}")
    print("=" * 60)
    source = await analyze_video_structure(source_path)
    print(f"  脚本: {len(source.script_structure)} 段, 镜头: {len(source.shots)} 个")
    print(f"  叙事: {source.transferable_features.narrative_pattern}")
    print(f"  时长: {source.meta.duration:.1f}s")

    # 2. 分析目标视频
    target_path = str(transfer_dir / "1.mp4")
    print(f"\n{'='*60}")
    print(f"Step 2: 分析目标视频 {target_path}")
    print("=" * 60)
    target = await analyze_video_structure(target_path)
    print(f"  时长: {target.meta.duration:.1f}s")
    print(f"  脚本: {len(target.script_structure)} 段")
    for sec in target.script_structure:
        print(f"    [{sec.type}] {sec.start_time:.1f}-{sec.end_time:.1f}s: {sec.text[:40]}")

    # 3. 构建目标描述
    target_desc = f"""目标视频内容描述:
- 时长: {target.meta.duration:.1f}秒, 分辨率: {target.meta.resolution}
- 画面内容: {target.shots[0].content if target.shots else '未知'}
- 旁白/对话: {'; '.join(sec.text for sec in target.script_structure if sec.text)}
- 整体风格: {target.packaging_structure.overall_visual_tone}"""

    # 4. 执行迁移
    print(f"\n{'='*60}")
    print("Step 3: 执行结构迁移...")
    print("=" * 60)
    result = await transfer_structure(
        source_structure=source,
        target_description=target_desc,
        target_meta={"duration": target.meta.duration, "resolution": target.meta.resolution},
        target_structure=target,
    )

    # 5. 保存结果
    out_dir = Path(__file__).parent / "outputs" / "transfer"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "transfer_1.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n迁移结果已保存到: {out_file}")

    # 打印结果摘要
    print(f"\n{'='*60}")
    print("迁移结果摘要")
    print("=" * 60)

    if "script" in result:
        total_dur = sum(seg.get("duration", 0) for seg in result["script"])
        print(f"\n新脚本 ({len(result['script'])} 段, 总时长 {total_dur:.1f}s):")
        for seg in result["script"]:
            print(f"  [{seg.get('type', '?')}] {seg.get('duration', '?')}s: {seg.get('text', '')[:50]}")

    if "storyboard" in result:
        print(f"\n新分镜 ({len(result['storyboard'])} 个):")
        for shot in result["storyboard"]:
            print(f"  #{shot.get('shot_number', '?')} [{shot.get('type', '?')}] {shot.get('duration', '?')}s: {shot.get('content', '')[:40]}")
            print(f"    source: {shot.get('source', '?')}")

    # 6. 生成视频
    print(f"\n{'='*60}")
    print("Step 4: 生成迁移视频...")
    print("=" * 60)
    video_path = str(out_dir / "transfer_1.mp4")
    generate_transfer_video(
        transfer_result_path=str(out_file),
        target_video_path=target_path,
        output_path=video_path,
        use_ai_image=True,
    )
    size_mb = Path(video_path).stat().st_size / 1024 / 1024
    print(f"视频已生成: {video_path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    asyncio.run(main())
