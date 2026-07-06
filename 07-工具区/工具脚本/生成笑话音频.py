#!/usr/bin/env python3
"""把笑话库 .md 文本按角色合成多音色音频

支持双后端：
- 讯飞超拟人语音（xfyun_oral）：用于已有授权音色的角色
- edge-tts：用于方言角色、童声、以及讯飞失败时的回退

用法：
    .venv/bin/python 07-工具区/工具脚本/生成笑话音频.py \
        "05-交付区/产品交付/书童音频节目/笑话库/按类型/方言相声/三个书童拜师父.md" \
        --out "05-交付区/产品交付/书童音频节目/音频节目/三个书童拜师父.mp3" \
        --play
"""

import argparse
import asyncio
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import edge_tts
from pydub import AudioSegment

# 把项目根目录加入路径，以便导入讯飞模块
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "03-引擎区"))

from 书童程序.核心.讯飞超拟人语音 import XfyunOralTTS  # noqa: E402
from 书童程序.工具.项目根目录 import get_project_root  # noqa: E402
from 书童程序.配置 import CONFIG  # noqa: E402


PROJECT_ROOT = get_project_root()


# 讯飞超拟人音色：只使用已授权音色
# 当前已开通：天津少女、聆伯松（男）、凌语嫣、惠芳女、凌小月、凌小璇、凌小雪、灵晓棠、灵玉照、紫金、古风仙女
XF_VOICE_MAP = {
    # 伴读书童 / 小书童：项目默认天津少女
    "伴读书童": "x6_tianjingshaonv_pro",
    # 成人男性角色统一用聆伯松（沉稳男声）
    "师父": "x6_lingbosong_pro",
    "禅师": "x6_lingbosong_pro",
    "王阳明": "x6_lingbosong_pro",
    "庄子": "x6_lingbosong_pro",
    "佛印": "x6_lingbosong_pro",
    "王爷爷": "x6_lingbosong_pro",
    "爸爸": "x6_lingbosong_pro",
    "老板": "x6_lingbosong_pro",
    # 成人女性角色
    "妈妈": "x6_lingyuyan_pro",
    "李奶奶": "x6_huifangnv_pro",
}

# edge-tts 音色：方言、童声、以及讯飞未覆盖角色的回退
EDGE_VOICE_MAP = {
    "伴读书童": "zh-CN-XiaoxiaoNeural",
    "东北书童": "zh-CN-liaoning-XiaobeiNeural",
    "台湾书童": "zh-TW-HsiaoChenNeural",
    "陕西书童": "zh-CN-shaanxi-XiaoniNeural",
    "师父": "zh-CN-YunjianNeural",
    "禅师": "zh-CN-YunjianNeural",
    "王阳明": "zh-CN-YunjianNeural",
    "庄子": "zh-CN-YunjianNeural",
    "佛印": "zh-CN-YunjianNeural",
    "惠子": "zh-CN-YunxiNeural",
    "老板": "zh-CN-YunxiNeural",
    "爸爸": "zh-CN-YunxiNeural",
    "妈妈": "zh-CN-XiaoyiNeural",
    "小明": "zh-CN-YunyangNeural",
    "小李": "zh-CN-YunyangNeural",
    "王爷爷": "zh-CN-YunjianNeural",
    "李奶奶": "zh-CN-XiaoyiNeural",
}

DEFAULT_EDGE_VOICE = "zh-CN-XiaoxiaoNeural"


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
    current_role = "伴读书童"
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
                segments.append((current_role, cleaned))
    return segments


async def synthesize_edge(text: str, voice: str, out_path: Path):
    """使用 edge-tts 合成音频"""
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(out_path))


def synthesize_xfyun(text: str, voice: str, out_path: Path) -> bool:
    """使用讯飞超拟人语音合成音频；成功返回 True"""
    original_voice = CONFIG.get("voice_name")
    try:
        CONFIG["voice_name"] = voice
        tts = XfyunOralTTS()
        audio = tts.synthesize_to_bytes(text)
        if audio:
            out_path.write_bytes(audio)
            return True
        print(f"    [讯飞] 合成失败: {tts.error_msg}")
        return False
    except Exception as e:
        print(f"    [讯飞] 异常: {e}")
        return False
    finally:
        CONFIG["voice_name"] = original_voice


async def synthesize_segment(role: str, text: str, out_path: Path, retries: int = 3):
    """合成单段音频，优先讯飞，失败回退 edge-tts"""
    xfyun_voice = XF_VOICE_MAP.get(role)
    edge_voice = EDGE_VOICE_MAP.get(role, DEFAULT_EDGE_VOICE)

    if xfyun_voice:
        for attempt in range(1, retries + 1):
            print(f"  [{role}] 讯飞 {xfyun_voice} 合成（{attempt}/{retries}）...")
            if synthesize_xfyun(text, xfyun_voice, out_path):
                return
            await asyncio.sleep(1.0 * attempt)
        print(f"  [{role}] 讯飞连续失败，回退 edge-tts: {edge_voice}")

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            await synthesize_edge(text, edge_voice, out_path)
            return
        except Exception as e:
            last_err = e
            print(f"  [{role}] edge-tts 合成失败（{attempt}/{retries}）: {e}")
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
        xf = XF_VOICE_MAP.get(r)
        edge = EDGE_VOICE_MAP.get(r, DEFAULT_EDGE_VOICE)
        backend = f"讯飞 {xf}" if xf else f"edge-tts {edge}"
        print(f"  - {r}: {backend}")

    asyncio.run(build_audio(segments, out_path, args.play))


if __name__ == "__main__":
    main()
