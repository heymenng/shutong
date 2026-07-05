#!/usr/bin/env python3
"""
伴读书童AI - 人脸注册脚本

功能：
1. 从照片中提取人脸特征（使用 MediaPipe Face Landmarker）
2. 保存人脸特征到本地
3. 仅用于本地识别，不上传云端

隐私说明：
- 只保存人脸关键点坐标，不保存原始照片
- 家长/本人可随时删除
"""

import json
import mediapipe as mp
import numpy as np
import sys
from datetime import datetime
from pathlib import Path

# MediaPipe Task API
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.core.base_options import BaseOptions


def extract_face_features(image_path, model_path):
    """从图片中提取人脸特征"""
    
    # 创建 Face Landmarker
    base_options = BaseOptions(model_asset_path=model_path)
    options = vision.FaceLandmarkerOptions(
        base_options=base_options,
        num_faces=1,
        running_mode=vision.RunningMode.IMAGE
    )
    detector = vision.FaceLandmarker.create_from_options(options)
    
    # 读取图片
    mp_image = mp.Image.create_from_file(str(image_path))
    results = detector.detect(mp_image)
    
    if not results.face_landmarks:
        print("❌ 未检测到人脸")
        return None
    
    # 获取第一张脸的关键点（478 个）
    landmarks = []
    for landmark in results.face_landmarks[0]:
        landmarks.append([landmark.x, landmark.y, landmark.z])
    
    landmarks = np.array(landmarks)
    
    # 计算人脸中心点（用于对齐）
    center_x = np.mean(landmarks[:, 0])
    center_y = np.mean(landmarks[:, 1])
    
    # 以中心点为原点，重新对齐
    aligned_landmarks = landmarks.copy()
    aligned_landmarks[:, 0] -= center_x
    aligned_landmarks[:, 1] -= center_y
    
    detector.close()
    
    return {
        "landmarks": aligned_landmarks.tolist(),
        "num_landmarks": len(landmarks)
    }


def register_face(person_name, role, image_paths, model_path):
    """注册一个人脸"""
    
    print("=" * 60)
    print(f"伴读书童AI - 人脸注册: {person_name}")
    print("=" * 60)
    
    all_features = []
    valid_images = []
    
    for image_path in image_paths:
        print(f"\n正在处理: {image_path}")
        features = extract_face_features(image_path, model_path)
        if features:
            all_features.append(features["landmarks"])
            valid_images.append(str(image_path))
            print(f"✅ 提取到 {features['num_landmarks']} 个人脸关键点")
        else:
            print(f"❌ 未能从该图片提取人脸")
    
    if not all_features:
        print("\n❌ 所有图片都未检测到人脸，注册失败")
        return None
    
    # 计算平均特征
    avg_features = np.mean(np.array(all_features), axis=0).tolist()
    
    # 保存到文件
    project_root = Path(__file__).resolve().parents[2]
    face_dir = project_root / "03-引擎区" / "书童程序" / "数据" / "人脸特征"
    face_dir.mkdir(parents=True, exist_ok=True)
    
    record = {
        "person_name": person_name,
        "role": role,
        "registered_at": datetime.now().isoformat(),
        "feature_type": "mediapipe_face_landmarker_478",
        "average_landmarks": avg_features,
        "sample_images": valid_images,
        "num_samples": len(all_features)
    }
    
    record_file = face_dir / f"{role}_face_features.json"
    with open(record_file, 'w', encoding='utf-8') as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 人脸特征已保存: {record_file}")
    print(f"✅ 使用了 {len(all_features)} 张样本照片")
    print("=" * 60)
    
    return record_file


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[2]
    screenshot_dir = project_root / "07-工具区" / "工具脚本" / "摄像头测试截图"
    model_path = project_root / "03-引擎区" / "书童程序" / "数据" / "模型" / "face_landmarker.task"
    
    image_paths = [
        screenshot_dir / "video_frame_at_1s.jpg",
        screenshot_dir / "video_frame_at_5s.jpg",
    ]
    
    # 自动添加最新的识别测试照片作为新样本
    test_images = sorted(screenshot_dir.glob("recognize_test_*.jpg"))
    if test_images:
        image_paths.append(test_images[-1])
        print(f"[注册] 自动添加新样本: {test_images[-1]}")
    
    register_face("师父", "master", image_paths, str(model_path))
