"""
伴读书童AI - 音频格式转换工具

用于把书童本地 TTS 生成的 MP3/WAV 转换成 G1 控制服务要求的 PCM 格式：
    s16le / 16000Hz / mono

G1 /audio/pcm 接口要求：
    - 格式：16-bit signed PCM, little-endian
    - 采样率：16000 Hz
    - 声道：单声道 (mono)
    - 单次请求最大：192000 bytes（约 6 秒）
"""

import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Union


def convert_to_g1_pcm(input_path: Union[str, Path], output_path: Optional[Union[str, Path]] = None) -> bytes:
    """
    把输入音频文件转换为 G1 可用的 PCM bytes。

    参数：
        input_path: 输入音频文件路径（mp3/wav 等）
        output_path: 可选，输出 pcm 文件路径；不指定则只返回 bytes

    返回：
        PCM 音频 bytes（s16le/16000Hz/mono）
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"音频文件不存在: {input_path}")

    # 如果没有指定输出路径，使用临时文件
    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".pcm", delete=False)
        output_path = Path(tmp.name)
        tmp.close()
        cleanup = True
    else:
        output_path = Path(output_path)
        cleanup = False

    try:
        cmd = [
            "ffmpeg",
            "-y",  # 覆盖输出
            "-i", str(input_path),
            "-f", "s16le",
            "-ar", "16000",
            "-ac", "1",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg 转换失败: {result.stderr}")

        pcm_bytes = output_path.read_bytes()
        return pcm_bytes
    finally:
        if cleanup and output_path.exists():
            output_path.unlink()


def check_ffmpeg() -> bool:
    """检查系统是否安装了 ffmpeg"""
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def split_pcm_chunks(pcm_bytes: bytes, chunk_seconds: float = 1.0) -> list:
    """
    把 PCM bytes 按时间分块，方便流式上传到 G1。

    参数：
        pcm_bytes: s16le/16000Hz/mono 的 PCM 数据
        chunk_seconds: 每块时长（秒）

    返回：
        PCM 块列表（bytes 列表）
    """
    bytes_per_second = 16000 * 2  # 16bit = 2 bytes per sample
    chunk_size = int(bytes_per_second * chunk_seconds)
    chunks = []
    for i in range(0, len(pcm_bytes), chunk_size):
        chunks.append(pcm_bytes[i:i + chunk_size])
    return chunks


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python 音频格式转换.py <输入音频文件> [输出pcm文件]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    if not check_ffmpeg():
        print("错误：未找到 ffmpeg，请先安装")
        sys.exit(1)

    pcm = convert_to_g1_pcm(input_file, output_file)
    print(f"转换完成，PCM 大小: {len(pcm)} bytes")
    if output_file:
        print(f"已保存: {output_file}")
