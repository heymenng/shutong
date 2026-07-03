"""伴读书童AI - 东北书童与台湾书童相声生成器

用法：
    .venv/bin/python -m 书童程序.工具.生成相声 --topic 写作业 --play
    .venv/bin/python -m 书童程序.工具.生成相声 --topic 起床 --duration 2 --output /tmp/相声.mp3

Python 调用：
    from 书童程序.工具.生成相声 import generate_comedy_sketch
    path = generate_comedy_sketch(topic="吃饭", duration_minutes=2, play=True)
"""

import argparse
import asyncio
import edge_tts
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# 把项目根目录加入路径
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from 书童程序.核心.语言模型 import chat_completion
from 书童程序.核心.讯飞超拟人语音 import XfyunOralTTS


PROMPT_FILE = PROJECT_ROOT / "训练素材" / "提示词" / "东北台湾书童相声提示词.md"
OUTPUT_DIR = PROJECT_ROOT / "临时交付"

VOICE_MAP = {
    "东北书童": "zh-CN-liaoning-XiaobeiNeural",
    "台湾书童": "zh-TW-HsiaoYuNeural",
    "伴读书童": "xfyun_oral",
    "三人齐声": "xfyun_oral",
}

DEFAULT_TOPICS = [
    "写作业",
    "起床",
    "吃饭",
    "运动",
    "睡前故事",
    "考试",
    "玩手机",
    "吃饺子",
    "讲道理",
    "夏天太热",
]


def load_prompt() -> str:
    """加载相声提示词"""
    if PROMPT_FILE.exists():
        return PROMPT_FILE.read_text(encoding="utf-8")
    return ""


def build_generation_prompt(topic: str, duration_minutes: int) -> str:
    """构建生成脚本的提示词"""
    base_prompt = load_prompt()
    return f"""{base_prompt}

---

请根据上面的角色设定，创作一段关于「{topic}」的相声/笑话对话。

要求：
- 时长约 {duration_minutes} 分钟
- 只有东北书童（老铁）和台湾书童（软软）两个人对话
- 不要旁白，不要场景描述
- 格式严格如下：

东北书童：
（台词，可以带东北口语）

台湾书童：
（台词，可以带台湾语气）

东北书童：
...

台湾书童：
...

- 内容要轻松、有趣、干净，适合给孩子和师父听
- 结尾要有笑点或温馨收尾
"""


def parse_script(script_text: str) -> list[tuple[str, str]]:
    """解析脚本为（说话人，台词）列表"""
    pattern = r"(?m)^(?P<speaker>东北书童|台湾书童|伴读书童|三人齐声)[：:]\s*\n(?P<text>.*?)(?=\n(?:东北书童|台湾书童|伴读书童|三人齐声)[：:]\s*\n|$)"
    matches = re.finditer(pattern, script_text, re.DOTALL)
    segments = []
    for m in matches:
        speaker = m.group("speaker")
        text = m.group("text").strip()
        text = re.sub(r"\n+", " ", text)
        if text:
            segments.append((speaker, text))
    return segments


async def generate_edge_tts_audio(text: str, voice: str, output_path: Path) -> bool:
    """使用 Edge-TTS 生成音频"""
    for attempt in range(3):
        try:
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(str(output_path))
            return True
        except Exception as e:
            print(f"  Edge-TTS 尝试 {attempt + 1} 失败: {e}")
            await asyncio.sleep(1)
    return False


def generate_xfyun_audio(text: str, output_path: Path) -> bool:
    """使用讯飞超拟人 TTS 生成音频"""
    tts = XfyunOralTTS()
    audio = tts.synthesize_to_bytes(text)
    if audio:
        output_path.write_bytes(audio)
        return True
    print(f"  讯飞生成失败: {tts.error_msg}")
    return False


async def generate_audio_segments(segments: list[tuple[str, str]], output_dir: Path) -> list[Path]:
    """为每个片段生成音频"""
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_files = []

    for i, (speaker, text) in enumerate(segments):
        voice = VOICE_MAP.get(speaker, "zh-CN-XiaoxiaoNeural")
        output_path = output_dir / f"相声片段_{i:03d}_{speaker}.mp3"
        print(f"[{i + 1}/{len(segments)}] {speaker}: {text[:40]}...")

        if voice == "xfyun_oral":
            success = generate_xfyun_audio(text, output_path)
        else:
            success = await generate_edge_tts_audio(text, voice, output_path)
            await asyncio.sleep(0.3)

        if success:
            audio_files.append(output_path)
        else:
            print(f"  {speaker} 生成失败，跳过")

    return audio_files


def merge_audio_files(audio_files: list[Path], output_path: Path) -> bool:
    """合并音频文件"""
    try:
        from pydub import AudioSegment

        combined = AudioSegment.empty()
        for path in audio_files:
            audio = AudioSegment.from_mp3(str(path))
            combined += audio
            combined += AudioSegment.silent(duration=600)

        combined.export(str(output_path), format="mp3")
        print(f"\n合并完成: {output_path}")
        print(f"总时长: {len(combined) / 1000:.1f} 秒")
        return True
    except ImportError:
        print("\n警告：未安装 pydub，无法合并音频。片段文件已生成：")
        for f in audio_files:
            print(f"  {f}")
        return False
    except Exception as e:
        print(f"合并音频失败: {e}")
        return False


def generate_script(topic: str, duration_minutes: int) -> str:
    """调用 LLM 生成相声脚本"""
    prompt = build_generation_prompt(topic, duration_minutes)
    messages = [
        {"role": "system", "content": "你是一位擅长写轻松幽默对话的编剧。"},
        {"role": "user", "content": prompt},
    ]
    return chat_completion(messages, max_tokens=2000)


def generate_comedy_sketch(
    topic: Optional[str] = None,
    duration_minutes: int = 2,
    play: bool = False,
    output_path: Optional[str] = None,
) -> Optional[Path]:
    """
    生成东北书童与台湾书童的相声音频

    Args:
        topic: 相声主题，如"写作业"、"起床"等。为空则随机选择。
        duration_minutes: 相声时长（分钟），默认2分钟
        play: 生成后是否立即播放
        output_path: 输出文件路径，为空则自动生成

    Returns:
        生成的音频文件路径，失败返回 None
    """
    import random

    if not topic:
        topic = random.choice(DEFAULT_TOPICS)

    print(f"\n=== 生成相声：{topic}（约 {duration_minutes} 分钟）===\n")

    # 生成脚本
    script_text = generate_script(topic, duration_minutes)

    if not script_text or "失败" in script_text:
        print(f"脚本生成失败: {script_text}")
        return None

    print("生成的脚本：")
    print("-" * 40)
    print(script_text)
    print("-" * 40)

    # 解析脚本
    segments = parse_script(script_text)
    if not segments:
        print("未能解析出对话片段，请检查脚本格式")
        return None

    print(f"\n解析到 {len(segments)} 个对话片段")

    # 生成音频
    timestamp = datetime.now().strftime("%m%d_%H%M%S")
    work_dir = OUTPUT_DIR / f"相声_{topic}_{timestamp}"
    audio_files = asyncio.run(generate_audio_segments(segments, work_dir))

    if not audio_files:
        print("没有生成任何音频")
        return None

    # 合并音频
    if output_path:
        final_path = Path(output_path)
    else:
        final_path = OUTPUT_DIR / f"东北台湾书童相声_{topic}_{timestamp}.mp3"

    if merge_audio_files(audio_files, final_path):
        if play:
            play_audio(final_path)
        return final_path

    return None


def play_audio(audio_path: Path):
    """播放音频"""
    if sys.platform == "darwin":
        subprocess.run(["afplay", str(audio_path)], check=False)
    elif sys.platform == "linux":
        for cmd in [["ffplay", "-autoexit", "-nodisp", str(audio_path)],
                    ["mpg123", str(audio_path)]]:
            try:
                subprocess.run(cmd, check=False)
                return
            except Exception:
                continue
    else:
        subprocess.run(["start", str(audio_path)], shell=True, check=False)


def main():
    parser = argparse.ArgumentParser(description="东北书童与台湾书童相声生成器")
    parser.add_argument("--topic", "-t", type=str, default=None, help="相声主题，如：写作业、起床")
    parser.add_argument("--duration", "-d", type=int, default=2, help="相声时长（分钟）")
    parser.add_argument("--play", "-p", action="store_true", help="生成后是否播放")
    parser.add_argument("--output", "-o", type=str, default=None, help="输出文件路径")
    args = parser.parse_args()

    generate_comedy_sketch(
        topic=args.topic,
        duration_minutes=args.duration,
        play=args.play,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
