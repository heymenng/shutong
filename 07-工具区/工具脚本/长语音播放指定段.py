#!/usr/bin/env python3
"""伴读书童AI - 长语音指定段播放器

用途：
播放由 "长语音分段生成.py" 生成的某一段语音。

原则：
- 一次只播放一段，确保不超时
- 播放完成后立即退出
- 先停止其他正在播放的语音，避免重叠
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def stop_other_voices():
    """停止其他正在播放的语音"""
    try:
        subprocess.run(['pkill', '-f', 'afplay'], check=False, timeout=5)
    except Exception:
        pass


def play_segment(index, output_dir=None):
    """播放指定段的语音"""
    if output_dir is None:
        output_dir = PROJECT_ROOT / "05-交付区" / "临时交付" / "语音分段"
    output_dir = Path(output_dir)

    seg_path = output_dir / f"segment_{index:03d}.mp3"
    if not seg_path.exists():
        print(f"[语音] 第 {index} 段不存在: {seg_path}")
        return False

    # 停止其他语音
    stop_other_voices()

    print(f"[语音] 播放第 {index} 段...")
    try:
        subprocess.run(['afplay', str(seg_path)], check=False, timeout=90)
        print(f"[语音] 第 {index} 段播放完成")
        return True
    except subprocess.TimeoutExpired:
        print(f"[语音] 第 {index} 段播放超时")
        return False
    except Exception as e:
        print(f"[语音] 第 {index} 段播放失败: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("用法: python3 长语音播放指定段.py <段号> [输出目录]")
        print("示例: python3 长语音播放指定段.py 1")
        sys.exit(1)

    try:
        index = int(sys.argv[1])
    except ValueError:
        print("[语音] 段号必须是数字")
        sys.exit(1)

    output_dir = sys.argv[2] if len(sys.argv) > 2 else None
    play_segment(index, output_dir)


if __name__ == "__main__":
    main()
