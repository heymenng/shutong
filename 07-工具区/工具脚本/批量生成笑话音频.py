#!/usr/bin/env python3
"""批量生成笑话库精选文本的多角色音频

用法：
    .venv/bin/python 07-工具区/工具脚本/批量生成笑话音频.py
"""

import subprocess
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "03-引擎区"))

from 书童程序.工具.项目根目录 import get_project_root  # noqa: E402


BASE = get_project_root()
GENERATOR = BASE / "07-工具区/工具脚本/生成笑话音频.py"
AUDIO_DIR = BASE / "05-交付区/产品交付/书童音频节目/音频节目"
JOKE_BASE = BASE / "05-交付区/产品交付/书童音频节目/笑话库"

# 保留的精选笑话（相对 JOKE_BASE 的路径）
JOKE_FILES = [
    "按角色/东北书童/老铁学太极.md",
    "按角色/台湾书童/软软做蛋糕.md",
    "按角色/陕西书童/秦娃修椅子.md",
    "按角色/伴读书童/小师弟点醒.md",
    "按角色/三个书童/买菜记.md",
    "按类型/深度寓意笑话/AI 问禅师.md",
    "按类型/成语新解/对牛弹琴.md",
    "按类型/成语新解/掩耳盗铃.md",
    "按类型/方言相声/三个书童拜师父.md",
    "按类型/历史深度笑话/苏东坡请客.md",
    "按类型/历史深度笑话/王阳明赏花.md",
    "按类型/历史深度笑话/庄子观鱼.md",
]


def main():
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    failed = []
    for rel in JOKE_FILES:
        md_path = JOKE_BASE / rel
        out_name = md_path.stem + "_多角色版.mp3"
        out_path = AUDIO_DIR / out_name
        print(f"\n{'='*60}")
        print(f"生成：{rel} -> {out_name}")
        print('='*60)
        cmd = [
            str(BASE / ".venv/bin/python"),
            str(GENERATOR),
            str(md_path),
            "--out", str(out_path),
        ]
        try:
            result = subprocess.run(
                cmd,
                cwd=str(BASE),
                timeout=180,
                text=True,
            )
            if result.returncode != 0:
                failed.append(rel)
                print(f"[失败] {rel}", file=sys.stderr)
            else:
                print(f"[成功] {out_name}")
        except subprocess.TimeoutExpired:
            failed.append(rel)
            print(f"[超时] {rel}", file=sys.stderr)
        except Exception as e:
            failed.append(rel)
            print(f"[异常] {rel}: {e}", file=sys.stderr)

    print("\n" + "="*60)
    print(f"完成：{len(JOKE_FILES) - len(failed)}/{len(JOKE_FILES)}")
    if failed:
        print("失败列表：")
        for f in failed:
            print(f"  - {f}")
    print(f"输出目录：{AUDIO_DIR}")


if __name__ == "__main__":
    main()
