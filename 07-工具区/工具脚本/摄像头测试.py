#!/usr/bin/env python3
"""
伴读书童AI - 摄像头测试脚本

功能：
1. 打开默认摄像头
2. 读取一帧画面
3. 保存为图片文件
4. 释放摄像头资源

注意：
- 仅用于测试摄像头硬件是否可用
- 不存储视频流
- 拍照后自动关闭摄像头
"""

import cv2
import sys
from datetime import datetime
from pathlib import Path


def test_camera():
    """测试摄像头并拍照"""
    
    # 项目根目录
    project_root = Path(__file__).resolve().parents[2]
    save_dir = project_root / "07-工具区" / "工具脚本" / "摄像头测试截图"
    save_dir.mkdir(exist_ok=True)
    
    # 生成文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_path = save_dir / f"camera_test_{timestamp}.jpg"
    
    print("=" * 60)
    print("伴读书童AI - 摄像头测试")
    print("=" * 60)
    print(f"保存路径: {save_path}")
    print("正在打开摄像头...")
    
    # 尝试多个摄像头索引（Mac可能有多个摄像头）
    cap = None
    for camera_idx in [1, 0]:
        cap = cv2.VideoCapture(camera_idx)
        if cap.isOpened():
            ret, test_frame = cap.read()
            if ret and test_frame is not None:
                print(f"✅ 摄像头已打开（索引 {camera_idx}）")
                break
        cap.release()
        cap = None
    
    if cap is None or not cap.isOpened():
        print("❌ 无法打开摄像头")
        print("可能原因：")
        print("  - 摄像头被其他应用占用")
        print("  - 没有摄像头设备")
        print("  - 权限未授权")
        sys.exit(1)
    
    print("正在读取画面...")
    
    # 读取几帧，让摄像头自动对焦/调整亮度
    for _ in range(10):
        ret, frame = cap.read()
        if ret:
            break
    
    if not ret or frame is None:
        print("❌ 无法读取画面")
        cap.release()
        sys.exit(1)
    
    print(f"✅ 读取画面成功: {frame.shape[1]}x{frame.shape[0]} 像素")
    
    # 保存图片
    cv2.imwrite(str(save_path), frame)
    print(f"✅ 图片已保存: {save_path}")
    
    # 释放摄像头
    cap.release()
    print("✅ 摄像头已关闭")
    
    print("=" * 60)
    print("测试完成")
    print("=" * 60)
    
    return str(save_path)


if __name__ == "__main__":
    test_camera()
