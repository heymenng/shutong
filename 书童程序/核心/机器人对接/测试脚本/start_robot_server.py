#!/usr/bin/env python3
"""远程启动 G1 PC2 上的 robot_control_server 服务。

用法（在仓库根目录执行）:
    python3 deploy/start_robot_server.py                  # 仅启动
    python3 deploy/start_robot_server.py --sync           # 先同步本地代码再启动
    python3 deploy/start_robot_server.py --port 9000      # 指定端口
    python3 deploy/start_robot_server.py --token g1secret # 带 token

前提:
    - 笔记本能 SSH 到 PC2
    - 已配置免密登录或脚本会提示输入密码
"""

import argparse
import os
import subprocess
import sys
import time
from typing import Optional

# 让同目录的 check_env 可被导入（复用免密登录配置逻辑，避免重复实现）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_env import setup_ssh_key  # noqa: E402

# ========== 配置 ==========
PC2_HOST = "192.168.0.248"
PC2_USER = "unitree"
PC2_PROJECT_DIR = "/home/unitree/Desktop/unitree_sdk2_python"
SERVER_SCRIPT = "example/g1/high_level/robot_control_server.py"
NETWORK_IFACE = "eth0"
DEFAULT_PORT = 8888

# 本脚本现位于 deploy/，需据此定位仓库根目录与同目录的 fetch_logs.py
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))      # deploy/
REPO_ROOT = os.path.dirname(SCRIPT_DIR)                       # 仓库根
LOCAL_PROJECT_DIR = REPO_ROOT
# ==========================


# 防卡死选项：
#  - BatchMode 禁交互、PasswordAuthentication=no：没配免密就立即失败，不卡密码提示
#  - GSSAPIAuthentication=no：关掉 Windows OpenSSH 默认开的 GSSAPI（Kerberos/DNS 查询卡十几秒）
#  - StrictHostKeyChecking=accept-new：自动接受新主机密钥，不弹确认
#  - -n：stdin 重定向到 NUL。Windows OpenSSH 在 stdout 被 Python 管道捕获(非 TTY)时,
#    认证阶段会同步卡约 9 秒(连本机 ssh-agent 套接字失败所致)；-n + stdin=DEVNULL 可绕开。
#    实测：不加会 9.5s，加了 0.4s。ConnectTimeout 只管 TCP，管不到这个握手期卡顿。
SSH_OPTS = [
    "-n",
    "-o", "ConnectTimeout=5",
    "-o", "BatchMode=yes",
    "-o", "PasswordAuthentication=no",
    "-o", "GSSAPIAuthentication=no",
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", "ServerAliveInterval=10",
]

SSH_BASE = ["ssh", *SSH_OPTS, f"{PC2_USER}@{PC2_HOST}"]


def run_ssh(cmd: str, timeout: int = 30, capture: bool = True) -> subprocess.CompletedProcess:
    """在 PC2 上执行命令。stdin=DEVNULL 配合 -n 防 Windows OpenSSH 管道捕获卡死。"""
    ssh_cmd = SSH_BASE + [cmd]
    return subprocess.run(
        ssh_cmd,
        capture_output=capture,
        text=True,
        timeout=timeout,
        stdin=subprocess.DEVNULL,
    )


def check_connectivity() -> bool:
    """检查 PC2 是否可达（SSH 端口能否连上）。

    用 BatchMode 测：不弹密码、不卡，能区分「只是没配免密」和「真连不上」。
    未配免密时返回码非 0 但 stderr 含 "permission denied"——说明 SSH 端口是通的，
    视为可达，交给第 2 步去配免密。
    """
    print(f"[1/6] 检查 PC2 连通性 ({PC2_USER}@{PC2_HOST})...")
    try:
        result = subprocess.run(
            ["ssh", *SSH_OPTS, f"{PC2_USER}@{PC2_HOST}", "echo ok"],
            capture_output=True, text=True, timeout=30,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        print("  ❌ 连接超时，请确认 PC2 已开机且在同一个 WiFi 下")
        return False
    except Exception as e:
        print(f"  ❌ 连接异常: {e}")
        return False

    if result.returncode == 0 and "ok" in result.stdout:
        print("  ✅ PC2 可达（免密已配置）")
        return True
    err = (result.stderr or "").lower()
    if "permission denied" in err or "publickey" in err:
        # SSH 端口通了，只是还没配免密——可达，第 2 步会去配
        print("  ✅ PC2 可达（免密未配置，下一步将配置）")
        return True
    msg = result.stderr.strip() or f"返回码 {result.returncode}"
    print(f"  ❌ SSH 连接失败: {msg}")
    print("    请确认 PC2 已开机、在同一个 WiFi 下、且 SSH 服务在运行")
    return False


def ensure_passwordless() -> bool:
    """确保已配置免密登录；未配置则引导配置（需输一次 PC2 密码）。

    配好后后续所有 ssh/scp 都不再要密码，也就不会触发 run_ssh 的 15s 超时。
    """
    print(f"[2/6] 检查免密登录 ({PC2_USER}@{PC2_HOST})...")
    # SSH_OPTS 含 BatchMode：没配免密就立即失败，不会卡住
    r = subprocess.run(
        ["ssh", *SSH_OPTS, f"{PC2_USER}@{PC2_HOST}", "echo ok"],
        capture_output=True, text=True, timeout=30,
        stdin=subprocess.DEVNULL,
    )
    if r.returncode == 0 and "ok" in r.stdout:
        print("  ✅ 免密登录可用")
        return True

    print("  ⚠️  免密未配置，开始配置（需要输入一次 PC2 密码）...")
    try:
        if setup_ssh_key():  # 复用 check_env：生成密钥 → 推公钥 → 验证
            print("  ✅ 免密登录已配置")
            return True
    except Exception as e:
        print(f"  ❌ 配置异常: {e}")
    print("  ❌ 免密登录配置失败，可手动运行: python3 deploy/check_env.py --yes")
    return False


def sync_code() -> bool:
    """同步 robot_control_server.py 到 PC2"""
    local = f"{LOCAL_PROJECT_DIR}/{SERVER_SCRIPT}"
    remote = f"{PC2_USER}@{PC2_HOST}:{PC2_PROJECT_DIR}/{SERVER_SCRIPT}"
    print(f"[3/6] 同步代码到 PC2...")
    try:
        result = subprocess.run(
            ["scp", *SSH_OPTS, local, remote],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode == 0:
            print("  ✅ 同步完成")
            return True
        else:
            print(f"  ⚠️  scp 警告: {result.stderr.strip()}")
            return True  # 不阻断
    except Exception as e:
        print(f"  ⚠️  同步异常: {e}，继续启动...")
        return True


def stop_existing():
    """停掉 PC2 上已有的 robot_control_server 进程"""
    print("[4/6] 停掉旧进程...")
    kill_cmd = "tmux kill-session -t robot 2>/dev/null; kill $(ps aux | grep robot_control_server | grep -v grep | awk '{print $2}') 2>/dev/null; echo done"
    result = run_ssh(kill_cmd)
    time.sleep(1)

    # 确认已停
    check = run_ssh("ps aux | grep robot_control_server | grep -v grep || echo 'all_clear'")
    if "all_clear" in check.stdout:
        print("  ✅ 旧进程已清理")
    else:
        print(f"  ⚠️  可能还有残留: {check.stdout.strip()}")


def start_service(port: int, token: Optional[str], log_level: str = "INFO"):
    """在 PC2 上启动服务"""
    print(f"[5/6] 启动服务 (端口 {port}, 日志级别 {log_level})...")
    token_arg = f" --token {token}" if token else ""
    log_arg = f" --log-level {log_level}"
    # 使用 tmux 在后台启动，彻底避免 SSH 阻塞
    start_cmd = (
        f"tmux kill-session -t robot 2>/dev/null; "
        f"tmux new-session -d -s robot "
        f"\"cd {PC2_PROJECT_DIR} && "
        f"PYTHONUNBUFFERED=1 python3 {SERVER_SCRIPT} {NETWORK_IFACE} "
        f"--host 0.0.0.0 --port {port}{token_arg}{log_arg} "
        f"> ~/robot_server.log 2>&1\""
    )
    result = run_ssh(start_cmd, timeout=15)
    if result.returncode != 0:
        print(f"  ❌ 启动失败: {result.stderr.strip()}")
        return False

    time.sleep(3)

    # 确认启动
    log = run_ssh("tail -5 ~/robot_server.log 2>/dev/null || echo EMPTY")
    if "listening" in log.stdout.lower():
        print("  ✅ 服务启动成功")
        return True
    else:
        print(f"  ⚠️  日志输出:\n{log.stdout.strip()}")
        # 再等一会
        time.sleep(5)
        log2 = run_ssh("tail -5 ~/robot_server.log 2>/dev/null || echo EMPTY")
        if "listening" in log2.stdout.lower():
            print("  ✅ 服务启动成功（延迟）")
            return True
        print(f"  ❌ 可能启动失败:\n{log2.stdout.strip()}")
        return False


def verify_service(port: int) -> bool:
    """笔记本本地 HTTP 验证"""
    import urllib.request
    import json

    url = f"http://{PC2_HOST}:{port}/health"
    print(f"[6/6] 验证服务 ({url})...")
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            if data.get("ok") and data.get("service") == "g1_robot_control_server":
                print(f"  ✅ 服务正常响应: {data}")
                return True
            else:
                print(f"  ⚠️  响应异常: {data}")
                return False
    except Exception as e:
        print(f"  ❌ HTTP 验证失败: {e}")
        return False


def _pidfile_path(log_file: str) -> str:
    return os.path.abspath(log_file) + ".pid"


def _kill_old_streamer(log_file: str):
    """杀掉上次启动的日志流进程，避免多个流写同一个文件。"""
    pidfile = _pidfile_path(log_file)
    if not os.path.exists(pidfile):
        return
    try:
        with open(pidfile, "r") as f:
            pid = int(f.read().strip())
    except (ValueError, OSError):
        pid = None
    if pid:
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                               capture_output=True)
            else:
                os.kill(pid, 9)
        except (ProcessLookupError, OSError):
            pass  # 进程已不在
    try:
        os.remove(pidfile)
    except OSError:
        pass


def start_log_streamer(port: int, token: Optional[str], log_file: str) -> bool:
    """服务启动成功后在笔记本本地后台拉起日志流，实时写入本地文件。"""
    fetch_script = os.path.join(SCRIPT_DIR, "fetch_logs.py")
    if not os.path.exists(fetch_script):
        print("  [日志流] 未找到 fetch_logs.py，跳过")
        return False

    _kill_old_streamer(log_file)

    cmd = [sys.executable, fetch_script, "--stream",
           "--host", PC2_HOST, "--port", str(port), "--out", log_file]
    if token:
        cmd += ["--token", token]

    # 让子进程独立存活，不被本脚本退出带走
    kwargs = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen(cmd, **kwargs)
    except Exception as e:
        print(f"  [日志流] 启动失败: {e}")
        return False

    # 记下 pid，下次启动时好清理
    try:
        with open(_pidfile_path(log_file), "w") as f:
            f.write(str(proc.pid))
    except OSError:
        pass

    print(f"  [日志流] 已后台启动 (pid {proc.pid})，实时写入 {log_file}")
    print(f"          实时查看: tail -f {log_file}")
    return True


def main():
    parser = argparse.ArgumentParser(description="远程启动 G1 robot_control_server")
    parser.add_argument("--sync", action="store_true", help="先同步本地代码到 PC2")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"服务端口 (默认 {DEFAULT_PORT})")
    parser.add_argument("--token", default=None, help="可选的访问令牌")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="PC2 服务端日志级别 (默认 INFO)")
    parser.add_argument("--log-file", default="robot_server.log",
                        help="笔记本本地日志保存路径 (默认 robot_server.log)")
    parser.add_argument("--no-log-stream", action="store_true",
                        help="不自动后台启动日志流")
    args = parser.parse_args()

    print("=" * 50)
    print("  G1 Robot Control Server — 远程启动")
    print("=" * 50)
    print()

    # 1. 连通性
    if not check_connectivity():
        sys.exit(1)

    # 2. 免密登录（没配则引导配置，配好才继续——避免后面 ssh 反复要密码导致超时）
    if not ensure_passwordless():
        sys.exit(1)

    # 3. 同步（可选）
    if args.sync:
        if not sync_code():
            print("  继续启动（跳过同步错误）...")
    else:
        print("[3/6] 跳过代码同步 (加 --sync 可同步)")

    # 3. 停旧
    stop_existing()

    # 4. 启动
    if not start_service(args.port, args.token, args.log_level):
        print("\n💡 提示: 如果端口被占用，试试 --port 9000")
        sys.exit(1)

    # 5. 验证
    if not verify_service(args.port):
        print("  服务未验证通过，跳过日志流启动")
        sys.exit(1)

    # 6. 后台启动日志流（笔记本本地实时落盘）
    if not args.no_log_stream:
        start_log_streamer(args.port, args.token, args.log_file)
    else:
        print("  [日志流] 已跳过 (--no-log-stream)")

    print()
    print("=" * 50)
    print(f"  服务地址: http://{PC2_HOST}:{args.port}")
    print(f"  健康检查: curl http://{PC2_HOST}:{args.port}/health")
    if not args.no_log_stream:
        print(f"  本地日志: tail -f {args.log_file}")
    print(f"  远程日志: ssh {PC2_USER}@{PC2_HOST} 'tail -f ~/robot_server.log'")
    print("=" * 50)


if __name__ == "__main__":
    main()
