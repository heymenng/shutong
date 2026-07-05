"""伴读书童AI - 晨起仪式生成器

为孩子生成 5-10 分钟的起床仪式音频：
- 轻柔到欢快的背景音乐
- 多角色语音（小艺主声、东北书童、台湾书童）
- 3-4 个笑话
- 温柔叫醒、互动问答、今日鼓励

输出：单个 MP3 文件，可直接播放。
"""

import asyncio
import math
import os
import struct
import sys
import tempfile
import time
import wave
from pathlib import Path

from pydub import AudioSegment

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = PROJECT_ROOT / "02-知识库区" / "训练素材" / "音频" / "晨起仪式"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 统一使用项目配置的语音引擎
sys.path.insert(0, str(PROJECT_ROOT))
from 书童程序.核心.语音模块 import VoiceEngine
from 书童程序.配置 import CONFIG


class MorningRitualGenerator:
    def __init__(self, child_name="小橙子", age=8, interests=None):
        self.child_name = child_name
        self.age = age
        self.interests = interests or []
        self.segments = []
        self.voice_engine = VoiceEngine()

    # ═══════════════════════════════════════════
    # 音乐生成
    # ═══════════════════════════════════════════

    def generate_music(self, duration_sec=90, filename="bgm.wav"):
        """生成一段轻快的儿童起床背景音乐"""
        sample_rate = 44100
        samples = []

        # 简单 cheerful 旋律循环
        base_melody = [
            (60, 0.4), (64, 0.4), (67, 0.4), (72, 0.8),
            (67, 0.4), (64, 0.4), (60, 0.8),
            (62, 0.4), (65, 0.4), (69, 0.4), (74, 0.8),
            (69, 0.4), (65, 0.4), (62, 0.8),
        ]

        note_duration = sum(d for _, d in base_melody)
        repeats = int(duration_sec / note_duration) + 1

        for _ in range(repeats):
            for note, dur in base_melody:
                freq = 440.0 * (2 ** ((note - 69) / 12.0))
                note_samples = int(sample_rate * dur)
                for i in range(note_samples):
                    t = i / sample_rate
                    # 柔和正弦波，带一点衰减
                    val = 0.12 * math.sin(2 * math.pi * freq * t) * math.exp(-t * 0.8)
                    samples.append(val)
                # 音符间短停顿
                samples.extend([0.0] * int(sample_rate * 0.05))

        # 截到目标时长
        target_samples = int(sample_rate * duration_sec)
        samples = samples[:target_samples]

        path = Path(tempfile.gettempdir()) / filename
        with wave.open(str(path), 'w') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            for s in samples:
                w.writeframes(struct.pack('h', int(max(-1, min(1, s)) * 32767)))
        return path

    # ═══════════════════════════════════════════
    # 语音合成
    # ═══════════════════════════════════════════

    def tts(self, text, role="书童"):
        """生成单个语音片段，返回 MP3 路径。
        默认使用项目配置的语音引擎（当前为讯飞天津少女）。
        """
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
        # 东北/台湾等特色声音暂时统一为主声音
        # 后续可通过方言陪伴模块扩展
        result = self.voice_engine.synthesize_to_file(text, tmp_path)
        if not result:
            raise RuntimeError(f"语音合成失败: {text[:30]}...")
        return tmp_path

    # ═══════════════════════════════════════════
    # 仪式内容
    # ═══════════════════════════════════════════

    def get_jokes(self):
        """获取适合孩子年龄的 3-4 个笑话"""
        if self.age <= 6:
            return [
                ("东北", f"{self.child_name}，给你讲一个啊。有一天，小鸭子问小鸡：'你为啥起那么早？'小鸡说：'我得打鸣，我一打鸣太阳就起来了。'小鸭子又问：'那你打鸣之前太阳在哪儿呢？'小鸡说：'在被窝里呢，跟我一样也不想出来！'小鸭子说：'那你今天别打了呗。'小鸡说：'那可不行，{self.child_name}还等着起床呢！'"),
                ("台湾", f"{self.child_name}，我再讲一个哦。有一隻小豬想要減肥，跑去問小兔子為什麼這麼瘦。小兔子說：'我吃紅蘿蔔，還會跳來跳去。'小豬買了紅蘿蔔，吃了一口說：'好難吃哦！'又跑去問小猴子。小猴子說：'我每天都爬樹。'小豬爬了半天爬不上去，坐在樹下說：'算啦，我還是當一隻快樂的小豬吧，減肥明天再說！'結果明天到了，小豬又說：'明天再說吧！'就這樣快樂地胖了一輩子。"),
                ("东北", f"{self.child_name}，再来一个。小蚂蚁问大象：'你家在哪儿啊？'大象说：'在前面。'小蚂蚁走啊走，走了三天三夜，回头一看，大象还在后面。小蚂蚁喊：'你骗我！'大象说：'我没骗你，我腿长，一步就到，你腿短，得走三天。'"),
            ]
        elif self.age <= 9:
            return [
                ("东北", f"{self.child_name}，早上好！给你讲一个。老师问小明：'你为什么迟到？'小明说：'我梦见自己在考试，就一直写一直写。'老师说：'那也不至于迟到啊。'小明说：'关键是，我醒来之后，发现真的有考试！'"),
                ("台湾", f"{self.child_name}，我問你哦。為什麼書本總是很累？因為它們有太多的故事要講，還要被人翻來翻去。那為什麼鉛筆總是很快樂？因為它每天都可以寫出新的答案。那為什麼橡皮擦很難過？因為它總是在擦別人的錯誤，自己的工作就是消失。"),
                ("东北", f"{self.child_name}，再来一个啊。小橙子问书童：'书童书童，你知道螃蟹为什么横着走吗？'书童说：'因为它有脾气，谁让它竖着走它都不听！'小橙子又问：'那你知道蜗牛为什么背着房子走吗？'书童说：'因为它买不起房，只能自己背着！'"),
                ("台湾", f"{self.child_name}，最後一個哦。有一天，冰箱對微波爐說：'你總是那麼急躁，我才不像你。'微波爐說：'你冷靜是因為你裡面裝的都是冰淇淋。'冰箱說：'那也比你天天轉來轉去強。'微波爐嘆了口氣：'我轉，是因為我想快點讓大家吃到熱乎乎的飯啊。'{self.child_name}，今天我們也早點起來，吃熱乎乎的早餐吧。"),
            ]
        else:
            # 10岁以上
            return [
                ("东北", f"{self.child_name}，早上好！给你讲一个。有一天，小明问爸爸：'爸爸，什么叫理想？'爸爸说：'理想就是你长大以后想干什么。'小明说：'那我的理想是当一个老板。'爸爸说：'好啊，有理想。'小明又说：'爸爸，你的理想是什么？'爸爸说：'我的理想就是你现在赶紧去上学。'"),
                ("台湾", f"{self.child_name}，我問你，你知道為什麼數學書總是很憂鬱嗎？因為它有太多的問題。那為什麼歷史書總是很平靜？因為它看過太多事情。那為什麼地理書總是很想旅行？因為它每天都在講別的地方，自己卻從來沒去過。"),
                ("东北", f"{self.child_name}，再来一个。老师问：'谁能用一句话证明你很穷？'小明说：'我起床不是为了梦想，是为了不迟到。'老师说：'这个不算。'小明又说：'我的钱包比我的脸还干净。'老师点点头：'这个算。'{self.child_name}，咱起床不是为了梦想，是为了今天不被太阳落下，好不好？"),
                ("台湾", f"{self.child_name}，最後一個。有一隻烏龜對兔子說：'你跑得那麼快，為什麼還是輸給我？'兔子說：'因為我睡著了。'烏龜說：'不對，是因為我一直在走。'兔子說：'那你走得慢啊。'烏龜說：'慢沒關係，重要的是我不停下來。'{self.child_name}，今天也一步一步來，不著急。"),
            ]

    def get_opening(self):
        """开场白"""
        return [
            ("书童", f"{self.child_name}，{self.child_name}，起床喽。太阳公公已经出来了，小鸟也在窗外唱歌呢。书童来陪你一起起床啦。"),
        ]

    def get_transitions(self):
        """过渡语"""
        return [
            ("书童", f"{self.child_name}，醒了吗？我再给你讲一个，好不好？"),
            ("书童", f"{self.child_name}，你觉得刚才那个好笑吗？再听一个吧。"),
            ("书童", f"{self.child_name}，睁开眼睛，伸个懒腰，我们再来一个。"),
        ]

    def get_interactions(self):
        """互动环节，让孩子参与进来"""
        return [
            ("书童", f"{self.child_name}，你现在睁开眼睛了吗？如果睁开了，就眨三下眼睛，书童知道你在听。"),
            ("书童", f"{self.child_name}，来，跟书童一起伸个懒腰。双手举过头顶，一二三，啊——好舒服。"),
            ("书童", f"{self.child_name}，你昨天晚上做了什么梦？如果记得，可以小声告诉我；如果不记得，就摇摇头。"),
        ]

    def get_facts(self):
        """小知识/今日一问"""
        return [
            ("书童", f"{self.child_name}，今天书童考考你。你知道为什么早晨的太阳看起来是红色的吗？因为早晨阳光要穿过更厚的大气层，蓝光被散射掉了，红光就留下来了。你起来之后可以看看今天的太阳是什么颜色。"),
            ("书童", f"{self.child_name}，你知道吗？人每天早上醒来的时候，身体里有一种叫皮质醇的激素，它会帮我们清醒。所以只要睁开眼睛，慢慢坐起来，身体就会自己开机啦。"),
        ]

    def get_closing(self):
        """结束语"""
        return [
            ("书童", f"好啦，{self.child_name}，今天的晨起仪式到这里啦。你慢慢穿衣服，不用着急。记住，今天你只需要做一件小事：开心地过好今天。书童一直陪着你。"),
        ]

    # ═══════════════════════════════════════════
    # 音频混合
    # ═══════════════════════════════════════════

    def _add_silence(self, duration_ms):
        """添加静音片段"""
        self.segments.append(AudioSegment.silent(duration=duration_ms))

    def _add_tts(self, text, role="小艺", pause_after=500):
        """添加语音片段"""
        path = self.tts(text, role)
        audio = AudioSegment.from_mp3(path)
        self.segments.append(audio)
        if pause_after > 0:
            self._add_silence(pause_after)
        try:
            os.unlink(path)
        except Exception:
            pass

    def _add_music(self, duration_sec=90, volume_db=-15):
        """添加背景音乐"""
        path = self.generate_music(duration_sec=duration_sec)
        music = AudioSegment.from_wav(path).apply_gain(volume_db)
        self.segments.append(music)
        try:
            os.unlink(path)
        except Exception:
            pass

    def generate(self, target_minutes=6):
        """生成完整的晨起仪式音频，默认目标 6 分钟"""
        print(f"[晨起仪式] 为 {self.child_name}（{self.age}岁）生成起床仪式，目标 {target_minutes} 分钟...")

        # 1. 轻柔音乐开场 30 秒
        self._add_music(duration_sec=30, volume_db=-18)
        self._add_silence(500)

        # 2. 开场叫醒
        for text, role in self.get_opening():
            self._add_tts(text, role, pause_after=800)

        # 3. 互动 + 笑话循环，直到接近目标时长
        jokes = self.get_jokes()
        transitions = self.get_transitions()
        interactions = self.get_interactions()
        facts = self.get_facts()

        joke_idx = 0
        while True:
            current_sec = sum(len(s) for s in self.segments) / 1000
            if current_sec >= target_minutes * 60 - 60:
                break

            # 互动
            if joke_idx < len(interactions):
                self._add_tts(interactions[joke_idx][1], interactions[joke_idx][0], pause_after=1000)

            # 笑话
            role, joke = jokes[joke_idx % len(jokes)]
            self._add_tts(joke, role, pause_after=800)

            # 过渡或小知识
            if joke_idx % 2 == 0 and joke_idx // 2 < len(facts):
                self._add_tts(facts[joke_idx // 2][1], facts[joke_idx // 2][0], pause_after=800)
            elif joke_idx < len(transitions):
                self._add_tts(transitions[joke_idx][1], transitions[joke_idx][0], pause_after=600)

            joke_idx += 1

            # 防止无限循环
            if joke_idx > 15:
                break

        # 4. 结束鼓励
        for text, role in self.get_closing():
            self._add_tts(text, role, pause_after=800)

        # 5. 结尾音乐 45 秒
        self._add_music(duration_sec=45, volume_db=-18)

        # 混合所有片段
        final = AudioSegment.empty()
        for seg in self.segments:
            final += seg

        # 导出
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{self.child_name}_晨起仪式_{timestamp}.mp3"
        out_path = OUTPUT_DIR / filename
        final.export(out_path, format="mp3", bitrate="192k")

        duration_min = len(final) / 1000 / 60
        print(f"[晨起仪式] 已生成: {out_path}")
        print(f"[晨起仪式] 时长: {duration_min:.1f} 分钟")
        return out_path


if __name__ == "__main__":
    gen = MorningRitualGenerator(child_name="小橙子", age=8, interests=["磁力片", "数独", "运动"])
    audio_path = gen.generate(target_minutes=6)
    print(f"\n文件路径: {audio_path}")
