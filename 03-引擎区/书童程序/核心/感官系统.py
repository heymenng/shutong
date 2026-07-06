"""伴读书童AI - 感官系统

书童的眼睛和耳朵：
- 眼睛：摄像头，用于人脸识别、环境观察、孩子状态判断
- 耳朵：麦克风，用于语音识别、情绪判断、日常对话

Mac 权限说明：
- 必须在 Terminal / iTerm 中运行才能获得摄像头/麦克风权限
- IDE / 某些 agent 环境无法访问摄像头和麦克风
- 首次运行会弹出系统授权窗口，需要点击"允许"
"""

import json
import platform
import tempfile
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

# 尝试导入项目配置
try:
    from ..配置 import CONFIG
except ImportError:
    CONFIG = {}

from ..工具.项目根目录 import get_project_root


_PROJECT_ROOT = get_project_root()


class SensorySystem:
    """书童感官系统：视觉 + 听觉"""

    def __init__(self, journal_dir=None, config=None):
        self.journal_dir = Path(journal_dir) if journal_dir else _PROJECT_ROOT / "03-引擎区" / "书童程序" / "数据" / "感官日志"
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        self.config = config or CONFIG
        
        self.vision = VisionSensor(self.journal_dir)
        self.audio = AudioSensor(self.journal_dir, self.config)
    
    def status(self):
        """返回感官系统状态"""
        return {
            "vision": self.vision.status(),
            "audio": self.audio.status(),
            "platform": platform.system(),
        }
    
    def look_and_listen(self, duration=5):
        """
        同时睁眼看、竖耳听。
        返回: {
            "frame_path": 照片路径或 None,
            "faces": 检测到的人脸数,
            "recognized": 识别到的人名或 None,
            "speech_text": 听到的文字或 "",
        }
        """
        result = {
            "frame_path": None,
            "faces": 0,
            "recognized": None,
            "speech_text": "",
        }
        
        # 睁眼
        try:
            frame = self.vision.capture_frame(save=True)
            if frame is not None:
                result["frame_path"] = str(self.vision.last_frame_path)
                result["faces"] = self.vision.detect_face_in_frame(frame)
                recognized = self.vision.recognize_person(frame)
                if recognized:
                    result["recognized"] = recognized
        except Exception as e:
            self.vision._log("look_error", f"睁眼失败: {e}")
        
        # 竖耳
        try:
            result["speech_text"] = self.audio.listen_and_transcribe(duration=duration)
        except Exception as e:
            self.audio._log("listen_error", f"竖耳失败: {e}")
        
        return result


class VisionSensor:
    """视觉传感器：摄像头 + 人脸识别"""
    
    def __init__(self, journal_dir):
        self.journal_dir = journal_dir
        self.cap = None
        self.last_frame_path = None
        
        # 摄像头索引：None 表示自动选择
        self._configured_index = CONFIG.get("camera_index")
        self._auto_select = CONFIG.get("camera_auto_select", True)
        self._prefer_landscape = CONFIG.get("camera_prefer_landscape", True)
        self._current_camera_index = self._select_camera_index()
        
        # 人脸识别相关
        self.project_root = Path(__file__).resolve().parents[3]
        self.face_model_path = self.project_root / "03-引擎区" / "书童程序" / "数据" / "模型" / "face_landmarker.task"
        self.face_features_dir = self.project_root / "03-引擎区" / "书童程序" / "数据" / "人脸特征"
        self._face_detector = None
        self._registered_faces = {}
        self._load_registered_faces()
    
    def _select_camera_index(self):
        """
        选择正确的摄像头。
        
        策略：
        1. 如果配置了 camera_index，先尝试该索引
        2. 如果 auto_select=True，遍历所有摄像头，选择：
           - 能读到真实画面的（非全黑、非过暗）
           - 优先横屏（宽 > 高），因为 MacBook 自带 FaceTime 摄像头通常是横屏
           - iPhone 连续互通相机通常是竖屏（高 > 宽），作为次选
        3. 默认回退到 0
        """
        import cv2
        
        candidates = []
        if self._configured_index is not None:
            candidates.append(self._configured_index)
        candidates.extend([0, 1, 2, 3])
        
        best_index = None
        best_is_landscape = False
        best_brightness = 0
        
        for idx in candidates:
            try:
                cap = cv2.VideoCapture(idx)
                if not cap.isOpened():
                    continue
                
                # 预热并读取一帧
                frame = None
                for _ in range(15):
                    ret, frame = cap.read()
                    if ret and frame is not None and frame.size > 0:
                        break
                
                cap.release()
                
                if frame is None or frame.size == 0:
                    self._log("camera_select", f"索引 {idx}: 无法读取画面")
                    continue
                
                h, w = frame.shape[:2]
                brightness = float(frame.mean())
                is_landscape = w > h
                
                self._log("camera_select", f"索引 {idx}: 画面 {w}x{h}, 亮度 {brightness:.1f}, 横屏={is_landscape}")
                
                # 如果配置了指定索引且它能打开，优先使用
                # （即使当前画面暗，也尊重用户选择；capture_frame 会进一步处理亮度和回退）
                if idx == self._configured_index:
                    self._log("camera_select", f"使用配置索引 {idx}，画面 {w}x{h}，亮度 {brightness:.1f}")
                    return idx
                
                # 过滤全黑/过暗画面（可能是占位设备或未授权）
                # 同时检查亮度与方差：全黑画面亮度≈0且方差≈0
                variance = float(frame.var())
                if brightness < 2 and variance < 10:
                    self._log("camera_select", f"索引 {idx}: 画面过暗/全黑，跳过")
                    continue
                
                # 自动选择：优先横屏；同方向下优先更亮的
                if best_index is None:
                    best_index = idx
                    best_is_landscape = is_landscape
                    best_brightness = brightness
                elif self._prefer_landscape and is_landscape and not best_is_landscape:
                    best_index = idx
                    best_is_landscape = True
                    best_brightness = brightness
                elif is_landscape == best_is_landscape and brightness > best_brightness:
                    best_index = idx
                    best_brightness = brightness
                
            except Exception as e:
                self._log("camera_select", f"索引 {idx}: 异常 {e}")
                continue
        
        if best_index is not None:
            self._log("camera_select", f"自动选择索引 {best_index}（横屏优先={self._prefer_landscape}）")
            return best_index
        
        # 兜底：如果配置了索引但不可用，回退到 0；否则也回退到 0
        fallback = self._configured_index if self._configured_index is not None else 0
        self._log("camera_select", f"无法自动选择有效摄像头，回退到索引 {fallback}")
        return fallback
    
    def status(self):
        """返回摄像头状态"""
        return {
            "available": self._check_camera_available(),
            "running": self.cap is not None,
            "last_frame": str(self.last_frame_path) if self.last_frame_path else None,
            "face_model_ready": self.face_model_path.exists(),
            "registered_faces": len(self._registered_faces),
            "camera_index": self._current_camera_index,
            "configured_index": self._configured_index,
        }
    
    def _check_camera_available(self):
        """检查摄像头是否可用"""
        try:
            import cv2
            cap = cv2.VideoCapture(self._current_camera_index)
            if cap.isOpened():
                cap.release()
                return True
            return False
        except Exception:
            return False
    
    def _is_valid_frame(self, frame):
        """检查画面是否有效：非空、非全黑"""
        if frame is None or frame.size == 0:
            return False
        brightness = float(frame.mean())
        variance = float(frame.var())
        return not (brightness < 2 and variance < 10)
    
    def _try_capture_from_index(self, idx, max_attempts=30):
        """尝试从指定索引捕获一帧有效画面，并进行预热稳定"""
        import cv2
        cap = cv2.VideoCapture(idx)
        if not cap.isOpened():
            return None
        
        best_frame = None
        best_score = -1
        
        for _ in range(max_attempts):
            ret, frame = cap.read()
            if not ret or frame is None or frame.size == 0:
                continue
            
            brightness = float(frame.mean())
            variance = float(frame.var())
            
            # 优先选择亮度适中、细节丰富的画面
            # 全黑画面亮度≈0且方差≈0；过曝画面方差也可能低
            score = brightness * variance
            
            if score > best_score and brightness > 2:
                best_score = score
                best_frame = frame
            
            # 如果已经获得足够好的画面，提前结束
            if brightness > 30 and variance > 500:
                break
        
        cap.release()
        return best_frame
    
    def capture_frame(self, save=True):
        """捕获一帧图像，自动在多个摄像头索引间选择有效画面"""
        import cv2
        
        # 优先使用当前选中的索引
        frame = self._try_capture_from_index(self._current_camera_index)
        used_index = self._current_camera_index
        
        # 如果当前索引无效，尝试其他候选索引
        if frame is None:
            candidates = [0, 1, 2, 3]
            if self._current_camera_index in candidates:
                candidates.remove(self._current_camera_index)
            
            for idx in candidates:
                frame = self._try_capture_from_index(idx)
                if frame is not None:
                    used_index = idx
                    self._log("capture_fallback", f"当前索引 {self._current_camera_index} 无效，切换到索引 {idx}")
                    # 更新当前索引，方便下次使用
                    self._current_camera_index = idx
                    break
        
        if frame is None:
            raise RuntimeError("无法从任何摄像头读取有效画面，请检查权限和硬件")
        
        if save:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            frame_path = self.journal_dir / f"vision_{timestamp}.jpg"
            cv2.imwrite(str(frame_path), frame)
            self.last_frame_path = frame_path
            self._log("capture", f"索引 {used_index} 保存画面到 {frame_path}")
        
        return frame
    
    def detect_face(self):
        """检测画面中是否有人脸（保留旧接口）"""
        try:
            frame = self.capture_frame(save=False)
            count = self.detect_face_in_frame(frame)
            self._log("face_detect", f"检测到 {count} 张人脸")
            return count, []
        except Exception as e:
            self._log("face_detect", f"检测失败: {e}")
            return 0, []
    
    def detect_face_in_frame(self, frame):
        """在已捕获的帧中检测人脸数量"""
        try:
            import cv2
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            face_cascade = cv2.CascadeClassifier(cascade_path)
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)
            return len(faces)
        except Exception:
            return 0
    
    def recognize_person(self, frame=None):
        """
        识别画面中的人物。
        返回: 识别到的人名，或 None。
        """
        if not self.face_model_path.exists():
            return None
        
        if not self._registered_faces:
            return None
        
        try:
            if frame is None:
                frame = self.capture_frame(save=False)
            if frame is None:
                return None
            
            # 保存临时文件给 MediaPipe 用
            temp_path = self.journal_dir / f"_recognize_temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            import cv2
            cv2.imwrite(str(temp_path), frame)
            
            new_features = self._extract_features(str(temp_path))
            temp_path.unlink(missing_ok=True)
            
            if new_features is None:
                return None
            
            best_match = None
            best_distance = float('inf')
            threshold = 1.5
            
            for name, data in self._registered_faces.items():
                registered_features = np.array(data["average_landmarks"])
                distance = np.linalg.norm(new_features - registered_features)
                self._log("face_compare", f"与 {name} 距离: {distance:.4f}")
                if distance < best_distance:
                    best_distance = distance
                    best_match = name
            
            if best_match and best_distance < threshold:
                self._log("face_recognize", f"识别为 {best_match}，距离 {best_distance:.4f}")
                return best_match
            
            return None
        except Exception as e:
            self._log("face_recognize_error", f"识别失败: {e}")
            return None
    
    def _extract_features(self, image_path):
        """从图片中提取人脸特征"""
        try:
            import mediapipe as mp
            from mediapipe.tasks.python import vision
            from mediapipe.tasks.python.core.base_options import BaseOptions
            
            base_options = BaseOptions(model_asset_path=str(self.face_model_path))
            options = vision.FaceLandmarkerOptions(
                base_options=base_options,
                num_faces=1,
                running_mode=vision.RunningMode.IMAGE
            )
            detector = vision.FaceLandmarker.create_from_options(options)
            
            mp_image = mp.Image.create_from_file(str(image_path))
            results = detector.detect(mp_image)
            
            if not results.face_landmarks:
                detector.close()
                return None
            
            landmarks = []
            for landmark in results.face_landmarks[0]:
                landmarks.append([landmark.x, landmark.y, landmark.z])
            
            landmarks = np.array(landmarks)
            
            # 对齐到中心
            center_x = np.mean(landmarks[:, 0])
            center_y = np.mean(landmarks[:, 1])
            aligned_landmarks = landmarks.copy()
            aligned_landmarks[:, 0] -= center_x
            aligned_landmarks[:, 1] -= center_y
            
            detector.close()
            return aligned_landmarks
        except Exception:
            return None
    
    def _load_registered_faces(self):
        """加载已注册的人脸特征"""
        if not self.face_features_dir.exists():
            return
        
        for record_file in self.face_features_dir.glob("*_face_features.json"):
            try:
                with open(record_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                person_name = data.get("person_name") or record_file.stem.replace("_face_features", "")
                self._registered_faces[person_name] = data
            except Exception:
                continue
    
    def _log(self, event_type, detail):
        """记录视觉事件"""
        log_file = self.journal_dir / f"vision_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} | {event_type} | {detail}\n")


class AudioSensor:
    """听觉传感器：麦克风 + 语音识别"""
    
    def __init__(self, journal_dir=None, config=None):
        self.journal_dir = Path(journal_dir) if journal_dir else _PROJECT_ROOT / "03-引擎区" / "书童程序" / "数据" / "感官日志"
        self.recording = False
        self.last_audio_path = None
        self.config = config or {}
        
        # 复用语音识别引擎（支持 Whisper / Vosk / Simulation）
        try:
            from .语音识别 import SpeechRecognition
            self.stt = SpeechRecognition(self.config)
        except Exception as e:
            print(f"[AudioSensor] 语音识别引擎初始化失败: {e}")
            self.stt = None
    
    def status(self):
        """返回麦克风状态"""
        return {
            "available": self._check_audio_available(),
            "recording": self.recording,
            "last_audio": str(self.last_audio_path) if self.last_audio_path else None,
        }
    
    def _check_audio_available(self):
        """检查麦克风是否可用"""
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            input_devices = [d for d in devices if d.get("max_input_channels", 0) > 0]
            return len(input_devices) > 0
        except Exception:
            return False
    
    def record_audio(self, duration=5, sample_rate=16000):
        """录制音频"""
        try:
            import sounddevice as sd
            import numpy as np
            
            self.recording = True
            self._log("record_start", f"开始录音 {duration} 秒")
            
            audio_data = sd.rec(
                int(duration * sample_rate),
                samplerate=sample_rate,
                channels=1,
                dtype=np.int16
            )
            sd.wait()
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            audio_path = self.journal_dir / f"audio_{timestamp}.wav"
            
            with wave.open(str(audio_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(audio_data.tobytes())
            
            self.last_audio_path = audio_path
            self.recording = False
            self._log("record_end", f"录音保存到 {audio_path}")
            
            return audio_path
        except Exception as e:
            self.recording = False
            self._log("record_error", f"录音失败: {e}")
            raise
    
    def record_audio_vad(self, max_duration=30, sample_rate=16000, silence_seconds=2.0, aggressiveness=3):
        """
        使用 WebRTC VAD 录制音频。

        规则：
        - 先持续录音，等待检测到有效语音
        - 检测到语音后，如果连续 silence_seconds 秒没有声音，停止录音
        - 如果一直没人说话，最多录 max_duration 秒

        Args:
            max_duration: 最大录音时长（秒）
            sample_rate: 采样率
            silence_seconds: 检测到连续静音多少秒后停止录音
            aggressiveness: VAD 激进程度 0-3，越大越严格过滤噪音
        """
        try:
            import sounddevice as sd
            import numpy as np
            import webrtcvad

            self.recording = True
            self._log("record_start", f"开始 WebRTC VAD 录音，最长 {max_duration} 秒，说话后停顿 {silence_seconds} 秒停止")
            print(f"[VAD] 开始录音，请说话...（说完后停顿 {silence_seconds} 秒自动结束）")

            vad = webrtcvad.Vad(aggressiveness)
            frame_duration_ms = 30  # WebRTC VAD 支持 10/20/30ms
            frame_samples = int(sample_rate * frame_duration_ms / 1000)
            silence_frames_needed = int(silence_seconds * 1000 / frame_duration_ms)
            silence_frames = 0
            max_frames = int(max_duration * 1000 / frame_duration_ms)

            audio_buffer = []
            speech_detected = False
            frames_recorded = 0

            def callback(indata, frames, time_info, status):
                audio_buffer.append(indata.copy())

            with sd.InputStream(samplerate=sample_rate, channels=1, dtype=np.int16, blocksize=frame_samples, callback=callback):
                while frames_recorded < max_frames:
                    if len(audio_buffer) > frames_recorded:
                        frame = audio_buffer[frames_recorded]
                        frames_recorded += 1

                        # WebRTC VAD 需要 bytes
                        frame_bytes = frame.tobytes()
                        is_speech = vad.is_speech(frame_bytes, sample_rate)

                        if is_speech:
                            speech_detected = True
                            silence_frames = 0
                        else:
                            silence_frames += 1

                        # 只有检测到语音后，连续静音才停止录音
                        if speech_detected and silence_frames >= silence_frames_needed:
                            print(f"[VAD] 检测到连续 {silence_seconds} 秒静音，停止录音")
                            break

            # 合并音频
            if audio_buffer:
                audio_data = np.concatenate(audio_buffer[:frames_recorded], axis=0)
            else:
                audio_data = np.array([], dtype=np.int16)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            audio_path = self.journal_dir / f"audio_vad_{timestamp}.wav"

            with wave.open(str(audio_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                if len(audio_data) > 0:
                    wf.writeframes(audio_data.tobytes())

            self.last_audio_path = audio_path
            self.recording = False
            actual_duration = frames_recorded * frame_duration_ms / 1000
            self._log("record_end", f"VAD 录音保存到 {audio_path}，时长约 {actual_duration:.1f} 秒")

            return audio_path
        except Exception as e:
            self.recording = False
            self._log("record_error", f"VAD 录音失败: {e}")
            raise
    
    def transcribe(self, audio_path=None):
        """语音识别"""
        try:
            if audio_path is None:
                audio_path = self.last_audio_path
            
            if not audio_path or not Path(audio_path).exists():
                raise RuntimeError("没有可识别的音频文件")
            
            # 复用语音识别引擎
            if self.stt and self.stt.engine:
                result = self.stt.transcribe(audio_file=audio_path)
                text = result.get("text", "").strip()
            else:
                raise RuntimeError("语音识别引擎未初始化")
            
            self._log("transcribe", f"识别结果: {text}")
            return text
        except Exception as e:
            self._log("transcribe_error", f"识别失败: {e}")
            raise
    
    def listen_and_transcribe(self, duration=5):
        """录音并识别，一步完成"""
        audio_path = self.record_audio(duration)
        return self.transcribe(audio_path)
    
    def _log(self, event_type, detail):
        """记录听觉事件"""
        log_file = self.journal_dir / f"audio_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} | {event_type} | {detail}\n")
