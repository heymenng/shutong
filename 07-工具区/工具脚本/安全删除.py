#!/usr/bin/env python3
"""伴读书童AI · 安全删除工具

强制机制：所有删除操作必须经过理由检查、Git 状态检查、区域风险检查，
并写入审计日志。杜绝师兄/师弟误删工作文件、档案文件的事故重演。

用法：
    .venv/bin/python 07-工具区/工具脚本/安全删除.py <路径> [路径...] --reason "删除理由"
    .venv/bin/python 07-工具区/工具脚本/安全删除.py <路径> --dry-run --reason "理由"
    .venv/bin/python 07-工具区/工具脚本/安全删除.py <路径> --force --reason "理由"
"""

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "03-引擎区"))

from 书童程序.工具.项目根目录 import get_project_root  # noqa: E402


ROOT = get_project_root()
AUDIT_LOG = ROOT / "04-工作区" / "删除审计日志.md"

# 区域风险等级
ZONE_RISK = {
    "00-灵魂区": "critical",
    "01-配置区": "critical",
    "02-知识库区": "high",
    "03-引擎区": "high",
    "04-工作区": "high",
    "05-交付区": "medium",
    "06-对接区": "high",
    "07-工具区": "high",
    "08-归档区": "high",
}

# 允许在无显式确认下删除的模式（必须是明显生成/缓存/日志类）
AUTO_ALLOW_PATTERNS = [
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".DS_Store",
    "*.log",
    "*.tmp",
    "*.bak",
]

# 05-交付区/临时交付/ 内可自动清理的文件模式
TEMP_ALLOW_PATTERNS = [
    "*.mp3",
    "*.html",
    "*.md",
    "*.txt",
    "*.docx",
    "*.zip",
]


def _run(cmd, cwd=None):
    try:
        return subprocess.run(
            cmd,
            cwd=cwd or ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as e:
        return subprocess.CompletedProcess(args=cmd, returncode=-1, stdout="", stderr=str(e))


def git_status(path: Path) -> dict:
    """返回路径的 git 状态：tracked/ignored/untracked/unknown"""
    rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
    tracked = _run(["git", "ls-files", "--error-unmatch", str(rel)])
    ignored = _run(["git", "check-ignore", str(rel)])
    if tracked.returncode == 0:
        return {"status": "tracked", "restore_cmd": f"git restore --source=HEAD -- '{rel}'"}
    if ignored.returncode == 0:
        return {"status": "ignored", "restore_cmd": "无法通过 git restore 恢复（被忽略）"}
    # 不在 git 中（可能未跟踪或 .gitignore 外）
    return {"status": "untracked", "restore_cmd": "无法通过 git restore 恢复（未跟踪）"}


def classify_zone(path: Path) -> tuple:
    """返回 (zone, risk)"""
    rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else None
    if rel is None:
        return ("外部", "critical")
    parts = rel.parts
    if not parts:
        return ("根目录", "critical")
    zone = parts[0]
    risk = ZONE_RISK.get(zone, "high")
    return (zone, risk)


def is_auto_allowed(path: Path, zone: str) -> bool:
    """判断路径是否属于明显可自动清理的生成物"""
    name = path.name
    for pat in AUTO_ALLOW_PATTERNS:
        if path.is_dir() and pat == name:
            return True
        if path.match(pat):
            return True
    # 05-交付区/临时交付/ 内的常见临时文件
    if "05-交付区/临时交付" in str(path.relative_to(ROOT)):
        for pat in TEMP_ALLOW_PATTERNS:
            if path.match(pat):
                return True
    return False


def prompt_confirm(msg: str) -> bool:
    try:
        ans = input(f"{msg} [y/N]: ").strip().lower()
        return ans in ("y", "yes")
    except EOFError:
        return False


def write_audit(path: Path, reason: str, zone: str, risk: str, git: dict, forced: bool, dry_run: bool):
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = "# 删除审计日志\n\n" if not AUDIT_LOG.exists() else ""
    entry = (
        f"| {ts} | `{path}` | {zone} | {risk} | {git['status']} | {reason} | "
        f"{'强制' if forced else '确认'} | {'模拟' if dry_run else '已执行'} | "
        f"`{git['restore_cmd']}` |\n"
    )
    if not AUDIT_LOG.exists():
        header += (
            "| 时间 | 路径 | 区域 | 风险 | Git 状态 | 删除理由 | 审批方式 | 执行结果 | 恢复命令 |\n"
            "|---|---|---|---|---|---|---|---|---|\n"
        )
    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(header + entry)


def delete_one(path: Path, reason: str, force: bool, dry_run: bool, yes: bool):
    if not path.exists():
        print(f"[跳过] 不存在: {path}")
        return

    zone, risk = classify_zone(path)
    git = git_status(path)
    auto_allowed = is_auto_allowed(path, zone)

    print(f"\n[待删除] {path}")
    print(f"  区域: {zone} | 风险: {risk} | Git: {git['status']} | 自动放行: {auto_allowed}")
    print(f"  理由: {reason}")
    print(f"  恢复: {git['restore_cmd']}")

    need_confirm = False
    if risk in ("critical", "high") and git["status"] == "tracked":
        need_confirm = True
    elif risk == "high" and not auto_allowed:
        need_confirm = True
    elif zone == "05-交付区" and "产品交付" in str(path):
        need_confirm = True
    elif zone == "08-归档区" and not auto_allowed:
        need_confirm = True

    if need_confirm and not force:
        if dry_run:
            print("  [模拟] 该删除需要确认或 --force，模拟中止。")
            write_audit(path, reason, zone, risk, git, forced=False, dry_run=True)
            return False
        if not yes and not prompt_confirm("  此删除需要显式确认，是否继续"):
            print("  [取消]")
            return False

    if dry_run:
        print("  [模拟] 已记录，未实际删除。")
        write_audit(path, reason, zone, risk, git, forced=force, dry_run=True)
        return True

    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        write_audit(path, reason, zone, risk, git, forced=force, dry_run=False)
        print("  [已删除并记录]")
        return True
    except Exception as e:
        print(f"  [失败] {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="安全删除工具：带审计、分区、Git 检查")
    parser.add_argument("paths", nargs="+", help="要删除的文件或目录")
    parser.add_argument("--reason", required=True, help="删除理由（必填）")
    parser.add_argument("--force", action="store_true", help="跳过交互确认（仍需理由）")
    parser.add_argument("--dry-run", action="store_true", help="模拟运行，不实际删除")
    parser.add_argument("--yes", action="store_true", help="对自动放行项自动确认")
    args = parser.parse_args()

    results = []
    for p in args.paths:
        path = Path(p).resolve()
        results.append(
            delete_one(path, args.reason, args.force, args.dry_run, args.yes)
        )

    print(f"\n完成: {sum(results)}/{len(results)} 项通过检查")
    if not args.dry_run:
        print(f"审计日志: {AUDIT_LOG}")


if __name__ == "__main__":
    main()
