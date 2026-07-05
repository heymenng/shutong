"""伴读书童AI - 心力成长系统

TODO: 待集成。当前未被主系统调用，但内容有价值（音乐库、冥想引导词），
未来应集成到日课系统/睡前仪式/情绪崩溃陪伴场景中。

核心定位：不是"打坐修行"，是"安静下来的游戏"。
通过音乐 + 冥想引导 + 睡前仪式，帮助孩子提升专注力、情绪调节力、
抗干扰能力和内在平静感，从根本上增强心能力，对抗手机/游戏成瘾。

来源：每日冥想静坐系统 V1.0（师父点化 + 师兄医学框架）
"""

import asyncio
import json
import random
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional


class HeartPowerSystem:
    """心力成长系统"""
    
    # 七日主题轮换
    WEEKLY_THEMES = {
        0: {"name": "回到身体", "keyword": "身体、呼吸、扎根", "music": ["R-01", "C-07", "N-03"]},
        1: {"name": "专注之灯", "keyword": "注意力、光、专注", "music": ["C-08", "G-01", "C-05"]},
        2: {"name": "情绪小怪兽", "keyword": "情绪、颜色、命名", "music": ["V-03", "C-03", "G-05"]},
        3: {"name": "能量充电", "keyword": "能量、太阳、充电", "music": ["G-03", "N-05", "R-03"]},
        4: {"name": "感恩花园", "keyword": "感谢、花朵、温暖", "music": ["V-04", "G-06", "C-02"]},
        5: {"name": "想象力飞行", "keyword": "飞行、宇宙、冒险", "music": ["C-06", "C-05", "N-04"]},
        6: {"name": "安静港湾", "keyword": "港湾、停泊、安眠", "music": ["G-08", "G-02", "N-01"]},
    }
    
    # 中国传统五音疗法音乐
    MUSIC_LIBRARY = {
        "G-01": {"name": "高山流水", "mode": "宫调", "organ": "脾/胃", "effect": "安定、踏实", "scene": "睡前、焦虑时"},
        "G-02": {"name": "梅花三弄", "mode": "羽调", "organ": "肾/膀胱", "effect": "沉静、助眠", "scene": "睡前、夜醒后"},
        "G-03": {"name": "十面埋伏", "mode": "徵调", "organ": "心/小肠", "effect": "振奋、温暖", "scene": "晨起、低落时"},
        "G-04": {"name": "阳春白雪", "mode": "商调", "organ": "肺/大肠", "effect": "清凉、平静", "scene": "烦躁、发热时"},
        "G-05": {"name": "胡笳十八拍", "mode": "角调", "organ": "肝/胆", "effect": "舒展、放松", "scene": "生气、紧张时"},
        "G-06": {"name": "渔舟唱晚", "mode": "宫调变奏", "organ": "脾/胃", "effect": "温和、滋养", "scene": "任何时间"},
        "G-07": {"name": "平沙落雁", "mode": "羽调变奏", "organ": "肾/膀胱", "effect": "悠远、宁静", "scene": "深度放松"},
        "G-08": {"name": "春江花月夜", "mode": "宫羽合调", "organ": "脾肾双补", "effect": "圆满、安眠", "scene": "睡前黄金曲"},
        "N-01": {"name": "雨滴芭蕉", "sound": "雨声+古琴", "effect": "清凉、洗涤", "scene": "夏日、烦躁时"},
        "N-02": {"name": "竹林风语", "sound": "竹叶声+箫", "effect": "清凉、通透", "scene": "生气后、春季"},
        "N-03": {"name": "山涧清泉", "sound": "流水+鸟鸣", "effect": "流动、清新", "scene": "任何时间"},
        "N-04": {"name": "海边日落", "sound": "海浪+海鸥", "effect": "开阔、放下", "scene": "压力大、哭泣后"},
        "N-05": {"name": "晨间森林", "sound": "鸟鸣+溪水", "effect": "苏醒、希望", "scene": "晨起、唤醒"},
        "N-06": {"name": "雪地静谧", "sound": "落雪+钟声", "effect": "纯净、静止", "scene": "冬日、极度安静"},
        "N-07": {"name": "篝火夜晚", "sound": "木柴燃烧+虫鸣", "effect": "温暖、安全", "scene": "害怕、孤独时"},
        "N-08": {"name": "草原星空", "sound": "风声+马头琴", "effect": "辽阔、自由", "scene": "愤怒、放下时"},
        "C-01": {"name": "小星星的梦", "style": "钢琴+八音盒", "age": "0-3岁", "effect": "梦幻、安眠"},
        "C-02": {"name": "云朵棉花糖", "style": "竖琴+长笛", "age": "3-6岁", "effect": "柔软、甜蜜"},
        "C-03": {"name": "森林小精灵", "style": "木琴+手风琴", "age": "3-6岁", "effect": "想象、冒险"},
        "C-04": {"name": "月光下的猫咪", "style": "大提琴+钢琴", "age": "6-9岁", "effect": "温柔、陪伴"},
        "C-05": {"name": "深海潜水艇", "style": "电子合成+水声", "age": "6-12岁", "effect": "探索、沉浸"},
        "C-06": {"name": "宇宙漂流瓶", "style": "电子氛围音", "age": "9-15岁", "effect": "浩瀚、哲思"},
        "C-07": {"name": "心跳的节拍", "style": "手鼓+心跳低频", "age": "全年龄", "effect": "grounding"},
        "C-08": {"name": "呼吸的颜色", "style": "渐变合成音", "age": "6-15岁", "effect": "可视化呼吸"},
        "R-01": {"name": "鼓点心跳", "rhythm": "60-80BPM", "effect": "grounding", "scene": "坐不住时"},
        "R-02": {"name": "雨棍漫步", "rhythm": "雨棍+脚步", "effect": "平静", "scene": "多动时"},
        "R-03": {"name": "非洲鼓圈", "rhythm": "重复鼓点", "effect": "释放后平静", "scene": "需要释放能量"},
        "R-04": {"name": "沙锤呼吸", "rhythm": "沙锤+呼吸", "effect": "呼吸训练", "scene": "呼吸入门"},
        "V-01": {"name": "月亮婆婆讲故事", "voice": "温柔女声", "effect": "故事化入睡"},
        "V-02": {"name": "身体扫描之旅", "voice": "平和男声", "effect": "身体放松"},
        "V-03": {"name": "情绪小怪兽", "voice": "童趣女声", "effect": "识别情绪"},
        "V-04": {"name": "感恩花园", "voice": "温暖女声", "effect": "感恩练习"},
    }
    
    # 分龄冥想引导词模板（简化版，完整版见文档）
    SCRIPT_TEMPLATES = {
        "S1-S2": {
            "回到身体": "小宝贝，妈妈在抱着你呢。听，这是小星星的音乐。星星在天上，一闪一闪。你的身体，也像小星星一样，软软的，亮亮的。",
            "情绪小怪兽": "我们来玩一个'情绪小怪兽'的游戏。今天，这个小怪兽是什么颜色的？不管它是什么颜色，你都跟它说：'你好呀，小怪兽，我看见你了。'",
        },
        "S3": {
            "回到身体": "我们来玩'身体探险'游戏。现在，你是一个小探险家，要去探索自己的身体王国。先找到你的大本营——小肚子。",
            "专注之灯": "今天，我们来点亮一盏'专注之灯'。想象你的心里有一盏小灯。当你专心的时候，这盏灯就亮亮的。",
            "情绪小怪兽": "今天，我们要认识心里的'情绪小怪兽'。闭上眼睛，想象你面前有一个大花园。花园里有各种颜色的花。",
            "感恩花园": "今天，我们去逛一个特别的花园——感恩花园。这个花园里，种的不是花，是'谢谢'。",
        },
        "S4": {
            "回到身体": "这一周开始了，我们来做一个'身体扫描'，让自己回到最舒服的状态。找一个舒服的姿势坐着，手放在膝盖上。",
            "专注之灯": "今天，我们来训练一个超级能力——专注力。你知道吗？专注力就像肌肉，越练越强。",
            "能量充电": "周四了，一周过半，你可能觉得有点累。今天，我们先'放电'，再'充电'。",
        },
        "S5": {
            "回到身体": "这一周开始了，你可能有很多事要处理。很多时候，我们的脑子转得太快，身体却跟不上。今天，只做一件事：回到身体。",
            "情绪小怪兽": "青春期，情绪像过山车。这不是你有问题，这是你的大脑在重建。今天，我们来做一个'情绪观察'练习。",
            "想象力飞行": "这一周辛苦了。今天不训练，只放飞。闭上眼睛，想象你变成了一道光，从地球出发，飞向宇宙。",
        },
        "S6": {
            "回到身体": "找一个舒服的姿势，坐着或躺着。今天，做一个完整的身体扫描，从头顶到脚底。不需要控制呼吸，只是观察。",
            "情绪小怪兽": "今天，做一个'情绪觉察'练习。不是解决情绪，只是看见它。情绪是信使，它在传递信息。",
            "安静港湾": "周日，一周的结束，新一周的开始。今天不做身体扫描，不做情绪觉察，只做一件事——安静。",
        },
    }
    
    def __init__(self, child_name: str = "小朋友", age_stage: str = "S3"):
        self.child_name = child_name
        self.age_stage = age_stage
        self.records_dir = Path(__file__).parent.parent / "数据" / "修行记录" / "心力成长"
        self.records_dir.mkdir(parents=True, exist_ok=True)
    
    def get_today_theme(self) -> dict:
        """获取今日主题"""
        weekday = datetime.now().weekday()
        return self.WEEKLY_THEMES[weekday]
    
    def select_music(self, mood: Optional[str] = None) -> dict:
        """根据主题和情绪选择音乐"""
        theme = self.get_today_theme()
        music_id = theme["music"][0]
        
        # 根据情绪微调
        mood_map = {
            "兴奋": "R-01",
            "烦躁": "G-05",
            "难过": "C-04",
            "害怕": "C-01",
            "紧张": "G-02",
            "疲惫": "G-07",
            "无聊": "G-03",
        }
        if mood and mood in mood_map:
            music_id = mood_map[mood]
        
        music = self.MUSIC_LIBRARY.get(music_id, {})
        return {"id": music_id, **music}
    
    def get_script(self) -> str:
        """获取今日冥想引导词"""
        theme = self.get_today_theme()
        theme_name = theme["name"]
        
        age_templates = self.SCRIPT_TEMPLATES.get(self.age_stage, self.SCRIPT_TEMPLATES["S3"])
        script = age_templates.get(theme_name, f"今天我们一起做一个'安静游戏'，主题是{theme_name}。")
        
        return f"{self.child_name}，{script}"
    
    def get_bedtime_ritual(self) -> dict:
        """获取完整睡前仪式"""
        theme = self.get_today_theme()
        music = self.select_music()
        script = self.get_script()
        
        return {
            "time": "睡前30分钟",
            "steps": [
                {"step": 1, "name": "环境准备", "content": "调暗灯光，关闭电子设备，播放助眠音乐"},
                {"step": 2, "name": "过渡引导", "content": "今天的故事讲完了，我们来做一个'安静游戏'"},
                {"step": 3, "name": "主体冥想", "content": f"今日主题：{theme['name']} - {script[:50]}..."},
                {"step": 4, "name": "收尾过渡", "content": "慢慢睁开眼睛，感受身体重重还是轻轻"},
                {"step": 5, "name": "睡眠过渡", "content": "继续播放助眠音乐，书童说晚安"},
            ],
            "music": music,
            "theme": theme,
            "script": script,
        }
    
    def record_session(self, duration: int, mood_before: str, mood_after: str, notes: str = ""):
        """记录一次心力成长 session"""
        record = {
            "timestamp": datetime.now().isoformat(),
            "child_name": self.child_name,
            "age_stage": self.age_stage,
            "theme": self.get_today_theme(),
            "duration": duration,
            "mood_before": mood_before,
            "mood_after": mood_after,
            "notes": notes,
        }
        
        date_str = datetime.now().strftime("%Y%m%d")
        record_file = self.records_dir / f"{self.child_name}_{date_str}.jsonl"
        with open(record_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        
        return record
