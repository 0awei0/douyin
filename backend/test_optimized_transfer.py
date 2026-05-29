"""优化版结构迁移测试

重新分析视频 → 优化迁移 → 生成视频
"""

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

    # 1. 分析样例视频（古装跳舞+CTA引导）
    source_path = str(videos_dir / "1.mp4")
    print(f"{'='*60}")
    print(f"Step 1: 分析样例视频 {source_path}")
    print("=" * 60)
    source = await analyze_video_structure(source_path)
    print(f"  时长: {source.meta.duration:.1f}s")
    print(f"  脚本: {len(source.script_structure)} 段")
    for sec in source.script_structure:
        print(f"    [{sec.type}] {sec.start_time:.1f}-{sec.end_time:.1f}s: {sec.text[:40]}")
    print(f"  叙事: {source.transferable_features.narrative_pattern}")
    print(f"  开头策略: {source.transferable_features.hook_strategy}")

    # 2. 分析目标视频（三姐妹操场跳手势舞）
    target_path = str(transfer_dir / "1.mp4")
    print(f"\n{'='*60}")
    print(f"Step 2: 分析目标视频 {target_path}")
    print("=" * 60)
    target = await analyze_video_structure(target_path)
    print(f"  时长: {target.meta.duration:.1f}s")
    print(f"  脚本: {len(target.script_structure)} 段")
    for sec in target.script_structure:
        print(f"    [{sec.type}] {sec.start_time:.1f}-{sec.end_time:.1f}s: {sec.text[:40]}")
    print(f"  镜头: {len(target.shots)} 个")
    for sh in target.shots:
        print(f"    [{sh.type}] {sh.start_time:.1f}-{sh.end_time:.1f}s: {sh.content[:50]}")

    # 3. 构建详细的目标描述（帮助AI更好理解素材）
    target_desc = f"""目标视频详细内容分析:

【基本信息】
- 时长: {target.meta.duration:.1f}秒, 分辨率: {target.meta.resolution}
- 整体风格: {target.packaging_structure.overall_visual_tone}

【脚本内容】
"""
    for sec in target.script_structure:
        target_desc += f"- [{sec.type}] {sec.start_time:.1f}-{sec.end_time:.1f}s: {sec.text}\n"
        target_desc += f"  作用: {sec.purpose}\n"

    target_desc += "\n【画面镜头】\n"
    for sh in target.shots:
        target_desc += f"- [{sh.type}] {sh.start_time:.1f}-{sh.end_time:.1f}s: {sh.content}\n"
        target_desc += f"  镜头运动: {sh.camera_move}\n"

    target_desc += f"""
【音频特点】
- BGM: {target.audio_structure.bgm.name}, 情绪: {target.audio_structure.bgm.mood}
- 旁白: {'有, ' + target.audio_structure.voiceover.style if target.audio_structure.voiceover.has else '无'}
- 卡节拍: {target.audio_structure.rhythm_sync}

【可迁移特征】
- 开头策略: {target.transferable_features.hook_strategy}
- 叙事模式: {target.transferable_features.narrative_pattern}
- 节奏模式: {target.transferable_features.pacing_pattern}
- 吸引力技巧: {', '.join(target.transferable_features.engagement_techniques)}

【素材亮点建议】
1. 开场(0-2s): 近景开场，主体离镜头近，适合作为hook
2. 手势舞(2-6s): 清晰近/中景手势动作，适合作为核心动作段
3. 延续动作(10-14s): 中景继续手势动作，可补强节奏
4. 远景(28-32s): 主体变小，适合承接近到远空间轨迹
5. 环境释放(48-56s): tiny/far 远景和操场环境，用于环境释放段

注意：16-24s 的走/跑只作为位置过渡，不作为核心爆款结构。"""

    # 4. 执行迁移（使用优化后的prompt）
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
    out_file = out_dir / "transfer_optimized.json"
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
            if shot.get('subtitle'):
                print(f"    字幕: {shot.get('subtitle')}")

    # 6. 生成视频（混入样例 BGM）
    print(f"\n{'='*60}")
    print("Step 4: 生成迁移视频（含 BGM）...")
    print("=" * 60)
    video_path = str(out_dir / "transfer_optimized.mp4")
    generate_transfer_video(
        transfer_result_path=str(out_file),
        target_video_path=target_path,
        output_path=video_path,
        use_ai_image=True,
        source_video_path=source_path,
    )
    size_mb = Path(video_path).stat().st_size / 1024 / 1024
    print(f"视频已生成: {video_path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    asyncio.run(main())
