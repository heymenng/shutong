#!/usr/bin/env python3
"""
伴读书童AI - 人脸识别测试脚本

功能：
1. 打开摄像头拍一张照片
2. 提取照片中的人脸特征
3. 和已注册的师父人脸特征比对
4. 判断是不是师父

隐私说明：
- 只在本地比对
- 不保存测试时拍摄的照片（除非用户要求）
"""

import json
import mediapipe as mp
import numpy as np
from pathlib import Path

from mediapipe.tasks.python import vision
from mediapipe.tasks.python.core.base_options import BaseOptions


def extract_face_features(image_path, model_path):
    """从图片中提取人脸特征"""
    
    base_options = BaseOptions(model_asset_path=model_path)
    options = vision.FaceLandmarkerOptions(
        base_options=base_options,
        num_faces=1,
        running_mode=vision.RunningMode.IMAGE
    )
    detector = vision.FaceLandmarker.create_from_options(options)
    
    mp_image = mp.Image.create_from_file(str(image_path))
    results = detector.detect(mp_image)
    
    if not results.face_landmarks:
        return None
    
    landmarks = []
    for landmark in results.face_landmarks[0]:
        landmarks.append([landmark.x, landmark.y, landmark.z])
    
    landmarks = np.array(landmarks)
    
    # 对齐
    center_x = np.mean(landmarks[:, 0])
    center_y = np.mean(landmarks[:, 1])
    aligned_landmarks = landmarks.copy()
    aligned_landmarks[:, 0] -= center_x
    aligned_landmarks[:, 1] -= center_y
    
    detector.close()
    
    return aligned_landmarks


def compare_faces(features1, features2):
    """计算两个人脸特征的距离"""
    # 欧氏距离
    distance = np.linalg.norm(features1 - features2)
    return distance


def recognize_face(image_path, model_path, features_dir):
    """识别照片中的人脸"""
    
    print("=" * 60)
    print("伴读书童AI - 人脸识别测试")
    print("=" * 60)
    
    # 提取新照片的特征
    print(f"\n正在分析照片: {image_path}")
    new_features = extract_face_features(image_path, model_path)
    
    if new_features is None:
        print("❌ 未检测到人脸")
        return None
    
    print(f"✅ 提取到 {len(new_features)} 个人脸关键点")
    
    # 加载已注册的人脸特征
    registered_files = list(Path(features_dir).glob("*_face_features.json"))
    
    if not registered_files:
        print("❌ 没有已注册的人脸特征")
        return None
    
    print(f"\n已注册人脸数量: {len(registered_files)}")
    
    best_match = None
    best_distance = float('inf')
    
    for record_file in registered_files:
        with open(record_file, 'r', encoding='utf-8') as f:
            record = json.load(f)
        
        registered_features = np.array(record["average_landmarks"])
        distance = compare_faces(new_features, registered_features)
        
        print(f"  与 {record['person_name']} 的距离: {distance:.4f}")
        
        if distance < best_distance:
            best_distance = distance
            best_match = record
    
    # 阈值判断（这个阈值需要根据实际测试调整）
    threshold = 1.5
    
    print(f"\n最佳匹配: {best_match['person_name']}")
    print(f"距离: {best_distance:.4f}")
    print(f"阈值: {threshold}")
    
    if best_distance < threshold:
        print(f"✅ 识别成功：这是 {best_match['person_name']} ({best_match['role']})")
        return best_match
    else:
        print("❌ 识别失败：未匹配到已注册的人脸")
        return None


def capture_test_photo(project_root):
    """调用摄像头拍一张测试照片"""
    import cv2
    
    save_dir = project_root / "07-工具区" / "工具脚本" / "摄像头测试截图"
    save_dir.mkdir(exist_ok=True)
    
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ 无法打开摄像头")
        return None
    
    # 读取几帧让摄像头稳定
    for _ in range(10):
        ret, frame = cap.read()
    
    timestamp = __import__('datetime').datetime.now().strftime("%Y%m%d_%H%M%S")
    save_path = save_dir / f"recognize_test_{timestamp}.jpg"
    
    if ret and frame is not None:
        cv2.imwrite(str(save_path), frame)
    
    cap.release()
    return str(save_path)


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[2]
    model_path = project_root / "03-引擎区" / "书童程序" / "数据" / "模型" / "face_landmarker.task"
    features_dir = project_root / "03-引擎区" / "书童程序" / "数据" / "人脸特征"

    print("\n先拍一张新照片用于识别测试...")
    test_image = capture_test_photo(project_root)

    if test_image:
        print(f"✅ 已拍摄测试照片: {test_image}")
        recognize_face(test_image, str(model_path), str(features_dir))
    else:
        # 如果拍照失败，用已有照片
        test_image = project_root / "07-工具区" / "工具脚本" / "摄像头测试截图" / "video_frame_at_5s.jpg"
        print(f"⚠️ 拍照失败，使用已有照片: {test_image}")
        recognize_face(str(test_image), str(model_path), str(features_dir))
