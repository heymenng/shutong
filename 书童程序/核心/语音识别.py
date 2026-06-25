"""伴读书童AI - 语音识别方案（技术层）

职责：
1. STT（Speech-to-Text）：把孩子说的话转成文字
2. 语音唤醒：检测唤醒词"书童"
3. 语音打断：孩子说"停"就停止
4. 方言适配：支持粤语/四川话等
5. 噪音过滤：户外/运动场景

技术选型：
- 本地部署：Whisper（默认，已集成） / Vosk / FunASR / Sherpa
- 云端API：百度/讯飞/阿里
- 录音方案：Mac 使用 AVFoundation（解决 sounddevice 音量过低问题）
          其他平台使用 sounddevice
"""

import json
import os
import queue
import re
import sys
import tempfile
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np


class SpeechRecognition:
    """
    语音识别引擎
    
    提供STT、唤醒词检测、语音打断等功能。
    """
    
    def __init__(self, config=None):
        self.config = config or {}
        self.wake_words = ["书童", "小书童", "书童在吗", "书童书童"]
        self.stop_words = ["停", "停止", "别说了", "安静", "闭嘴"]
        self.engine = None
        self.model = None
        self.engine_name = self.config.get("stt_engine", "simulation")
        self.recorder_name = self.config.get("stt_recorder", "sounddevice")
        self.sample_rate = self.config.get("stt_sample_rate", 16000)
        self.record_seconds = self.config.get("stt_record_seconds", 5)
        self.enable_denoise = self.config.get("stt_enable_denoise", True)
        self.enable_gain = self.config.get("stt_enable_gain", True)
        
        # 尝试加载真实引擎
        self._init_engine()
    
    def _init_engine(self):
        """初始化识别引擎"""
        if self.engine_name == "vosk":
            self._init_vosk()
        elif self.engine_name == "whisper":
            self._init_whisper()
        elif self.engine_name == "funasr":
            self._init_funasr()
        elif self.engine_name == "baidu":
            self._init_baidu()
        else:
            print("[STT] 使用模拟模式（无真实语音识别）")
            print("[STT] 如需真实识别，请配置 stt_engine='whisper' 或 'vosk'")
    
    def _init_vosk(self):
        """初始化 Vosk 离线识别引擎"""
        try:
            from vosk import Model, KaldiRecognizer
            
            model_dir = Path(self.config.get("vosk_model_dir", "书童程序/数据/模型/vosk"))
            model_name = self.config.get("vosk_model_name", "cn")
            model_path = model_dir / model_name
            
            if not model_path.exists():
                # 尝试小模型作为回退
                fallback_path = model_dir / "cn"
                if fallback_path.exists():
                    print(f"[STT] 未找到模型 {model_name}，使用 cn 小模型")
                    model_path = fallback_path
                else:
                    print(f"[STT] ❌ Vosk 模型不存在: {model_path}")
                    print("[STT] 请先下载中文模型到该路径")
                    self.engine_name = "simulation"
                    return
            
            self.model = Model(str(model_path))
            self.engine = "vosk"
            print(f"[STT] ✅ Vosk 模型已加载: {model_path.name}")
            
        except ImportError:
            print("[STT] vosk 未安装，请运行: pip install vosk")
            self.engine_name = "simulation"
        except Exception as e:
            print(f"[STT] Vosk 加载失败: {e}")
            self.engine_name = "simulation"
    
    def _init_whisper(self):
        """初始化Whisper"""
        try:
            import whisper
            model_size = self.config.get("whisper_model", "base")
            self.engine = whisper.load_model(model_size)
            print(f"[STT] Whisper {model_size} 模型已加载")
        except ImportError:
            print("[STT] whisper 未安装，请运行: pip install openai-whisper")
            self.engine = None
    
    def _init_funasr(self):
        """初始化FunASR（阿里巴巴）"""
        try:
            from funasr import AutoModel
            self.engine = AutoModel(model="paraformer-zh")
            print("[STT] FunASR 模型已加载")
        except ImportError:
            print("[STT] funasr 未安装，请运行: pip install funasr")
            self.engine = None
    
    def _init_baidu(self):
        """初始化百度语音识别"""
        self.baidu_app_id = self.config.get("baidu_app_id", "")
        self.baidu_api_key = self.config.get("baidu_api_key", "")
        self.baidu_secret_key = self.config.get("baidu_secret_key", "")
        
        if self.baidu_api_key and self.baidu_secret_key:
            print("[STT] 百度语音API已配置")
        else:
            print("[STT] 百度语音API未配置，请在配置中填写app_id/api_key/secret_key")
    
    # ═══════════════════════════════════════════
    # 录音功能
    # ═══════════════════════════════════════════
    
    def record_audio(self, duration_seconds=None, sample_rate=None, use_vad=True) -> np.ndarray:
        """
        录制音频
        
        Args:
            duration_seconds: 录音时长（秒）
            sample_rate: 采样率
            use_vad: 是否使用语音活动检测，自动在说话结束后停止
        
        Returns:
            numpy int16 数组
        """
        sr = sample_rate or self.sample_rate
        
        if use_vad:
            # VAD 模式：录最长时间，但自动剪切到实际说话结束点
            max_duration = duration_seconds or self.record_seconds
            # 保证至少给 VAD 一个合理的采样窗口，但不强制最小值
            if max_duration < 3:
                max_duration = 3
            if self.recorder_name == "avfoundation" and sys.platform == "darwin":
                audio = self._record_avfoundation(max_duration, sr)
            else:
                audio = self._record_sounddevice(max_duration, sr)
            return self._apply_vad(audio, sr)
        else:
            duration = duration_seconds or self.record_seconds
            if duration < 3:
                duration = 3
            if self.recorder_name == "avfoundation" and sys.platform == "darwin":
                return self._record_avfoundation(duration, sr)
            else:
                return self._record_sounddevice(duration, sr)
    
    def _apply_vad(self, audio_data: np.ndarray, sample_rate: int) -> np.ndarray:
        """
        应用简单能量阈值 VAD，剪切掉尾端静音
        
        逻辑：
        - 从后往前找最后一个音量高于阈值的点
        - 在该点后加 0.5 秒留白
        - 返回剪切后的音频
        """
        if len(audio_data) == 0:
            return audio_data
        
        # 参数
        frame_size = int(0.1 * sample_rate)  # 100ms 一帧
        threshold = 100  # RMS 能量阈值，低于此认为是静音
        # 师父要求：真正不说话 2 秒后切换。
        # 但说话中的正常换气/停顿可能持续 1 秒左右，所以设为 2.5 秒，避免中途切断。
        min_silence_frames = 25  # 持续 2.5 秒静音才认为说完
        trailing_ms = 800  # 结束后保留 800ms（不要把尾音切掉）
        
        # 计算每帧 RMS
        frames = []
        for i in range(0, len(audio_data), frame_size):
            frame = audio_data[i:i + frame_size]
            if len(frame) == 0:
                break
            rms = np.sqrt(np.mean(frame.astype(np.float32) ** 2))
            frames.append(rms)
        
        if not frames:
            return audio_data
        
        # 从后往前找最后一个有效语音帧
        last_voice_frame = -1
        silence_count = 0
        for i in range(len(frames) - 1, -1, -1):
            if frames[i] > threshold:
                last_voice_frame = i
                break
            silence_count += 1
            if silence_count >= min_silence_frames:
                # 已经够长的静音，认为之前就说完了
                break
        
        if last_voice_frame < 0:
            # 全程静音或音量过低
            return audio_data
        
        # 计算结束样本点
        end_sample = (last_voice_frame + 1) * frame_size
        trailing_samples = int(trailing_ms * sample_rate / 1000)
        end_sample = min(end_sample + trailing_samples, len(audio_data))
        
        return audio_data[:end_sample]
    
    def _record_avfoundation(self, duration_seconds: int, sample_rate: int) -> np.ndarray:
        """使用 Mac AVFoundation 录音"""
        import Foundation
        import AVFoundation
        
        output_path = "/tmp/bookboy_stt_recording.wav"
        
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
        
        recorder.recordForDuration_(duration_seconds)
        time.sleep(duration_seconds + 0.5)
        recorder.stop()
        
        with wave.open(output_path, 'rb') as wf:
            data = wf.readframes(wf.getnframes())
            return np.frombuffer(data, dtype=np.int16)
    
    def _record_sounddevice(self, duration_seconds: int, sample_rate: int) -> np.ndarray:
        """使用 sounddevice 录音（备用方案）"""
        import sounddevice as sd
        
        audio_queue = queue.Queue()
        frames = []
        blocksize = 8000
        
        def callback(indata, frames, time, status):
            if status:
                print(f"录音状态: {status}", file=sys.stderr)
            audio_queue.put(np.array(indata, dtype='int16').copy())
        
        with sd.RawInputStream(
            samplerate=sample_rate,
            blocksize=blocksize,
            dtype='int16',
            channels=1,
            callback=callback
        ):
            for _ in range(int(duration_seconds * sample_rate / blocksize)):
                frames.append(audio_queue.get())
        
        return np.concatenate(frames, axis=0)
    
    def preprocess_audio(self, audio_data: np.ndarray, sample_rate: int = None) -> np.ndarray:
        """
        音频预处理：降噪 + 自动增益
        
        Args:
            audio_data: int16 音频数组
            sample_rate: 采样率
        
        Returns:
            int16 处理后的音频数组
        """
        sr = sample_rate or self.sample_rate
        
        # 归一化到 [-1, 1]
        processed = audio_data.astype(np.float32) / 32768.0
        
        # 自动增益
        if self.enable_gain:
            peak = np.max(np.abs(processed))
            if peak > 0:
                target_peak = 0.7
                gain = target_peak / peak
                gain = min(gain, 10.0)
                processed = processed * gain
        
        # 降噪
        if self.enable_denoise:
            try:
                import noisereduce as nr
                noise_sample_len = min(int(0.3 * sr), len(processed) // 4)
                if noise_sample_len > 1000:
                    noise_clip = processed[:noise_sample_len]
                    processed = nr.reduce_noise(
                        y=processed,
                        y_noise=noise_clip,
                        sr=sr,
                        prop_decrease=0.75
                    )
            except Exception:
                pass
        
        processed = np.clip(processed, -1.0, 1.0)
        return (processed * 32767).astype(np.int16)
    
    # ═══════════════════════════════════════════
    # 核心STT功能
    # ═══════════════════════════════════════════
    
    def transcribe(self, audio_data=None, audio_file=None) -> Dict:
        """
        语音识别：音频→文字
        
        Args:
            audio_data: 音频数据（numpy int16 数组）
            audio_file: 音频文件路径
        
        Returns:
            {
                "text": "识别文字",
                "confidence": 0.95,
                "language": "zh",
                "engine": "vosk",
            }
        """
        if audio_data is None and audio_file is None:
            return {"text": "", "confidence": 0, "error": "未提供音频数据或文件"}
        
        if self.engine_name == "vosk" and self.model:
            return self._transcribe_vosk(audio_data, audio_file)
        elif self.engine_name == "whisper" and self.engine:
            return self._transcribe_whisper(audio_file)
        elif self.engine_name == "funasr" and self.engine:
            return self._transcribe_funasr(audio_file)
        elif self.engine_name == "baidu":
            return self._transcribe_baidu(audio_data)
        else:
            return self._transcribe_simulation()
    
    def _transcribe_vosk(self, audio_data=None, audio_file=None) -> Dict:
        """Vosk 识别"""
        from vosk import KaldiRecognizer
        
        if audio_file and os.path.exists(audio_file):
            with wave.open(str(audio_file), 'rb') as wf:
                data = wf.readframes(wf.getnframes())
                sr = wf.getframerate()
                audio_data = np.frombuffer(data, dtype=np.int16)
        elif audio_data is not None:
            sr = self.sample_rate
        else:
            return {"text": "", "confidence": 0, "error": "音频数据或文件不存在"}
        
        # 重采样到 16000（Vosk 要求）
        if sr != 16000 and len(audio_data) > 0:
            try:
                import librosa
                audio_float = audio_data.astype(np.float32) / 32768.0
                audio_resampled = librosa.resample(audio_float, orig_sr=sr, target_sr=16000)
                audio_data = (audio_resampled * 32767).astype(np.int16)
                sr = 16000
            except ImportError:
                return {"text": "", "confidence": 0, "error": "需要 librosa 进行重采样"}
        
        rec = KaldiRecognizer(self.model, sr)
        rec.SetWords(True)
        
        audio_bytes = audio_data.tobytes()
        chunk_size = 4096 * 2
        for i in range(0, len(audio_bytes), chunk_size):
            chunk = audio_bytes[i:i + chunk_size]
            if len(chunk) == 0:
                break
            rec.AcceptWaveform(chunk)
        
        result = json.loads(rec.FinalResult())
        text = result.get("text", "")
        
        return {
            "text": text,
            "confidence": 0.85 if text else 0,
            "language": "zh",
            "engine": "vosk",
        }
    
    def _transcribe_whisper(self, audio_file):
        """Whisper识别"""
        if not audio_file or not os.path.exists(audio_file):
            return {"text": "", "confidence": 0, "error": "音频文件不存在"}
        
        result = self.engine.transcribe(str(audio_file), language="zh")
        return {
            "text": result["text"],
            "confidence": 0.9,
            "language": "zh",
            "engine": "whisper",
        }
    
    def _transcribe_funasr(self, audio_file):
        """FunASR识别"""
        if not audio_file or not os.path.exists(audio_file):
            return {"text": "", "confidence": 0, "error": "音频文件不存在"}
        
        result = self.engine.generate(input=audio_file)
        return {
            "text": result[0]["text"] if result else "",
            "confidence": 0.85,
            "language": "zh",
            "engine": "funasr",
        }
    
    def _transcribe_baidu(self, audio_data):
        """百度语音识别"""
        return {"text": "", "confidence": 0, "error": "百度API需要完整实现", "engine": "baidu"}
    
    def _transcribe_simulation(self):
        """模拟识别（无真实引擎时使用）"""
        return {
            "text": "",
            "confidence": 0,
            "engine": "simulation",
            "note": "模拟模式：无真实语音识别，请配置STT引擎",
        }
    
    def listen_once(self, duration_seconds=None, verbose=True, use_vad=True) -> Dict:
        """
        录音并识别一次
        
        Args:
            duration_seconds: 录音时长
            verbose: 是否打印过程
            use_vad: 是否使用语音活动检测
        
        Returns:
            识别结果字典
        """
        max_duration = duration_seconds if duration_seconds is not None else self.record_seconds
        if max_duration < 3:
            max_duration = 3
        
        if verbose:
            print(f"🎙️ 聆听中（最长{max_duration}秒，说完即停）...")
        
        try:
            audio_data = self.record_audio(duration_seconds=max_duration, use_vad=use_vad)
            peak = np.max(np.abs(audio_data))
            rms = np.sqrt(np.mean(audio_data.astype(np.float32) ** 2))
            actual_duration = len(audio_data) / self.sample_rate
            
            if verbose:
                print(f"  录音完成 | 实际时长: {actual_duration:.1f}秒 | 峰值: {peak} | RMS: {rms:.1f}")
            
            # 音量过低提示
            if peak < 300:
                if verbose:
                    print("  ⚠️ 音量过低，可能没有录到声音")
                return {
                    "text": "",
                    "confidence": 0,
                    "engine": self.engine_name,
                    "error": "音量过低",
                    "peak": int(peak),
                }
            
            # 预处理
            processed = self.preprocess_audio(audio_data)
            
            # 识别
            result = self.transcribe(audio_data=processed)
            result["peak"] = int(peak)
            result["rms"] = float(rms)
            result["duration"] = float(actual_duration)
            
            if verbose:
                print(f"  识别结果: {result.get('text', '')}")
            
            return result
            
        except Exception as e:
            return {
                "text": "",
                "confidence": 0,
                "engine": self.engine_name,
                "error": str(e),
            }
    
    # ═══════════════════════════════════════════
    # 唤醒词检测
    # ═══════════════════════════════════════════
    
    def detect_wake_word(self, text: str) -> bool:
        """检测是否包含唤醒词"""
        if not text:
            return False
        
        text = text.lower()
        for wake_word in self.wake_words:
            if wake_word in text:
                return True
        return False
    
    def detect_stop_word(self, text: str) -> bool:
        """检测是否包含打断词"""
        if not text:
            return False
        
        for stop_word in self.stop_words:
            if stop_word in text:
                return True
        return False
    
    # ═══════════════════════════════════════════
    # 方言适配
    # ═══════════════════════════════════════════
    
    def set_dialect(self, dialect: str):
        """设置方言"""
        supported = ["mandarin", "cantonese", "sichuan", "shanghai"]
        if dialect in supported:
            self.config["dialect"] = dialect
            print(f"[STT] 方言已设置为: {dialect}")
        else:
            print(f"[STT] 不支持的方言: {dialect}，支持: {supported}")
    
    # ═══════════════════════════════════════════
    # 噪音过滤
    # ═══════════════════════════════════════════
    
    def filter_noise(self, audio_data):
        """噪音过滤（简化版）"""
        return self.preprocess_audio(audio_data)
    
    # ═══════════════════════════════════════════
    # 完整交互流程
    # ═══════════════════════════════════════════
    
    def listen_and_respond(self, callback):
        """
        监听并响应的完整流程
        
        1. 持续监听
        2. 检测唤醒词
        3. 识别语音
        4. 返回文字
        """
        print("[STT] 开始监听...")
        print(f"[STT] 唤醒词: {'/'.join(self.wake_words)}")
        print(f"[STT] 打断词: {'/'.join(self.stop_words)}")
        
        while True:
            result = self.listen_once(duration_seconds=3, verbose=False)
            text = result.get("text", "")
            
            if self.detect_wake_word(text):
                print(f"[STT] 检测到唤醒词: {text}")
                callback({"type": "wake", "text": text, "result": result})
            elif self.detect_stop_word(text):
                print(f"[STT] 检测到打断词: {text}")
                callback({"type": "stop", "text": text, "result": result})
            elif text:
                callback({"type": "speech", "text": text, "result": result})
