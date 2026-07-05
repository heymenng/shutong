#!/usr/bin/env python3
"""
伴读书童AI - 摄像头录像测试脚本

功能：
1. 打开默认摄像头
2. 录制指定时长的视频
3. 保存为 MP4 文件
4. 自动关闭摄像头

注意：
- 仅用于测试
- 录制完成后自动停止
- 不长期监控
"""

import cv2
import sys
from datetime import datetime
from pathlib import Path


def record_video(duration_seconds=10, fps=20):
    """录制视频"""
    
    # 项目根目录
    project_root = Path(__file__).resolve().parents[2]
    save_dir = project_root / "07-工具区" / "工具脚本" / "摄像头测试截图"
    save_dir.mkdir(exist_ok=True)
    
    # 生成文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_path = save_dir / f"camera_video_{timestamp}.mp4"
    
    print("=" * 60)
    print("伴读书童AI - 摄像头录像测试")
    print("=" * 60)
    print(f"保存路径: {save_path}")
    print(f"录制时长: {duration_seconds} 秒")
    print(f"帧率: {fps} fps")
    print("正在打开摄像头...")
    
    # 打开默认摄像头
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("❌ 无法打开摄像头")
        sys.exit(1)
    
    # 获取画面尺寸
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"✅ 摄像头已打开: {width}x{height}")
    
    # 设置视频编码器
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(str(save_path), fourcc, fps, (width, height))
    
    if not out.isOpened():
        print("❌ 无法创建视频文件，尝试使用 AVI 格式...")
        save_path = save_dir / f"camera_video_{timestamp}.avi"
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        out = cv2.VideoWriter(str(save_path), fourcc, fps, (width, height))
    
    print(f"✅ 开始录制...")
    
    frame_count = 0
    total_frames = duration_seconds * fps
    
    while frame_count < total_frames:
        ret, frame = cap.read()
        if not ret:
            print("❌ 读取画面失败")
            break
        
        out.write(frame)
        frame_count += 1
        
        # 每秒钟打印一次进度
        if frame_count % fps == 0:
            seconds = frame_count // fps
            print(f"  已录制 {seconds}/{duration_seconds} 秒")
    
    # 释放资源
    cap.release()
    out.release()
    
    print(f"✅ 视频已保存: {save_path}")
    print(f"✅ 总帧数: {frame_count}")
    print("✅ 摄像头已关闭")
    print("=" * 60)
    print("录制完成")
    print("=" * 60)
    
    return str(save_path)


if __name__ == "__main__":
    # 默认录制10秒
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    record_video(duration_seconds=duration)
