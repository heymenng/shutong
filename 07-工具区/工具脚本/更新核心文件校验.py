#!/usr/bin/env python3
"""
伴读书童AI - 更新核心文件校验哈希（带师父认证）

用途：
当师父合法修改 AGENTS.md 或 WORKFLOW.md 后，运行此脚本更新校验文件。
此脚本需要【人脸识别 + 师父口令】双重认证，不能由书童自动运行。

安全原则：
- 道统核心文件是书童的灵魂，更新必须确认是师父本人授权。
- 当前版本为本地简单实现：人脸检测 + 口令认证。
- 未来升级为真实人脸识别（人脸特征匹配）+ 声纹 + 硬件密钥。

运行方式：
  正常模式（师父手动操作）：
    .venv/bin/python 07-工具区/工具脚本/更新核心文件校验.py
  
  自动模式（书童代操作，测试用）：
    .venv/bin/python 07-工具区/工具脚本/更新核心文件校验.py --auto
"""

import argparse
import hashlib
import json
import secrets
import sys
import time
from pathlib import Path
from datetime import datetime

# 人脸识别依赖 OpenCV，优先使用项目虚拟环境
try:
    import cv2
except ImportError:
    print("❌ 需要 OpenCV 才能进行人脸识别认证")
    print("请使用项目虚拟环境运行：")
    print("  .venv/bin/python 07-工具区/工具脚本/更新核心文件校验.py")
    sys.exit(1)


def compute_sha256(file_path):
    """计算文件 SHA256 哈希"""
    h = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def capture_face_snapshot(save_dir):
    """
    打开摄像头拍照，并进行人脸检测。
    
    返回: (snapshot_path, status)
    - snapshot_path: 照片保存路径，失败则为 None
    - status: "人脸检测通过" / "未检测到人脸" / "检测到多张人脸" / 错误信息
    """
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    
    # Mac 通常优先使用索引 1，失败回退 0
    cap = cv2.VideoCapture(1)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        return None, "无法打开摄像头"
    
    frame = None
    for _ in range(20):
        ret, frame = cap.read()
        if ret and frame is not None:
            break
    cap.release()
    
    if frame is None:
        return None, "无法读取画面"
    
    # 保存原始照片
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_path = save_dir / f"master_auth_{timestamp}.jpg"
    cv2.imwrite(str(snapshot_path), frame)
    
    # 人脸检测
    try:
        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(120, 120)
        )
        
        if len(faces) == 0:
            return str(snapshot_path), "未检测到人脸"
        elif len(faces) > 1:
            return str(snapshot_path), "检测到多张人脸"
        else:
            return str(snapshot_path), "人脸检测通过"
    except Exception as e:
        return str(snapshot_path), f"人脸检测出错: {e}"


def load_or_setup_master_password(config_path, auto_mode=False, auto_password=None):
    """
    加载或首次设置师父口令。
    口令以 SHA256 哈希保存，不保存明文。
    
    auto_mode 为 True 时：
    - 如果没有配置文件，自动生成随机口令并保存
    - 返回 (password_hash, actual_password_plaintext)
    """
    config_path = Path(config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    if not config_path.exists():
        if auto_mode:
            # 自动生成随机口令
            if auto_password is None:
                auto_password = secrets.token_urlsafe(16)
            print(f"🤖 自动模式：已生成临时口令（请师父牢记，测试后可重置）：{auto_password}")
        else:
            print("\n⚠️ 首次使用认证系统，需要设置师父口令。")
            print("此口令将用于未来更新道统核心文件时的身份验证。")
            print("（当前为简单实现，输入时可见，未来升级为隐藏输入。）")
            
            auto_password = input("请设置师父口令：").strip()
            confirm_pass = input("请再次输入以确认：").strip()
            
            if not auto_password or auto_password != confirm_pass:
                print("❌ 口令不一致或为空，认证失败。")
                return None, None
        
        auth_config = {
            "created_at": datetime.now().isoformat(),
            "password_hash": hashlib.sha256(auto_password.encode()).hexdigest(),
            "note": "师父口令哈希，用于更新道统核心文件时认证",
            "auto_generated": auto_mode
        }
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(auth_config, f, ensure_ascii=False, indent=2)
        
        print("✅ 师父口令已设置。")
    else:
        # 配置文件已存在
        if auto_mode and auto_password:
            # 自动模式下使用给定口令验证，但不覆盖配置
            pass
        elif auto_mode and not auto_password:
            # 自动模式但未给口令，读取现有配置后返回明文 None
            pass
    
    with open(config_path, 'r', encoding='utf-8') as f:
        auth_config = json.load(f)
    
    return auth_config.get("password_hash", ""), auto_password


def authenticate_master(project_root, auto_mode=False, auto_password=None, no_camera=False):
    """
    师父身份认证：人脸识别 + 口令。
    认证通过返回 (True, actual_password)，否则返回 (False, None)。
    
    no_camera 为 True 时：跳过摄像头，仅用于测试或无摄像头环境。
    """
    print("\n" + "=" * 60)
    print("【师父身份认证】")
    print("=" * 60)
    print("此操作将更新道统核心文件（AGENTS.md / WORKFLOW.md）的校验哈希。")
    print("根据书童安全机制，需要【人脸识别 + 师父口令】双重认证。")
    print()
    
    auth_dir = project_root / "03-引擎区" / "书童程序" / "数据" / "认证记录"
    auth_config_path = project_root / "03-引擎区" / "书童程序" / "数据" / "师父认证配置.json"
    
    # 第一步：人脸检测
    if no_camera:
        print("【第一步】人脸识别（已跳过）")
        print("⚠️ 当前为无摄像头模式，仅用于测试。")
        print("   生产环境请在 iTerm/Terminal 中运行完整模式。")
        face_status = "无摄像头模式跳过"
        snapshot_path = "无"
        print("✅ 人脸检测步骤已跳过")
    else:
        print("【第一步】人脸识别")
        
        if auto_mode:
            print("🤖 自动模式：请师父面向摄像头，5 秒后自动拍照。")
            for i in range(5, 0, -1):
                print(f"  倒计时: {i} 秒")
                time.sleep(1)
            print("  拍照中...")
        else:
            print("请师父面向摄像头，保持面部在画面中央。")
            input("确认已面向摄像头后，按回车键拍照：")
        
        snapshot_path, face_status = capture_face_snapshot(auth_dir)
        
        if snapshot_path:
            print(f"📷 已拍照: {snapshot_path}")
            print(f"🔍 人脸检测结果: {face_status}")
        else:
            print(f"❌ {face_status}")
            return False, None
        
        if face_status != "人脸检测通过":
            print("❌ 认证失败：未检测到清晰、唯一的人脸。")
            print("请确保只有师父一人面向摄像头，光线充足。")
            return False, None
        
        print("✅ 人脸检测通过")
    
    # 第二步：口令认证
    print("\n【第二步】口令认证")
    expected_hash, stored_password = load_or_setup_master_password(
        auth_config_path, auto_mode=auto_mode, auto_password=auto_password
    )
    
    if expected_hash is None:
        return False, None
    
    if auto_mode and stored_password:
        # 自动模式且已生成/给定口令，直接使用
        input_pass = stored_password
        print("🤖 自动模式：已输入口令")
    elif auto_mode and not stored_password:
        # 配置文件已存在，但自动模式未给定口令，需要读取环境变量或失败
        input_pass = auto_password
        if not input_pass:
            print("❌ 自动模式下配置文件已存在，但未提供口令。")
            print("   请提供 --password 参数，或删除配置文件重新设置。")
            return False, None
        print("🤖 自动模式：使用提供的口令验证")
    else:
        # 手动模式
        input_pass = input("请输入师父口令：").strip()
    
    input_hash = hashlib.sha256(input_pass.encode()).hexdigest()
    
    if input_hash != expected_hash:
        print("❌ 口令错误，认证失败。")
        return False, None
    
    print("✅ 口令认证通过")
    
    # 记录认证日志
    auth_log_path = auth_dir / "认证日志.jsonl"
    auth_record = {
        "timestamp": datetime.now().isoformat(),
        "action": "更新核心文件校验",
        "face_status": face_status,
        "snapshot": str(snapshot_path),
        "result": "通过",
        "auto_mode": auto_mode
    }
    with open(auth_log_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(auth_record, ensure_ascii=False) + '\n')
    
    print("\n✅ 师父身份认证通过，允许更新道统核心文件校验。")
    return True, input_pass


def main():
    parser = argparse.ArgumentParser(description="更新伴读书童AI核心文件校验哈希")
    parser.add_argument(
        "--auto", action="store_true",
        help="自动模式：书童自动拍照、自动生成口令（测试用）"
    )
    parser.add_argument(
        "--password", type=str, default=None,
        help="指定自动模式下的口令（可选，不提供则随机生成）"
    )
    parser.add_argument(
        "--no-camera", action="store_true",
        help="无摄像头模式：跳过人脸识别，仅用于测试"
    )
    args = parser.parse_args()
    
    project_root = Path(__file__).resolve().parents[2]
    
    # 先进行师父身份认证
    auth_ok, actual_password = authenticate_master(
        project_root,
        auto_mode=args.auto,
        auto_password=args.password,
        no_camera=args.no_camera
    )
    
    if not auth_ok:
        print("\n❌ 未能通过师父认证，书童拒绝更新核心文件校验。")
        print("如需更新，请确保：")
        print("  1. 师父本人面向摄像头")
        print("  2. 输入正确的师父口令")
        return 1
    
    agents_path = project_root / "00-灵魂区" / "AGENTS.md"
    workflow_path = project_root / "00-灵魂区" / "WORKFLOW.md"
    verify_path = project_root / "03-引擎区" / "书童程序" / "数据" / "核心文件校验.json"
    
    print("\n" + "=" * 60)
    print("伴读书童AI - 更新核心文件校验")
    print("=" * 60)
    print()
    
    if not agents_path.exists() or not workflow_path.exists():
        print("❌ 核心文件不存在，无法更新校验")
        return 1
    
    print("正在计算新的校验哈希...")
    hashes = {
        "AGENTS.md": compute_sha256(agents_path),
        "WORKFLOW.md": compute_sha256(workflow_path),
    }
    
    verify_data = {
        "version": "1.0",
        "algorithm": "sha256",
        "hashes": hashes,
        "note": "此文件用于验证道统核心文件完整性，篡改会导致书童拒绝启动",
        "last_updated_by": "师父认证更新",
        "last_updated_at": datetime.now().isoformat()
    }
    
    verify_path.parent.mkdir(exist_ok=True)
    with open(verify_path, 'w', encoding='utf-8') as f:
        json.dump(verify_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 校验文件已更新: {verify_path}")
    print()
    print("新的校验哈希：")
    for name, h in hashes.items():
        print(f"  {name}: {h}")
    print()
    print("⚠️ 提醒：请确认 AGENTS.md 和 WORKFLOW.md 的修改是师父授权的合法修改。")
    
    if args.auto and actual_password:
        print()
        print("=" * 60)
        print("【自动模式口令提示】")
        print(f"本次测试使用的临时口令是：{actual_password}")
        print("请师父牢记，或测试后立即重置为自己的私密口令。")
        print("=" * 60)
    
    return 0


if __name__ == "__main__":
    exit(main())
