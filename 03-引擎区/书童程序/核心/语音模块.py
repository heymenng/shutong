"""伴读书童AI - 语音模块

支持多种 TTS 引擎：
- edge-tts：微软 Edge 在线 TTS（推荐，中文自然）
- say：macOS 系统 TTS（离线回退）
- pyttsx3：跨平台 TTS（离线回退）

配置项：
- voice_enabled: 是否启用语音
- voice_backend: "edge-tts" | "say" | "pyttsx3"
- voice_name: 具体声音名称
- voice_rate: 语速（仅 say/pyttsx3 有效）
"""

import asyncio
import hashlib
import re
import subprocess
import sys
import platform
import tempfile
import os
from pathlib import Path
from ..配置 import CONFIG


class VoiceEngine:
    # 类级别播放锁，防止多个语音同时播放
    _play_lock = None

    def __init__(self):
        self.engine = None
        self.backend = None
        self.cache_dir = None

        from threading import Lock
        if VoiceEngine._play_lock is None:
            VoiceEngine._play_lock = Lock()

        if not CONFIG.get("voice_enabled", True):
            print("[语音] 语音功能已禁用")
            return
        
        # 初始化语音缓存目录（主要用于 edge-tts）
        project_root = Path(__file__).resolve().parents[3]
        self.cache_dir = project_root / "03-引擎区" / "书童程序" / "数据" / "语音缓存"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
            # 根据配置选择后端
        # 书童常规声音：讯飞超拟人语音 x6_tianjingshaonv_pro（天津少女）
        # 禁止默认把 macOS say 当“系统测试音”使用
        preferred_backend = CONFIG.get("voice_backend", "xfyun_oral")

        if preferred_backend == "xfyun_oral":
            if self._try_xfyun_oral():
                return
            print("[语音] ⚠️ 讯飞超拟人语音不可用，尝试回退到 edge-tts")
            if self._try_edge_tts():
                return
        elif preferred_backend == "edge-tts":
            if self._try_edge_tts():
                return
            print("[语音] ⚠️ edge-tts 不可用，尝试回退")
            if platform.system() == 'Darwin' and self._try_say():
                return
            if self._try_pyttsx3():
                return
        elif preferred_backend == "say":
            if platform.system() == 'Darwin' and self._try_say():
                return
            if self._try_pyttsx3():
                return
        elif preferred_backend == "pyttsx3":
            if self._try_pyttsx3():
                return
        elif preferred_backend == "auto":
            # 自动选择：优先讯飞，其次 edge-tts，最后 say / pyttsx3
            if self._try_xfyun_oral():
                return
            if self._try_edge_tts():
                return
            if platform.system() == 'Darwin' and self._try_say():
                return
            if self._try_pyttsx3():
                return

        print("[语音] 无可用 TTS 引擎，语音功能已禁用")
    
    # ═══════════════════════════════════════════
    # 后端初始化
    # ═══════════════════════════════════════════
    
    def _try_edge_tts(self):
        """尝试初始化 Edge-TTS"""
        try:
            import edge_tts
            self.backend = 'edge-tts'
            voice_name = CONFIG.get("voice_name", "zh-CN-XiaoxiaoNeural")
            print(f"[语音] 使用 Edge-TTS 引擎，声音: {voice_name}")
            return True
        except ImportError:
            return False

    def _try_xfyun_oral(self):
        """尝试初始化讯飞超拟人语音（书童常规声音：天津少女 x6_tianjingshaonv_pro）"""
        try:
            from .讯飞超拟人语音 import XfyunOralTTS
            tts = XfyunOralTTS()
            # 先做一次空合成，验证密钥和网络可用性
            test_bytes = tts.synthesize_to_bytes("你好")
            if test_bytes is None:
                print(f"[语音] 讯飞超拟人语音不可用: {tts.error_msg}")
                return False
            self.backend = 'xfyun_oral'
            voice_name = CONFIG.get("voice_name", "x6_tianjingshaonv_pro")
            print(f"[语音] 使用讯飞超拟人语音引擎，声音: {voice_name}")
            return True
        except ImportError as e:
            print(f"[语音] 讯飞 SDK 未安装: {e}")
            return False
        except Exception as e:
            print(f"[语音] 讯飞超拟人语音初始化失败: {e}")
            return False

    def _speak_xfyun_oral(self, text):
        """使用讯飞超拟人语音播放"""
        from .讯飞超拟人语音 import XfyunOralTTS, play_audio_bytes

        segments = self._split_text(text, max_len=120)
        for i, segment in enumerate(segments, 1):
            segment = segment.strip()
            if not segment:
                continue
            filtered = self._filter_for_tts(segment)
            if not filtered:
                continue

            tts = XfyunOralTTS()
            audio_bytes = tts.synthesize_to_bytes(filtered)
            if audio_bytes:
                play_audio_bytes(audio_bytes)
                print(f"  [语音播放完成 ({i}/{len(segments)}]")
            else:
                raise RuntimeError(f"讯飞合成失败: {tts.error_msg}")

    def _try_say(self):
        """尝试初始化 macOS say"""
        try:
            result = subprocess.run(['which', 'say'], capture_output=True, text=True)
            if result.returncode == 0:
                self.backend = 'say'
                voice_name = CONFIG.get("voice_name", "Tingting")
                print(f"[语音] 使用 macOS say 引擎（回退），声音: {voice_name}")
                return True
        except Exception:
            pass
        return False
    
    def _try_pyttsx3(self):
        """尝试初始化 pyttsx3"""
        try:
            import pyttsx3
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', CONFIG.get("voice_rate", 110))
            self.backend = 'pyttsx3'
            print("[语音] 使用 pyttsx3 引擎（回退）")
            return True
        except Exception:
            return False
    
    # ═══════════════════════════════════════════
    # 语音播放
    # ═══════════════════════════════════════════
    
    def speak(self, text):
        """播放文字（增强稳定性：失败重试 + 自动回退引擎）"""
        if not text or not self.backend:
            return
        
        # 清洗文本
        clean_text = re.sub(r'[（(].*?[）)]', '', text)
        clean_text = clean_text.replace('\n', ' ').replace('\r', ' ')
        clean_text = clean_text.strip()
        if not clean_text:
            return
        
        # 记录原始首选后端
        original_backend = self.backend
        original_engine = self.engine
        
        # 尝试当前引擎，失败则回退
        engines_to_try = [
            (original_backend, original_engine),
        ]
        # 如果首选是讯飞超拟人语音，只允许回退到 edge-tts，禁止自动切到 macOS say 测试音
        if original_backend == 'xfyun_oral':
            engines_to_try.append(('edge-tts', None))
        else:
            if original_backend != 'say' and platform.system() == 'Darwin':
                engines_to_try.append(('say', None))
            if original_backend != 'pyttsx3':
                engines_to_try.append(('pyttsx3', None))
        
        last_error = None
        for backend, engine in engines_to_try:
            try:
                if backend == 'edge-tts':
                    self._speak_edge_tts(clean_text)
                elif backend == 'xfyun_oral':
                    self._speak_xfyun_oral(clean_text)
                elif backend == 'say':
                    self._say_long_text(clean_text)
                elif backend == 'pyttsx3':
                    if engine:
                        engine.say(clean_text)
                        engine.runAndWait()
                    else:
                        # 临时初始化 pyttsx3
                        import pyttsx3
                        temp_engine = pyttsx3.init()
                        temp_engine.setProperty('rate', CONFIG.get("voice_rate", 110))
                        temp_engine.say(clean_text)
                        temp_engine.runAndWait()
                        temp_engine.stop()
                # 播放成功
                if backend != original_backend:
                    print(f"[语音] 回退引擎 {backend} 播放成功")
                return
            except Exception as e:
                last_error = e
                print(f"[语音] {backend} 播放失败: {e}，尝试回退")
                continue
        
        # 所有引擎都失败
        print(f"[语音] 所有引擎播放失败: {last_error}")
    
    def _speak_edge_tts(self, text):
        """使用 Edge-TTS 播放（带缓存）"""
        import edge_tts
        
        voice_name = CONFIG.get("voice_name", "zh-CN-XiaoxiaoNeural")
        
        # 长文本分段，每段控制在约30-40秒，确保完整播放
        segments = self._split_text(text, max_len=120)
        
        for i, segment in enumerate(segments, 1):
            segment = segment.strip()
            if not segment:
                continue
            
            # 过滤特殊字符
            filtered = self._filter_for_tts(segment)
            if not filtered:
                continue
            
            # 计算缓存文件名
            cache_key = hashlib.md5(f"{voice_name}:{filtered}".encode('utf-8')).hexdigest()
            cache_path = self.cache_dir / f"{cache_key}.mp3"
            
            # 检查缓存
            if cache_path.exists():
                print(f"  [语音缓存命中] {filtered[:30]}...")
                self._play_audio(str(cache_path), segment_index=i, total=len(segments))
                continue
            
            # 生成临时音频文件
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp:
                tmp_path = tmp.name
            play_path = tmp_path
            
            try:
                # 异步生成音频
                asyncio.run(self._generate_edge_tts(filtered, voice_name, tmp_path))
                
                # 保存到缓存
                try:
                    import shutil
                    shutil.move(tmp_path, str(cache_path))
                    play_path = str(cache_path)
                    tmp_path = None  # 已移动，不需要再删除
                except Exception as e:
                    print(f"  [语音缓存失败] {e}")
                
                # 播放音频
                self._play_audio(play_path, segment_index=i, total=len(segments))
            finally:
                # 删除临时文件（如果还在）
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass
            
            # 清理旧缓存，最多保留 200 个
            self._clean_cache(max_files=200)
    
    async def _generate_edge_tts(self, text, voice, output_path):
        """异步调用 Edge-TTS 生成音频"""
        import edge_tts
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)
    
    def _play_audio(self, audio_path, segment_index=None, total=None):
        """播放音频文件，带完成确认和并发控制"""
        if VoiceEngine._play_lock is None:
            from threading import Lock
            VoiceEngine._play_lock = Lock()

        seg_info = f" ({segment_index}/{total})" if segment_index and total else ""

        with VoiceEngine._play_lock:
            # 播放前先停止任何正在播放的 afplay 进程
            if platform.system() == 'Darwin':
                try:
                    subprocess.run(['pkill', '-f', 'afplay'], check=False, timeout=5)
                except Exception:
                    pass

            try:
                if platform.system() == 'Darwin':
                    subprocess.run(['afplay', audio_path], check=False, timeout=60)
                    print(f"  [语音播放完成{seg_info}]")
                else:
                    # Linux/Windows 尝试其他播放器
                    for cmd in [['ffplay', '-autoexit', '-nodisp', audio_path],
                               ['mpg123', audio_path],
                               ['cvlc', audio_path]]:
                        try:
                            subprocess.run(cmd, check=False, timeout=60,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            print(f"  [语音播放完成{seg_info}]")
                            return
                        except Exception:
                            continue
            except subprocess.TimeoutExpired:
                print(f"  [语音播放超时{seg_info}]")
            except Exception as e:
                print(f"  [语音播放失败{seg_info}]: {e}")
    
    def _split_text(self, text, max_len=300):
        """按句子分割长文本"""
        sentences = re.split(r'([。！？.!?])', text)
        segments = []
        current = ""
        
        for part in sentences:
            if not part:
                continue
            if len(part) > max_len:
                if current:
                    segments.append(current)
                    current = ""
                for i in range(0, len(part), max_len):
                    segments.append(part[i:i+max_len])
                continue
            
            if len(current) + len(part) > max_len and current:
                segments.append(current)
                current = part
            else:
                current += part
        
        if current:
            segments.append(current)
        
        return segments if segments else [text]
    
    def _filter_for_tts(self, text):
        """过滤 TTS 不需要的字符"""
        filtered = re.sub(r'!\[.*?\]\(.*?\)', '', text)  # 图片
        filtered = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', filtered)  # 链接保留文字
        filtered = re.sub(r'[`#*|>\-]', '', filtered)  # Markdown 符号
        filtered = re.sub(r'https?://\S+', '链接', filtered)  # URL
        filtered = re.sub(r'\s+', ' ', filtered).strip()
        return filtered
    
    def _say_long_text(self, text, max_len=60):
        """macOS say 分段播放长文本"""
        filtered = self._filter_for_tts(text)
        if not filtered:
            return
        
        segments = self._split_text(filtered, max_len)
        voice_name = CONFIG.get("voice_name", "Tingting")
        voice_rate = CONFIG.get("voice_rate", 110)
        
        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue
            try:
                subprocess.run(
                    ['say', '-v', voice_name, '-r', str(voice_rate), segment],
                    capture_output=True,
                    timeout=30
                )
            except subprocess.TimeoutExpired:
                print(f"[语音] 分段播放超时，跳过: {segment[:30]}...")
            except Exception as e:
                print(f"[语音] 分段播放失败: {e}")
    
    def _clean_cache(self, max_files=200):
        """清理旧语音缓存"""
        if not self.cache_dir or not self.cache_dir.exists():
            return
        
        cache_files = sorted(self.cache_dir.glob('*.mp3'), key=lambda p: p.stat().st_mtime, reverse=True)
        if len(cache_files) > max_files:
            for old_file in cache_files[max_files:]:
                try:
                    old_file.unlink()
                except Exception:
                    pass
