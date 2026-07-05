#!/usr/bin/env python3
"""
同步 档案区/家庭群/ 到 书童程序/数据/家庭/

规则：
- 档案区/家庭群/ 按分类存放家庭档案，如：
  档案区/家庭群/师父直系/default_family/family.json
  档案区/家庭群/师门/family_lanxin/family.json
- 运行时只需要 flat 结构：书童程序/数据/家庭/<family_id>/family.json
- 本脚本把分类目录下的 family.json 同步到运行时目录，按 family_id 命名。
"""

import shutil
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_BASE = PROJECT_ROOT / "04-工作区" / "档案区" / "家庭群"
DST_BASE = PROJECT_ROOT / "03-引擎区" / "书童程序" / "数据" / "家庭"


def sync_families():
    if not SRC_BASE.exists():
        print(f"源目录不存在: {SRC_BASE}")
        return

    DST_BASE.mkdir(parents=True, exist_ok=True)
    count = 0

    for family_json in SRC_BASE.rglob("family.json"):
        try:
            with open(family_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            family_id = data.get("family_id")
            if not family_id:
                print(f"跳过（无 family_id）: {family_json}")
                continue
            dst_dir = DST_BASE / family_id
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst = dst_dir / "family.json"
            shutil.copy(family_json, dst)
            print(f"同步 {family_id}: {family_json} -> {dst}")
            count += 1
        except Exception as e:
            print(f"同步失败 {family_json}: {e}")

    print(f"\n完成，共同步 {count} 个家庭。")


if __name__ == "__main__":
    sync_families()
