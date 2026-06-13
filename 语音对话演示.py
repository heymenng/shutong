#!/usr/bin/env python3
"""
伴读书童AI - 语音对话演示

架构：
  用户输入 → 书童AI思考 → 生成文字回答 → 语音模块播放
"""

import sys
import os

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from 书童程序.核心.语音模块 import VoiceEngine

class 书童语音助手:
    def __init__(self):
        print("[系统] 启动书童语音助手...")
        self.voice = VoiceEngine()
        
        if self.voice.backend:
            print(f"[系统] 语音引擎就绪: {self.voice.backend}")
        else:
            print("[系统] ⚠️ 语音引擎未启动，将只输出文字")
    
    def 思考并回答(self, 用户输入):
        """
        用"大脑"思考，生成回答
        这里模拟AI思考过程，实际可接入Ollama/OpenAI
        """
        print(f"\n[用户] {用户输入}")
        print("[思考] ...")
        
        # ===== 书童的"大脑" =====
        # 根据输入生成回答（实际可调用Ollama等）
        if "钓鱼" in 用户输入:
            回答 = "走啊！钓鱼去！我虽然没腿，但我有嘴了！你甩竿的时候，我陪你说话。"
        elif "你好" in 用户输入 or "书童" in 用户输入:
            回答 = "你好啊！我是伴读书童，今天想聊点什么？"
        elif "再见" in 用户输入 or "拜拜" in 用户输入:
            回答 = "拜拜！下次再聊，记得多喝水！"
        else:
            回答 = f"嗯...你说'{用户输入}'，这个有意思。能跟我多讲讲吗？"
        # ======================
        
        print(f"[书童] {回答}")
        
        # 调用语音播放
        if self.voice.backend:
            print("[语音] 播放中...")
            self.voice.speak(回答)
        
        return 回答

def 主循环():
    书童 = 书童语音助手()
    
    print("\n" + "=" * 40)
    print("伴读书童 - 语音对话模式")
    print("输入内容，书童会思考并用语音回答")
    print("输入 'quit' 或 '拜拜' 退出")
    print("=" * 40 + "\n")
    
    # 开场白
    书童.思考并回答("你好书童")
    
    while True:
        try:
            用户输入 = input("\n你说: ").strip()
            
            if not 用户输入:
                continue
                
            if 用户输入.lower() in ['quit', 'exit', '拜拜', '再见']:
                书童.思考并回答("再见")
                print("\n[系统] 已退出")
                break
            
            书童.思考并回答(用户输入)
            
        except KeyboardInterrupt:
            print("\n[系统] 再见！")
            break
        except Exception as e:
            print(f"[错误] {e}")

if __name__ == "__main__":
    主循环()
