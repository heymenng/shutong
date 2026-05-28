#!/usr/bin/env python3
"""伴读书童AI - 外部数据集下载脚本（逐文件版）"""

import os
from huggingface_hub import hf_hub_download, HfApi

DOWNLOAD_DIR = os.path.expanduser(
    "~/Documents/qimai/归档封存/历史工作成果/伴读书童AI训练素材库/09-外部数据集"
)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

DATASETS = [
    {
        "repo_id": "styfeng/TinyDialogues",
        "local_dir": "TinyDialogues",
        "description": "儿童对话数据集，适合训练对话能力",
    },
    {
        "repo_id": "YAIR/YouthSafe",
        "local_dir": "YouthSafe",
        "description": "青少年安全对话数据集",
    },
    {
        "repo_id": "BAAI/CCI2-Data",
        "local_dir": "CCI2",
        "description": "中文通用指令数据集",
    },
]


def download_dataset(repo_id, local_dir, description):
    target = os.path.join(DOWNLOAD_DIR, local_dir)
    os.makedirs(target, exist_ok=True)

    try:
        api = HfApi()
        files = api.list_repo_files(repo_id, repo_type="dataset")
    except Exception as e:
        print(f"  获取文件列表失败: {e}")
        return False

    success = 0
    for fname in files:
        local_path = os.path.join(target, fname)
        if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
            print(f"  已存在，跳过: {fname}")
            success += 1
            continue

        try:
            print(f"  下载中: {fname} ...")
            hf_hub_download(
                repo_id=repo_id,
                repo_type="dataset",
                filename=fname,
                local_dir=target,
                local_dir_use_symlinks=False,
                resume_download=True,
            )
            print(f"  完成: {fname}")
            success += 1
        except Exception as e:
            print(f"  失败: {fname} - {e}")

    print(f"  结果: {success}/{len(files)} 个文件")
    return success == len(files)


def main():
    print("伴读书童AI - 外部数据集下载")
    print(f"下载目录: {DOWNLOAD_DIR}\n")

    ok = 0
    for ds in DATASETS:
        print(f"{'='*60}")
        print(f"数据集: {ds['repo_id']}")
        print(f"描述: {ds['description']}")
        print(f"{'='*60}")
        if download_dataset(ds["repo_id"], ds["local_dir"], ds["description"]):
            ok += 1
        print()

    print(f"{'='*60}")
    print(f"完成: {ok}/{len(DATASETS)} 个数据集")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
