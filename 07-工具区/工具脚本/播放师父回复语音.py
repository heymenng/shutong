#!/usr/bin/env python3
"""
播放师父回复语音

用法:
    .venv/bin/python3 07-工具区/工具脚本/播放师父回复语音.py "要播放的文本"

功能:
    1. 使用 edge_tts 生成中文语音
    2. 使用 afplay 完整播放
    3. 播放完成后自动清理临时文件
    4. 支持长文本分段播放（每段不超过 3000 字符）
"""

import asyncio
import edge_tts
import subprocess
import sys
import tempfile
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]


def split_text(text: str, max_len: int = 3000) -> list:
    """按句子分割长文本，每段不超过 max_len 字符。"""
    if len(text) <= max_len:
        return [text]
    
    sentences = text.replace('。', '。|').replace('？', '？|').replace('！', '！|').split('|')
    segments = []
    current = ""
    
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if len(current) + len(s) + 1 <= max_len:
            current += s
        else:
            if current:
                segments.append(current)
            current = s
    
    if current:
        segments.append(current)
    
    return segments


async def generate_and_play(text: str, voice: str = "zh-CN-XiaoyiNeural") -> None:
    """生成并播放单段语音。"""
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False, dir=str(project_root / "05-交付区" / "临时交付")) as tmp:
        tmp_path = Path(tmp.name)
    
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(tmp_path))
        subprocess.run(['afplay', str(tmp_path)], check=True)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


async def main():
    if len(sys.argv) < 2:
        print("用法: .venv/bin/python3 07-工具区/工具脚本/播放师父回复语音.py \"要播放的文本\"")
        sys.exit(1)
    
    text = sys.argv[1]
    segments = split_text(text)
    
    print(f"文本长度: {len(text)} 字符，分为 {len(segments)} 段播放")
    
    for i, segment in enumerate(segments, 1):
        print(f"正在播放第 {i}/{len(segments)} 段...")
        await generate_and_play(segment)
    
    print("语音播放完成")


if __name__ == "__main__":
    asyncio.run(main())
