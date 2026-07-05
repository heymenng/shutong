#!/usr/bin/env python3
"""伴读书童AI - 长语音分段播放工具

用途：
将长文本自动分段，生成多个MP3文件，并顺序完整播放。

原则：
- 每段控制在可稳定播放的长度内
- 按语义断句，不切断句子
- 顺序播放，确保完整
- 播放失败时记录并继续
"""

import asyncio
import edge_tts
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def split_text(text, max_chars=120):
    """按语义把长文本切分成小段。
    
    优先按句号、问号、感叹号、换行切分，
    如果单句仍超过 max_chars，再按逗号切分。
    """
    import re
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
                if tmp:
                    buffer = tmp
                else:
                    buffer = ""
            else:
                buffer = s
    if buffer:
        segments.append(buffer)
    
    return [s.strip() for s in segments if s.strip()]


async def generate_segment(text, voice, output_path):
    """生成单段语音"""
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(output_path))


def play_segment(path, timeout=60):
    """播放单段语音，超时则跳过"""
    try:
        subprocess.run(
            ['afplay', str(path)],
            check=False,
            timeout=timeout
        )
        return True
    except subprocess.TimeoutExpired:
        print(f"[语音] 分段播放超时: {path.name}")
        return False
    except Exception as e:
        print(f"[语音] 分段播放失败: {path.name}, {e}")
        return False


def play_long_text(text, voice="zh-CN-XiaoyiNeural", max_chars=120, output_dir=None):
    """主入口：分段生成并完整播放长文本"""
    if output_dir is None:
        output_dir = PROJECT_ROOT / "05-交付区" / "临时交付" / "语音分段"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    segments = split_text(text, max_chars)
    if not segments:
        print("[语音] 没有可播放的内容")
        return
    
    print(f"[语音] 长文本已切分为 {len(segments)} 段")
    
    played_count = 0
    for i, segment in enumerate(segments, 1):
        seg_path = output_dir / f"segment_{i:03d}.mp3"
        
        # 生成
        try:
            asyncio.run(generate_segment(segment, voice, seg_path))
        except Exception as e:
            print(f"[语音] 第{i}段生成失败: {e}")
            continue
        
        # 播放
        print(f"[语音] 播放第 {i}/{len(segments)} 段")
        if play_segment(seg_path):
            played_count += 1
    
    print(f"[语音] 播放完成: {played_count}/{len(segments)} 段")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 长语音分段播放.py '要播放的长文本'")
        sys.exit(1)
    
    text = sys.argv[1]
    play_long_text(text)
