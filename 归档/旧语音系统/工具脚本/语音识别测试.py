#!/usr/bin/env python3
"""
伴读书童AI - 语音识别测试脚本（Mac AVFoundation 版）

功能：
1. 使用 Mac AVFoundation 录制音频（解决 sounddevice 音量过低问题）
2. 可选：降噪、自动增益
3. 使用 Vosk 离线识别为文字
4. 输出识别结果

注意：
- 仅用于测试
- 需要麦克风权限
- 中文模型可选 small 或 large
"""

import json
import queue
import sys
import time
import wave
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd
from vosk import Model, KaldiRecognizer


def record_audio_avfoundation(duration_seconds=5, sample_rate=16000):
    """使用 Mac AVFoundation 录制音频"""
    import Foundation
    import AVFoundation

    print("=" * 60)
    print("伴读书童AI - 语音识别测试（AVFoundation 版）")
    print("=" * 60)
    print(f"录制时长: {duration_seconds} 秒")
    print(f"采样率: {sample_rate} Hz")
    print("准备录音，请对着麦克风说话...")

    output_path = "/tmp/stt_test_avfoundation.wav"

    settings = {
        AVFoundation.AVFormatIDKey: AVFoundation.kAudioFormatLinearPCM,
        AVFoundation.AVSampleRateKey: float(sample_rate),
        AVFoundation.AVNumberOfChannelsKey: 1,
        AVFoundation.AVLinearPCMBitDepthKey: 16,
        AVFoundation.AVLinearPCMIsFloatKey: False,
        AVFoundation.AVLinearPCMIsBigEndianKey: False,
    }

    url = Foundation.NSURL.fileURLWithPath_(output_path)
    recorder, error = AVFoundation.AVAudioRecorder.alloc().initWithURL_settings_error_(url, settings, None)

    if recorder is None:
        raise RuntimeError(f"AVAudioRecorder 初始化失败: {error}")

    print("🎙️ 开始录音...")
    recorder.recordForDuration_(duration_seconds)
    time.sleep(duration_seconds + 0.5)
    recorder.stop()
    print("✅ 录音结束")

    with wave.open(output_path, 'rb') as wf:
        data = wf.readframes(wf.getnframes())
        audio_data = np.frombuffer(data, dtype=np.int16)

    return audio_data, sample_rate


def record_audio_sounddevice(duration_seconds=5, sample_rate=16000):
    """使用 sounddevice 录制音频（备用方案）"""

    print("=" * 60)
    print("伴读书童AI - 语音识别测试（sounddevice 备用版）")
    print("=" * 60)
    print(f"录制时长: {duration_seconds} 秒")
    print(f"采样率: {sample_rate} Hz")
    print("准备录音，请对着麦克风说话...")

    audio_queue = queue.Queue()

    def callback(indata, frames, time, status):
        import numpy as np
        if status:
            print(f"录音状态: {status}", file=sys.stderr)
        audio_queue.put(np.array(indata, dtype='int16').copy())

    frames = []
    blocksize = 8000
    with sd.RawInputStream(
        samplerate=sample_rate,
        blocksize=blocksize,
        dtype='int16',
        channels=1,
        callback=callback
    ):
        print("🎙️ 开始录音...")
        for _ in range(int(duration_seconds * sample_rate / blocksize)):
            frames.append(audio_queue.get())
        print("✅ 录音结束")

    audio_data = np.concatenate(frames, axis=0)
    return audio_data, sample_rate


def save_wav(audio_data, sample_rate, save_path):
    """保存为 WAV 文件"""
    with wave.open(str(save_path), 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_data.tobytes())


def preprocess_audio(audio_data, sample_rate=16000, enable_denoise=True, enable_gain=True):
    """音频预处理：降噪 + 自动增益"""

    # 先归一化到 [-1, 1]
    processed = audio_data.astype(np.float32) / 32768.0

    # 自动增益
    if enable_gain:
        peak = np.max(np.abs(processed))
        if peak > 0:
            target_peak = 0.7
            gain = target_peak / peak
            gain = min(gain, 10.0)
            processed = processed * gain
            print(f"  自动增益: {gain:.2f}x")

    # 降噪
    if enable_denoise:
        try:
            import noisereduce as nr
            noise_sample_len = min(int(0.3 * sample_rate), len(processed) // 4)
            if noise_sample_len > 1000:
                noise_clip = processed[:noise_sample_len]
                processed = nr.reduce_noise(
                    y=processed,
                    y_noise=noise_clip,
                    sr=sample_rate,
                    prop_decrease=0.75
                )
                print("  降噪处理完成")
        except Exception as e:
            print(f"  降噪失败: {e}", file=sys.stderr)

    processed = np.clip(processed, -1.0, 1.0)
    return (processed * 32767).astype(np.int16)


def recognize_speech(audio_data, sample_rate, model_path):
    """使用 Vosk 识别语音"""

    print("\n正在识别...")
    model = Model(str(model_path))
    rec = KaldiRecognizer(model, sample_rate)
    rec.SetWords(True)

    audio_bytes = audio_data.tobytes()

    chunk_size = 4096
    for i in range(0, len(audio_bytes), chunk_size * 2):
        chunk = audio_bytes[i:i + chunk_size * 2]
        if len(chunk) == 0:
            break
        rec.AcceptWaveform(chunk)

    final_result = json.loads(rec.FinalResult())
    return final_result.get("text", "")


def main():
    project_root = Path(__file__).parent.parent
    save_dir = project_root / "工具脚本" / "语音识别测试录音"
    save_dir.mkdir(exist_ok=True)

    # 选择模型
    small_model = project_root / "书童程序" / "数据" / "模型" / "vosk" / "cn"
    large_model = project_root / "书童程序" / "数据" / "模型" / "vosk" / "cn-large"

    if large_model.exists():
        model_path = large_model
        model_name = "cn-large（大模型）"
    elif small_model.exists():
        model_path = small_model
        model_name = "cn（小模型）"
    else:
        print("❌ 没有找到 Vosk 中文模型")
        print(f"  小模型路径: {small_model}")
        print(f"  大模型路径: {large_model}")
        sys.exit(1)

    print(f"使用模型: {model_name}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    wav_path = save_dir / f"stt_test_{timestamp}.wav"
    processed_wav_path = save_dir / f"stt_test_{timestamp}_processed.wav"

    # 录音：优先使用 AVFoundation
    try:
        audio_data, sample_rate = record_audio_avfoundation(duration_seconds=5)
    except Exception as e:
        print(f"⚠️ AVFoundation 录音失败: {e}")
        print("尝试使用 sounddevice 备用方案...")
        try:
            audio_data, sample_rate = record_audio_sounddevice(duration_seconds=5)
        except Exception as e2:
            print(f"❌ 录音失败: {e2}")
            print("可能原因：麦克风权限未授权，或没有麦克风设备")
            sys.exit(1)

    # 保存原始录音
    save_wav(audio_data, sample_rate, wav_path)
    print(f"✅ 原始录音已保存: {wav_path}")
    print(f"  峰值: {np.max(np.abs(audio_data))}, RMS: {np.sqrt(np.mean(audio_data.astype(np.float32)**2)):.2f}")

    # 预处理
    print("\n正在进行音频预处理...")
    processed_audio = preprocess_audio(audio_data, sample_rate)
    save_wav(processed_audio, sample_rate, processed_wav_path)
    print(f"✅ 处理后录音已保存: {processed_wav_path}")

    # 识别
    try:
        text = recognize_speech(processed_audio, sample_rate, model_path)
        print(f"\n{'='*60}")
        print(f"识别结果: {text}")
        print(f"{'='*60}")
    except Exception as e:
        print(f"❌ 识别失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
