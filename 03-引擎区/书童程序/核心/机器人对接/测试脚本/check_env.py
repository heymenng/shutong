#!/usr/bin/env python3
"""G1 远程服务环境检测与自动配置。

跑一遍即可：检测 Python、requests、ssh、免密登录，缺失时提示并尝试自动修复。

用法（在仓库根目录执行）:
    python3 deploy/check_env.py            # 检测 + 交互式修复
    python3 deploy/check_env.py --check    # 只检测，不修改任何东西
    python3 deploy/check_env.py --yes      # 检测 + 全部自动修复，不再逐项确认
"""

import argparse
import os
import shutil
import subprocess
import sys

# ========== 配置（与 start_robot_server.py 保持一致） ==========
PC2_HOST = "192.168.0.248"
PC2_USER = "unitree"
MIN_PY = (3, 8)
# ===============================================================

IS_WIN = os.name == "nt"

# 防卡死选项。
#  - GSSAPIAuthentication=no：关掉 Windows OpenSSH 默认开的 GSSAPI（Kerberos/DNS 查询卡十几秒）
#  - StrictHostKeyChecking=accept-new：自动接受新主机密钥，不弹确认
# ConnectTimeout 只管 TCP 连接，管不到后续握手，必须靠上面两条避免握手期卡死。
SSH_BASE_OPTS = [
    "-o", "ConnectTimeout=5",
    "-o", "GSSAPIAuthentication=no",
    "-o", "StrictHostKeyChecking=accept-new",
]
# 测免密用：彻底非交互，没配就立即失败。
# 额外加 -n + stdin=DEVNULL：Windows OpenSSH 在 stdout 被 Python 管道捕获(非 TTY)时,
# 认证阶段会同步卡约 9 秒(连本机 ssh-agent 套接字失败所致)；-n 可绕开。实测 9.5s → 0.4s。
SSH_TEST_OPTS = ["-n"] + SSH_BASE_OPTS + [
    "-o", "BatchMode=yes",
    "-o", "PasswordAuthentication=no",
]


# ---------- 基础工具 ----------

def run(cmd, **kw):
    """跑命令，返回 CompletedProcess。

    默认 stdin=DEVNULL，配合 ssh 的 -n 防 Windows OpenSSH 管道捕获卡死；
    调用方显式传 input=... 时会覆盖此默认值（如推公钥需要 stdin 传数据）。
    """
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    kw.setdefault("stdin", subprocess.DEVNULL)
    return subprocess.run(cmd, **kw)


def confirm(prompt: str, auto_yes: bool) -> bool:
    if auto_yes:
        return True
    try:
        return input(prompt).strip().lower() in ("y", "yes", "")
    except (EOFError, KeyboardInterrupt):
        return False


def ok(msg):   print(f"  \033[92m[OK]   {msg}\033[0m")
def fail(msg): print(f"  \033[91m[FAIL] {msg}\033[0m")
def warn(msg): print(f"  \033[93m[WARN] {msg}\033[0m")


# ---------- 检测项 ----------

def check_python() -> bool:
    """Python 版本 ≥ 3.8"""
    print("[1/4] Python 版本...")
    for py in ("python3", "python"):
        if shutil.which(py):
            r = run([py, "--version"])
            if r.returncode == 0:
                v = r.stdout.strip() or r.stderr.strip()
                print(f"  {v} ({py})")
                try:
                    parts = v.lower().replace("python", "").strip().split(".")
                    major, minor = int(parts[0]), int(parts[1])
                    if (major, minor) >= MIN_PY:
                        ok(f"满足 ≥ {MIN_PY[0]}.{MIN_PY[1]}")
                        return True
                    else:
                        fail(f"版本过低，需 ≥ {MIN_PY[0]}.{MIN_PY[1]}")
                        return False
                except (ValueError, IndexError):
                    warn(f"无法解析版本号：{v}，假定可用")
                    return True
    fail("未找到 python3/python")
    print("    Mac:  brew install python")
    print("    Win:  https://python.org 下载安装，勾选 Add to PATH")
    print("    Linux: sudo apt install python3")
    return False


def check_requests(fix: bool, auto: bool) -> bool:
    """requests 包"""
    print("[2/4] requests 包...")
    py = "python3" if shutil.which("python3") else "python"
    r = run([py, "-c", "import requests; print(requests.__version__)"])
    if r.returncode == 0:
        ok(f"requests {r.stdout.strip()}")
        return True

    fail("requests 未安装")
    if not fix:
        return False

    if not confirm("  是否自动安装 requests? [Y/n] ", auto):
        return False

    pip = "pip3" if shutil.which("pip3") else "pip"
    # 先试普通安装，失败再试 --break-system-packages（新版 Homebrew Python）
    r = run([pip, "install", "requests"])
    if r.returncode != 0:
        warn("普通安装失败，尝试 --break-system-packages ...")
        r = run([pip, "install", "--user", "--break-system-packages", "requests"])
    if r.returncode == 0:
        ok("requests 安装完成")
        return True
    fail(f"安装失败: {r.stderr.strip()}")
    return False


def check_ssh_client() -> bool:
    """ssh 客户端"""
    print("[3/4] SSH 客户端...")
    if shutil.which("ssh"):
        r = run(["ssh", "-V"])
        ver = (r.stderr or r.stdout).strip()
        ok(ver or "ssh 已安装")
        return True
    fail("未找到 ssh 客户端")
    print("    Win10 1803+ 自带 OpenSSH；旧版装 Git Bash 或 PuTTY")
    print("    Linux: sudo apt install openssh-client")
    return False


def ssh_key_path() -> str:
    home = os.path.expanduser("~")
    return os.path.join(home, ".ssh", "id_rsa")


def check_ssh_login(fix: bool, auto: bool) -> bool:
    """SSH 免密登录到 PC2"""
    print(f"[4/4] SSH 免密登录 ({PC2_USER}@{PC2_HOST})...")
    try:
        r = run(
            ["ssh", *SSH_TEST_OPTS, f"{PC2_USER}@{PC2_HOST}", "echo ok"],
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        fail("连接超时（SSH 端口不通或 PC2 未开机）")
        return False
    if r.returncode == 0 and "ok" in r.stdout:
        ok("免密登录可用")
        return True

    fail("免密登录不可用")
    if not fix:
        print("    请按 REMOTE_SERVICE_GUIDE.md 配置免密登录")
        return False

    if not confirm("  是否自动配置免密登录? [Y/n] ", auto):
        return False

    return setup_ssh_key()


def setup_ssh_key() -> bool:
    """生成密钥（如无）并把公钥推到 PC2。"""
    key = ssh_key_path()
    if not os.path.exists(key):
        print(f"  生成密钥 {key} ...")
        r = run(["ssh-keygen", "-t", "rsa", "-b", "4096",
                 "-f", key, "-N", ""])
        if r.returncode != 0:
            fail(f"ssh-keygen 失败: {r.stderr.strip()}")
            return False
        ok("密钥已生成")
    else:
        warn(f"已存在密钥 {key}，跳过生成")

    pub = key + ".pub"
    if not os.path.exists(pub):
        fail(f"找不到公钥 {pub}")
        return False

    # 优先用 ssh-copy-id（Mac/Linux），Windows 上回退到手动追加
    if shutil.which("ssh-copy-id"):
        print(f"  推送公钥到 {PC2_USER}@{PC2_HOST}（可能需要输入 PC2 密码）...")
        # 不能 capture，因为要交互输密码；带防卡死选项但不带 BatchMode（要输密码）
        r = subprocess.run(
            ["ssh-copy-id", *SSH_BASE_OPTS, f"{PC2_USER}@{PC2_HOST}"],
        )
        if r.returncode == 0:
            ok("公钥已推送")
        else:
            warn("ssh-copy-id 未成功，尝试手动追加")
            return _manual_append_pub(pub)
        return verify_login()

    return _manual_append_pub(pub)


def _manual_append_pub(pub: str) -> bool:
    """用 cat | ssh 把公钥追加到远端 authorized_keys（Windows 兼容）。"""
    print(f"  手动追加公钥到 {PC2_USER}@{PC2_HOST}（需要输入 PC2 密码）...")
    with open(pub, "r", encoding="utf-8") as f:
        pubdata = f.read().strip()
    remote_cmd = (
        "mkdir -p ~/.ssh && chmod 700 ~/.ssh && "
        "cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
    )
    # 公钥通过 stdin 传入，避免命令行转义问题
    # 带 GSSAPI off / accept-new 防卡死，但不带 BatchMode（这一步要输密码）
    r = subprocess.run(
        ["ssh", *SSH_BASE_OPTS, f"{PC2_USER}@{PC2_HOST}", remote_cmd],
        input=pubdata + "\n",
        text=True,
    )
    if r.returncode == 0:
        ok("公钥已追加")
        return verify_login()
    fail(f"追加失败（返回码 {r.returncode}）")
    return False


def verify_login() -> bool:
    """配置后再测一次免密。"""
    try:
        r = run(
            ["ssh", *SSH_TEST_OPTS, f"{PC2_USER}@{PC2_HOST}", "echo ok"],
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        fail("验证超时（SSH 端口不通或 PC2 未开机）")
        return False
    if r.returncode == 0 and "ok" in r.stdout:
        ok("免密登录验证通过")
        return True
    fail("配置后仍无法免密登录，请检查 PC2 用户名/地址/密码")
    return False


# ---------- 主流程 ----------

def main():
    parser = argparse.ArgumentParser(description="G1 远程服务环境检测与自动配置")
    parser.add_argument("--check", action="store_true",
                        help="只检测，不做任何修改")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="自动修复，不逐项确认")
    args = parser.parse_args()

    fix = not args.check

    # Windows 默认 GBK 控制台可能编码不了某些字符，切到 UTF-8 容错
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    print("=" * 50)
    print("  G1 远程服务 — 环境检测")
    print("=" * 50)
    print()

    results = []
    results.append(check_python())
    results.append(check_requests(fix=fix, auto=args.yes))
    results.append(check_ssh_client())
    if all(results[:3]):
        results.append(check_ssh_login(fix=fix, auto=args.yes))
    else:
        print("[4/4] SSH 免密登录... 跳过（前置项未就绪）")
        results.append(False)

    print()
    print("=" * 50)
    if all(results):
        ok("环境就绪，可以运行: python3 deploy/start_robot_server.py")
    else:
        fail("环境未完全就绪，请按提示处理")
    print("=" * 50)

    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已取消")
        sys.exit(130)
