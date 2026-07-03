#!/usr/bin/env python3
"""
伴读书童AI · 安装包打包脚本

支持三种模式：
1. 通用安装包：不包含任何家庭数据，用户自行配置 family_id
2. 家庭定制安装包：--family <family_id>，预置该家庭的本地数据
3. 批量家庭安装包：--all-families，为每个家庭各生成一个安装包

原则：
- 灵魂文件（AGENTS.md、核心提示词、训练素材等）只存云端，不进安装包
- 家庭数据（孩子档案、陪伴计划、学习计划、孩子作品）可随家庭安装包分发
"""
import os
import sys
import shutil
import zipfile
import json
import argparse
import urllib.request
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent
BUILD_DIR = PROJECT_ROOT / "产品交付" / "安装包"
ARCHIVE_ZONE = PROJECT_ROOT / "档案区" / "家庭群"

EXCLUDES = {
    # 版本控制和环境
    ".git", ".venv", "__pycache__", ".DS_Store",
    # 临时和归档
    "临时交付", "归档", "日志", "产品交付",
    # 灵魂文件：只存云端，不进安装包
    "AGENTS.md",
    "WORKFLOW.md",
    "书童程序/数据/提示词",
    "训练素材",
    "项目文档",
    "README.md",
    "目录说明.md",
    "setup.py",
    "config.json",  # 每安装包单独生成
    # 云端服务端文件（只部署在云端，不进客户端安装包）
    "cloud_server.py",
    "启动云端书童.command",
    "云端师父控制台.html",
    "云端数据区",
    # 师父专属入口与工具（家庭安装包不应包含）
    "师父PC端.html",
        "static/师父头像.jpg",
    "设置书童头像.command",
    "解锁核心文件.command",
    "锁定核心文件.command",
    # 内部开发/打包/部署文件
    "build_installer.py",
    "云端与本地边界说明.md",
    "deploy",
    "docker",
    "cloudflared_http.log",
    "cloudflared_http2.log",
    "cloudflared_http3.log",
    "cloudflared_http4.log",
    # 测试、演示、工具脚本（非家庭用户所需）
    "测试页面.html",
    "书童形象展示.html",
    "启动感官系统测试.command",
    "工具脚本",
    "对接规范",
    "每日陪伴记录",
    # 完整本地服务端（云端版安装包只保留 本地书童界面_云端版.py）
    "本地书童界面.py",
    "static/本地书童头像.jpg",
    # 知识库：云端版安装包不保留，知识调用走云端
    "知识库",
    # 开发/检查脚本，家庭用户不需要
    "脚本",
    # git 忽略文件
    ".gitignore",
    # 书童程序下的运行时数据与缓存，家庭安装包不应携带
    "书童程序/数据/感官日志",
    "书童程序/数据/语音缓存",
    "书童程序/数据/音频素材",
    "书童程序/数据/修行记录",
    "书童程序/数据/模型",
    "书童程序/数据/对话记录",
    "书童程序/数据/认证记录",
    "书童程序/数据/执行计划",
    "书童程序/数据/机器人日志",
    "书童程序/数据/修行日志",
    "书童程序/数据/标签库",
    "书童程序/数据/人脸标签",
    "书童程序/数据/人脸特征",
    "书童程序/数据/陪伴计划",
    "书童程序/数据/证书",
    # 开发用 OpenCode 工具
    ".opencode",
    # 家庭数据：通用安装包不包含；家庭安装包按需单独复制
    "档案区/家庭群",
    # 运行时生成的隐私数据，不进安装包
    "档案区/陪伴日志",
    "档案区/对话记录",
    "档案区/陪伴计划",
    "档案区/家庭群/家庭群总览.md",
    # 旧数据目录（已被家庭群替代）
    "档案区/孩子档案",
    "档案区/嘟嘟作品",
    "档案区/小橙子作品",
    # 内部工具/测试音频/运行时日志/云端专用依赖，不进家庭安装包
    "书童程序/工具",
    "static/测试音频.mp3",
    "书童运行日志.txt",
    "config.json.template",
    "requirements_cloud.txt",
}

REQUIRED_FILES = [
    "config.json.template",
    "README_安装说明.md",
    "install.py",
    "start.py",
    "requirements.txt",
]


def should_include(path: Path) -> bool:
    rel = path.relative_to(PROJECT_ROOT)
    rel_str = str(rel).replace(chr(92), "/")
    for ex in EXCLUDES:
        ex_str = ex.rstrip("/")
        # exact part match or path prefix match
        if ex_str in rel.parts:
            return False
        if rel_str == ex_str or rel_str.startswith(ex_str + "/"):
            return False
    return True


def copy_project(dest: Path):
    print(f"[步骤] 复制项目文件到 {dest}")
    dest.mkdir(parents=True, exist_ok=True)
    for item in PROJECT_ROOT.iterdir():
        if item.name in EXCLUDES:
            continue
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(item, target, ignore=lambda src, names: [n for n in names if not should_include(Path(src) / n)])
        else:
            shutil.copy2(item, target)

    # 确保必备文件存在
    for req in REQUIRED_FILES:
        src = PROJECT_ROOT / req
        dst = dest / req
        if src.exists() and not dst.exists():
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            print(f"[补充] {req}")


def _ignore_ds_store(src, names):
    """copytree 用 ignore 函数，过滤 .DS_Store 等系统文件"""
    return [n for n in names if n == ".DS_Store"]


def copy_family_data(dest: Path, family_id: str, family_dir: Path):
    """把指定家庭的本地数据复制到安装包中，仅包含该家庭，不包含其他家庭"""
    print(f"[步骤] 复制家庭数据：{family_id}")
    rel_parts = family_dir.relative_to(ARCHIVE_ZONE).parts
    dest_family_dir = dest / "档案区" / "家庭群" / Path(*rel_parts)
    dest_family_dir.mkdir(parents=True, exist_ok=True)

    # 复制该家庭目录下的所有内容
    for item in family_dir.iterdir():
        target = dest_family_dir / item.name
        if item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(item, target, ignore=_ignore_ds_store)
        else:
            if item.name == ".DS_Store":
                continue
            shutil.copy2(item, target)

    # 不复制家庭群总览，避免把所有家庭名称暴露进单个安装包
    print(f"[OK] 已复制 {family_dir} -> {dest_family_dir}")


def cloud_request(base_url: str, master_key: str, path: str, data: dict = None, method: str = "GET"):
    """调用云端师父接口"""
    url = f"{base_url.rstrip('/')}{path}"
    headers = {
        "Authorization": f"Bearer {master_key}",
        "Content-Type": "application/json",
    }
    body = json.dumps(data or {}, ensure_ascii=False).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"success": False, "error": f"云端请求失败: {e.code}"}
    except Exception as e:
        return {"success": False, "error": f"云端连接失败: {str(e)}"}


def get_or_create_family_key(cloud_api_base: str, master_key: str, family_id: str) -> str:
    """从云端获取或创建家庭订阅密钥"""
    if not master_key or not cloud_api_base:
        print(f"[提示] 未提供云端密钥，将使用占位符")
        return "请向师父或管理员申请订阅密钥"

    # 先查询该家庭是否已有完整密钥（reserve=true 表示打包预留，避免多个安装包复用同一密钥）
    resp = cloud_request(cloud_api_base, master_key, f"/admin/family/{family_id}/subscription_key?reserve=true")
    if resp.get("success"):
        key = resp.get("key", "")
        if key:
            print(f"[云端] 发现 {family_id} 已有订阅")
            return key

    # 没有则创建
    resp = cloud_request(
        cloud_api_base,
        master_key,
        f"/admin/family/{family_id}/subscribe",
        {"plan": "standard", "expires": "2027-12-31"},
        "POST",
    )
    if resp.get("success"):
        key = resp.get("key", "")
        print(f"[云端] 已为 {family_id} 创建订阅密钥")
        return key

    print(f"[警告] 云端创建订阅失败: {resp.get('error')}")
    return "请向师父或管理员申请订阅密钥"


def create_config(dest: Path, family_id: str, cloud_api_base: str = None, api_key: str = None):
    """生成预配置 config.json"""
    config = {
        "cloud_api_base": cloud_api_base or "https://bookkidai.com",
        "family_id": family_id,
        "api_key": api_key or "请向师父或管理员申请订阅密钥",
        "voice_enabled": True,
        "local_data_dir": "书童程序/数据",
        "unitree_enabled": False,
        "unitree_mode": "simulation",
        "unitree_model": "g1",
        "g1_http_enabled": False,
        "g1_http_control_url": "http://192.168.0.248:8888",
        "g1_http_control_token": "",
    }
    config_path = dest / "config.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[创建] {config_path}（family_id={family_id}）")


def create_family_readme(dest: Path, family_id: str, family_name: str):
    """为家庭安装包生成定制说明"""
    readme_path = dest / "README_安装说明.md"
    base_readme = PROJECT_ROOT / "README_安装说明.md"
    if base_readme.exists():
        content = base_readme.read_text(encoding="utf-8")
    else:
        content = ""
    
    family_note = f"""
---

## 本安装包说明

这是 **{family_name}（{family_id}）** 的专属安装包。

- `config.json` 已预配置 family_id 为 `{family_id}`
- 安装包中已包含本家庭的孩子档案、陪伴计划、学习计划等本地数据
- 安装后只需填入 `api_key`（订阅密钥）即可使用
- 请勿将本安装包转发给其他家庭使用
"""
    readme_path.write_text(content + family_note, encoding="utf-8")
    print(f"[创建] {readme_path}（家庭版）")


def create_package_password(package_dir: Path, password: str):
    """在安装包中写入启动密码（不依赖 zip 加密，避免中文文件名乱码）"""
    if not password:
        return
    pwd_path = package_dir / ".package_password"
    pwd_path.write_text(password, encoding="utf-8")
    print(f"[创建] 安装包启动密码已写入")


def create_manifest(package_dir: Path, timestamp: str, family_id: str = None, family_name: str = None, package_type: str = "full"):
    manifest = {
        "product": "伴读书童AI · 家庭版",
        "version": timestamp,
        "type": "cloud-client-installer",
        "package_type": package_type,
        "note": "本安装包不包含灵魂文件，需连接云端服务",
        "generated_at": datetime.now().isoformat(),
        "includes_soul_files": False,
    }
    if family_id:
        manifest["family_id"] = family_id
        manifest["family_name"] = family_name or family_id
        manifest["type"] = "family-client-installer"
        manifest["note"] = f"本安装包为 {family_id} 专属，已预置家庭本地数据，需连接云端服务"
    
    manifest_path = package_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[创建] {manifest_path}（类型: {package_type}）")


def cleanup_files_by_package_type(package_dir: Path, package_type: str):
    """根据安装包类型清理不该出现的文件"""
    # 所有家庭包都不应包含师父专属文件和内部文件
    always_remove = [
        "师父PC端.html",
    "static/师父头像.jpg",
        "设置书童头像.command",
        "解锁核心文件.command",
        "锁定核心文件.command",
        "测试页面.html",
        "书童形象展示.html",
        "启动感官系统测试.command",
        "build_installer.py",
        "云端与本地边界说明.md",
    ]
    type_specific_remove = {
        "child": ["墨童.html"],
        "mobile": ["墨童.html", "书童家庭端.html"],
    }
    to_remove = always_remove + type_specific_remove.get(package_type, [])
    for name in to_remove:
        target = package_dir / name
        if target.exists():
            try:
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
                print(f"[清理] {name}")
            except Exception as e:
                print(f"[警告] 清理 {name} 失败: {e}")


def apply_package_type(package_dir: Path, package_type: str, family_id: str):
    """根据安装包类型裁剪入口与默认启动行为"""
    entry_path = package_dir / "书童家庭访问入口.html"
    if entry_path.exists():
        content = entry_path.read_text(encoding="utf-8")
        # 注入包类型，前端据此隐藏入口
        inject = f"<script>window.PACKAGE_TYPE = '{package_type}'; window.LOCKED_FAMILY_ID = '{family_id}';</script>"
        content = content.replace("</head>", f"{inject}\n</head>")
        entry_path.write_text(content, encoding="utf-8")
        print(f"[入口] 已标记安装包类型: {package_type}")

    # 根据类型写入启动偏好
    start_pref = package_dir / "package_type.txt"
    start_pref.write_text(package_type, encoding="utf-8")


def create_zip(source: Path, zip_path: Path, password: str = None):
    """打包 source 目录到 zip_path；如果提供 password，使用系统 zip 命令做传统加密"""
    print(f"[步骤] 打包 {zip_path}")
    if not password:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in source.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, file_path.relative_to(source))
        return

    # 使用系统 zip 命令在 source 目录内直接生成加密包
    import subprocess
    cmd = ["zip", "-P", password, "-r", str(zip_path), "."]
    try:
        result = subprocess.run(cmd, cwd=source, check=True, capture_output=True, text=True)
        print(f"[加密] zip 已加密，解压密码: {password}")
    except Exception as e:
        print(f"[警告] zip 加密失败: {e}，回退为未加密")
        # 回退为普通 zip
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in source.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, file_path.relative_to(source))


def encrypt_zip(zip_path: Path, password: str) -> Path:
    """保留此函数以兼容旧调用，但加密已在 create_zip 中完成"""
    return zip_path


def discover_families():
    """扫描家庭群目录，返回 {family_id: family_dir} 映射"""
    families = {}
    if not ARCHIVE_ZONE.exists():
        print(f"[警告] 家庭群目录不存在: {ARCHIVE_ZONE}")
        return families
    
    for family_json in ARCHIVE_ZONE.rglob("family.json"):
        try:
            with open(family_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            family_id = data.get("family_id")
            if not family_id:
                continue
            families[family_id] = {
                "dir": family_json.parent,
                "name": data.get("name", family_id),
                "data": data,
            }
        except Exception as e:
            print(f"[警告] 读取家庭配置失败 {family_json}: {e}")
    
    return families


def build_generic_package(timestamp: str, cloud_api_base: str = None, master_key: str = None, zip_password: str = None) -> Path:
    """构建通用安装包"""
    package_dir = BUILD_DIR / f"书童家庭版_{timestamp}"
    zip_path = BUILD_DIR / f"书童家庭版_{timestamp}.zip"

    if package_dir.exists():
        shutil.rmtree(package_dir)

    copy_project(package_dir)
    create_config(package_dir, "请填写您的家庭ID", cloud_api_base, "请向师父或管理员申请订阅密钥")
    create_manifest(package_dir, timestamp)
    create_package_password(package_dir, zip_password)
    create_zip(package_dir, zip_path)

    return zip_path


def _cleanup_other_families(package_dir: Path, keep_family_id: str):
    """清理安装包中其他家庭的本地 family.json，避免隐私泄露"""
    local_family_dir = package_dir / "书童程序" / "数据" / "家庭"
    if not local_family_dir.exists():
        return
    for item in local_family_dir.iterdir():
        if not item.is_dir():
            continue
        if item.name == keep_family_id:
            continue
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            print(f"[清理] 移除其他家庭本地数据: {item.name}")
        except Exception as e:
            print(f"[警告] 清理 {item.name} 失败: {e}")


def build_family_package(family_id: str, family_info: dict, timestamp: str, cloud_api_base: str = None, master_key: str = None, package_type: str = "full", type_index: int = 0, zip_password: str = None) -> Path:
    """构建指定家庭的安装包，支持类型：full / parent / child / mobile"""
    type_suffix = f"_{package_type}" if package_type != "full" else ""
    index_suffix = f"_{type_index}" if type_index > 0 else ""
    package_dir = BUILD_DIR / f"书童家庭版_{family_id}{type_suffix}{index_suffix}_{timestamp}"
    zip_path = BUILD_DIR / f"书童家庭版_{family_id}{type_suffix}{index_suffix}_{timestamp}.zip"

    if package_dir.exists():
        shutil.rmtree(package_dir)

    copy_project(package_dir)
    copy_family_data(package_dir, family_id, family_info["dir"])
    _cleanup_other_families(package_dir, family_id)

    apply_package_type(package_dir, package_type, family_id)
    cleanup_files_by_package_type(package_dir, package_type)

    api_key = get_or_create_family_key(cloud_api_base, master_key, family_id) if (cloud_api_base and master_key) else None
    create_config(package_dir, family_id, cloud_api_base, api_key)
    create_family_readme(package_dir, family_id, family_info["name"])
    create_manifest(package_dir, timestamp, family_id=family_id, family_name=family_info["name"], package_type=package_type)
    create_package_password(package_dir, zip_password)
    create_zip(package_dir, zip_path)

    return zip_path


def main():
    parser = argparse.ArgumentParser(description="伴读书童AI 安装包打包工具")
    parser.add_argument("--family", type=str, help="指定 family_id，生成该家庭的专属安装包")
    parser.add_argument("--all-families", action="store_true", help="为所有家庭各生成一个专属安装包")
    parser.add_argument("--generic", action="store_true", help="同时生成通用安装包（与 --family/--all-families 配合）")
    parser.add_argument("--package-type", type=str, default="full",
                        choices=["full", "parent", "child", "mobile"],
                        help="安装包类型：full 全入口 / parent 家长端 / child 孩子端 / mobile 手机端")
    parser.add_argument("--package-types", type=str,
                        help="一次生成多个类型，用逗号分隔，例如 parent,parent,mobile")
    parser.add_argument("--zip-password", type=str, default="",
                        help="zip 安装包解压密码（传统 zip 加密，用于防止随意转发）")
    parser.add_argument("--cloud-api-base", type=str, default=os.environ.get("BOOKBOY_CLOUD_API_BASE", "http://114.55.9.27"), help="云端 API 地址")
    parser.add_argument("--master-key", type=str, default=os.environ.get("BOOKBOY_MASTER_KEY", ""), help="师父管理密钥，用于为家庭创建订阅")
    args = parser.parse_args()

    print("=" * 60)
    print("伴读书童AI · 安装包打包")
    print("原则：灵魂文件存云端，家庭数据可预置")
    print("=" * 60)

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    built_packages = []
    cloud_api_base = args.cloud_api_base
    master_key = args.master_key

    # 模式 1：通用安装包
    if not args.family and not args.all_families or args.generic:
        print("\n[模式] 生成通用安装包")
        zip_path = build_generic_package(timestamp, cloud_api_base, master_key, zip_password=args.zip_password)
        built_packages.append(("通用版", zip_path))

    # 模式 2 / 3：家庭安装包
    if args.family or args.all_families:
        families = discover_families()
        if not families:
            print("[错误] 未找到任何家庭配置")
            sys.exit(1)

        target_ids = list(families.keys()) if args.all_families else [args.family]

        # 支持一次生成多个包类型
        type_list = []
        if args.package_types:
            type_list = [t.strip() for t in args.package_types.split(",") if t.strip()]
        else:
            type_list = [args.package_type]

        for fid in target_ids:
            if fid not in families:
                print(f"[错误] 未找到家庭: {fid}")
                continue
            info = families[fid]

            type_counter = {}
            for pt in type_list:
                idx = type_counter.get(pt, 0)
                type_counter[pt] = idx + 1
                print(f"\n[模式] 生成家庭安装包：{fid} ({info['name']}) 类型: {pt} 序号: {idx}")
                zip_path = build_family_package(fid, info, timestamp, cloud_api_base, master_key, package_type=pt, type_index=idx, zip_password=args.zip_password)
                label = f"{fid} ({info['name']}) [{pt}]"
                if idx > 0:
                    label += f" #{idx}"
                built_packages.append((label, zip_path))

    print("\n" + "=" * 60)
    print("打包完成！")
    for name, path in built_packages:
        print(f"  - {name}: {path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
