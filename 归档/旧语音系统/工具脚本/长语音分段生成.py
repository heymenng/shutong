#!/usr/bin/env python3
"""伴读书童AI - 长语音分段生成器

用途：
将长文本自动分段，生成多个MP3文件。

原则：
- 只生成，不播放
- 每段控制在约30-40秒，确保单独播放不会超时
- 按语义断句，不切断句子
- 生成播放清单，方便后续逐段播放
"""

import asyncio
import edge_tts
import re
import sys
from pathlib import Path


def split_text(text, max_chars=100):
    """按语义把长文本切分成小段。"""
    # 先按完整句子切
    raw_sentences = re.split(r'([。！？.!?\n])', text)
    sentences = []
    current = ""
    for part in raw_sentences:
        if not part.strip():
            continue
        current += part
        if part in "。！？.!?\n":
            sentences.append(current.strip())
            current = ""
    if current.strip():
        sentences.append(current.strip())

    # 合并短句，控制每段长度
    segments = []
    buffer = ""
    for s in sentences:
        if len(buffer) + len(s) <= max_chars:
            buffer += s
        else:
            if buffer:
                segments.append(buffer)
            # 如果单句就超过限制，再按逗号切
            if len(s) > max_chars:
                clauses = re.split(r'([，,])', s)
                tmp = ""
                for c in clauses:
                    if len(tmp) + len(c) <= max_chars:
                        tmp += c
                    else:
                        if tmp:
                            segments.append(tmp)
                        tmp = c
                buffer = tmp if tmp else ""
            else:
                buffer = s
    if buffer:
        segments.append(buffer)

    return [s.strip() for s in segments if s.strip()]


async def generate_segment(text, voice, output_path):
    """生成单段语音"""
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(output_path))


async def main():
    if len(sys.argv) < 2:
        print("用法: python3 长语音分段生成.py '要播放的长文本' [输出目录]")
        sys.exit(1)

    text = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    if output_dir is None:
        output_dir = Path(__file__).parent.parent / "临时交付" / "语音分段"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 清理旧的分段文件
    for old in output_dir.glob("segment_*.mp3"):
        old.unlink()

    voice = "zh-CN-XiaoyiNeural"
    segments = split_text(text, max_chars=100)

    if not segments:
        print("[语音] 没有可生成的内容")
        return

    print(f"[语音] 长文本已切分为 {len(segments)} 段")

    for i, segment in enumerate(segments, 1):
        seg_path = output_dir / f"segment_{i:03d}.mp3"
        try:
            await generate_segment(segment, voice, seg_path)
            print(f"[语音] 已生成第 {i}/{len(segments)} 段: {seg_path.name}")
        except Exception as e:
            print(f"[语音] 第{i}段生成失败: {e}")

    # 生成播放清单
    playlist_path = output_dir / "播放清单.txt"
    with open(playlist_path, 'w', encoding='utf-8') as f:
        for i in range(1, len(segments) + 1):
            seg_path = output_dir / f"segment_{i:03d}.mp3"
            f.write(f"{seg_path}\n")

    print(f"\n[语音] 生成完成，共 {len(segments)} 段")
    print(f"[语音] 播放清单: {playlist_path}")
    print(f"[语音] 请逐段播放，例如: python3 工具脚本/长语音播放指定段.py 1")


if __name__ == "__main__":
    asyncio.run(main())
