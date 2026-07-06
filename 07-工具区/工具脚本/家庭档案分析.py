#!/usr/bin/env python3
"""家庭档案脱敏分析 CLI

用法示例：
    .venv/bin/python 07-工具区/工具脚本/家庭档案分析.py --cloud --rebuild
    .venv/bin/python 07-工具区/工具脚本/家庭档案分析.py --cloud --label 教师家庭
    .venv/bin/python 07-工具区/工具脚本/家庭档案分析.py --cloud --distribution
"""

import argparse
import json
import sys
from pathlib import Path

def _find_project_root(start: Path) -> Path:
    """向上查找项目根：包含 书童程序 或 03-引擎区 的目录"""
    for parent in [start] + list(start.parents):
        if (parent / "书童程序").is_dir() or (parent / "03-引擎区").is_dir():
            return parent
    return start


PROJECT_ROOT = _find_project_root(Path(__file__).resolve().parent)
sys.path.insert(0, str(PROJECT_ROOT))
if (PROJECT_ROOT / "03-引擎区").is_dir():
    sys.path.insert(0, str(PROJECT_ROOT / "03-引擎区"))

from 书童程序.工具.项目根目录 import get_project_root
from 书童程序.核心 import 家庭档案管理 as archive_mgr


def main():
    parser = argparse.ArgumentParser(description="家庭档案脱敏分析")
    parser.add_argument("--cloud", action="store_true", help="分析云端档案")
    parser.add_argument("--rebuild", action="store_true", help="重建索引")
    parser.add_argument("--distribution", action="store_true", help="输出标签分布")
    parser.add_argument("--label", type=str, help="统计单个标签")
    parser.add_argument("--min-k", type=int, default=10, help="k-匿名阈值")
    args = parser.parse_args()

    if args.cloud:
        data_root = Path("/opt/bookboy-cloud/云端数据区/家庭")
        index_path = archive_mgr.CLOUD_INDEX_PATH
    else:
        data_root = get_project_root() / "04-工作区" / "云端数据区" / "家庭"
        index_path = archive_mgr.LOCAL_INDEX_PATH

    idx = archive_mgr.FamilyArchiveIndex(index_path, data_root)

    if args.rebuild:
        result = idx.rebuild_from_disk()
        print(f"已索引家庭数：{result['indexed']}")

    if args.label:
        print(json.dumps(idx.count_by_label(args.label, min_k=args.min_k), ensure_ascii=False, indent=2))
        return

    if args.distribution:
        print(json.dumps(idx.label_distribution(min_k=args.min_k), ensure_ascii=False, indent=2))
        return

    if not (args.rebuild or args.label or args.distribution):
        print(f"当前索引家庭总数：{idx.total_families()}")
        print("请使用 --distribution 查看标签分布，或 --label <标签名> 统计单个标签。")


if __name__ == "__main__":
    main()
