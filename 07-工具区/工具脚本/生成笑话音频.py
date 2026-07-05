#!/usr/bin/env python3
"""把笑话库 .md 文本按角色合成多音色音频（edge-tts）

用法：
    .venv/bin/python 07-工具区/工具脚本/生成笑话音频.py \
        "05-交付区/产品交付/书童音频节目/笑话库/按类型/方言相声/三个书童拜师父.md" \
        --out "05-交付区/产品交付/书童音频节目/音频节目/三个书童拜师父.mp3" \
        --play
"""

import argparse
import asyncio
import re
import sys
import tempfile
from pathlib import Path

import edge_tts
from pydub import AudioSegment


# 角色 -> edge-tts 声音映射
# 按最新《角色声音分配表》：东北/陕西/台湾书童用女声；普通话成人用男声；伴读书童用女声
VOICE_MAP = {
    "伴读书童": "zh-CN-XiaoxiaoNeural",
    "东北书童": "zh-CN-liaoning-XiaobeiNeural",
    "台湾书童": "zh-TW-HsiaoChenNeural",
    "陕西书童": "zh-CN-shaanxi-XiaoniNeural",
    "师父": "zh-CN-YunjianNeural",
    "禅师": "zh-CN-YunjianNeural",
    "佛印": "zh-CN-YunjianNeural",
    "王阳明": "zh-CN-YunjianNeural",
    "庄子": "zh-CN-YunjianNeural",
    "惠子": "zh-CN-YunxiNeural",
    "老板": "zh-CN-YunxiNeural",
    "爸爸": "zh-CN-YunxiNeural",
    "妈妈": "zh-CN-XiaoyiNeural",
    "小明": "zh-CN-YunyangNeural",
    "小李": "zh-CN-YunyangNeural",
    "王爷爷": "zh-CN-YunjianNeural",
    "李奶奶": "zh-CN-XiaoyiNeural",
}

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
DEFAULT_ROLE = "伴读书童"


def parse_markdown(md_path: Path):
    """解析 .md 文件，返回 (role, text) 列表"""
    text = md_path.read_text(encoding="utf-8")
    # 去掉 front matter
    text = re.sub(r"^---\n.*?---\n", "", text, flags=re.S)
    # 去掉标题行 # ...
    text = re.sub(r"^#.*$", "", text, flags=re.M)
    # 去掉结尾的笑点/寓意区块（保留到 --- 之前的对话）
    parts = text.split("\n---\n")
    body = parts[0] if parts else text

    segments = []
    current_role = DEFAULT_ROLE
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        # 匹配 **角色**：台词
        m = re.match(r"^\*\*(.+?)\*\*[\s：:](.*)$", line)
        if m:
            current_role = m.group(1).strip()
            content = m.group(2).strip()
            # 过滤括号里的舞台提示，不读出来（保留可读性）
            content = re.sub(r"[（(].*?[）)]", " ", content)
            content = content.strip()
            if content:
                segments.append((current_role, content))
        else:
            # 无角色名的行当作旁白/舞台说明，默认伴读书童读
            cleaned = re.sub(r"[（(].*?[）)]", " ", line).strip()
            if cleaned:
                segments.append((DEFAULT_ROLE, cleaned))
    return segments


async def synthesize_segment(role: str, text: str, out_path: Path, retries: int = 3):
    """合成单段音频，带重试"""
    voice = VOICE_MAP.get(role, DEFAULT_VOICE)
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(str(out_path))
            return
        except Exception as e:
            last_err = e
            print(f"  [{role}] 合成失败（第 {attempt}/{retries} 次）: {e}")
            await asyncio.sleep(1.5 * attempt)
    raise last_err


async def build_audio(segments, out_path: Path, play: bool = False):
    """生成并拼接音频"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    combined = AudioSegment.empty()
    silence = AudioSegment.silent(duration=400)

    with tempfile.TemporaryDirectory() as tmpdir:
        for i, (role, text) in enumerate(segments, 1):
            seg_path = Path(tmpdir) / f"seg_{i:03d}.mp3"
            print(f"[{i}/{len(segments)}] {role}: {text[:30]}...")
            await synthesize_segment(role, text, seg_path)
            combined += AudioSegment.from_mp3(seg_path) + silence

    # 去掉最后一段沉默
    if len(combined) > len(silence):
        combined = combined[:-len(silence)]
    combined.export(out_path, format="mp3")
    print(f"\n已生成：{out_path}")

    if play:
        import subprocess
        subprocess.run(["afplay", str(out_path)], check=False)


def main():
    parser = argparse.ArgumentParser(description="把笑话库文本生成多角色音频")
    parser.add_argument("md_path", help="笑话 markdown 文件路径")
    parser.add_argument("--out", "-o", help="输出 mp3 路径")
    parser.add_argument("--play", action="store_true", help="生成后播放")
    args = parser.parse_args()

    md_path = Path(args.md_path)
    if not md_path.exists():
        print(f"文件不存在: {md_path}", file=sys.stderr)
        sys.exit(1)

    if args.out:
        out_path = Path(args.out)
    else:
        stem = md_path.stem
        out_path = md_path.parent / f"{stem}.mp3"

    segments = parse_markdown(md_path)
    if not segments:
        print("未解析到可合成内容", file=sys.stderr)
        sys.exit(1)

    print(f"共 {len(segments)} 段台词，角色分布：")
    roles = sorted(set(r for r, _ in segments))
    for r in roles:
        print(f"  - {r}: {VOICE_MAP.get(r, DEFAULT_VOICE)}")

    asyncio.run(build_audio(segments, out_path, args.play))


if __name__ == "__main__":
    main()
