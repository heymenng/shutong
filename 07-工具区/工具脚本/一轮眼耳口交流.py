#!/usr/bin/env python3
"""
伴读书童AI - 一轮眼耳口交流

流程：
1. 睁眼：拍照 + 人脸识别
2. 竖耳：听 8 秒，语音识别
3. 思考：调用完整大脑生成回复
4. 开口：语音播报回复
5. 保存本轮记录
"""

import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "03-引擎区"))

from 书童程序.核心.系统核心 import BookBoySystem


def main():
    print("=" * 60)
    print("伴读书童AI · 一轮眼耳口交流")
    print("=" * 60)
    print("\n书童正在唤醒眼睛、耳朵和嘴巴...")
    
    bookboy = BookBoySystem()
    
    # 1. 睁眼
    print("\n👁️ 书童睁眼看...")
    look_result = bookboy.look_at_camera(save=True)
    print(f"   拍照: {'成功' if look_result['success'] else '失败'}")
    print(f"   人脸: {look_result['face_count']} 张")
    print(f"   认出: {look_result['recognized'] or '无'}")
    
    recognized = look_result.get("recognized")
    speaker_id = recognized if recognized else "default"
    speaker_name = recognized if recognized else "师父"
    
    # 2. 竖耳
    print("\n👂 书童竖耳听，请师父说话（8秒）...")
    listen_result = bookboy.speech.listen_once(duration_seconds=8, verbose=True)
    heard_text = listen_result.get("text", "").strip()
    print(f"   听到: {heard_text if heard_text else '（没听清）'}")
    
    if not heard_text:
        response = "师父，书童没听清，您能再说一遍吗？"
        bookboy.voice.speak(response)
        print(f"\n书童：{response}")
        return
    
    # 3. 思考 + 4. 开口
    labeled_input = f"[{speaker_name}] {heard_text}"
    print("\n💭 书童思考中...")
    response = bookboy.chat(labeled_input, child_id=speaker_id, verbose_thinking=False)
    print(f"\n书童：\n{response}")
    
    # 5. 保存记录
    try:
        journal_dir = Path(bookboy.sensory.journal_dir)
        log_file = journal_dir / f"eye_ear_mouth_{datetime.now().strftime('%Y%m%d')}.md"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n## {datetime.now().strftime('%H:%M:%S')}\n\n")
            f.write(f"**看到**: {look_result}\n\n")
            f.write(f"**听到**: {heard_text}\n\n")
            f.write(f"**书童说**: {response}\n\n")
            f.write("---\n")
        print(f"\n[日志] 已保存: {log_file}")
    except Exception as e:
        print(f"\n[日志] 保存失败: {e}")


if __name__ == "__main__":
    main()
