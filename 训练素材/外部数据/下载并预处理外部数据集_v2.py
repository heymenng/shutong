#!/usr/bin/env python3
"""伴读书童AI - 外部数据集下载与预处理脚本 v2.0"""

import os
import sys
import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime

try:
    from huggingface_hub import snapshot_download
except ImportError:
    print("请先安装依赖: pip install huggingface_hub")
    sys.exit(1)

DOWNLOAD_DIR = Path(
    "~/Documents/qimai/归档封存/历史工作成果/伴读书童AI训练素材库/09-外部数据集"
).expanduser()
LOG_DIR = DOWNLOAD_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"download_{datetime.now():%Y%m%d_%H%M%S}.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

DATASETS = [
    {
        "repo_id": "styfeng/TinyDialogues",
        "local_dir": "TinyDialogues",
        "description": "130k儿童导向对话，按年龄分层的英语对话数据",
        "type": "dataset",
        "expected_files": ["README.md", "train.jsonl", "val.jsonl"],
        "size_hint": "~500MB",
    },
    {
        "repo_id": "YouthSafe/YouthSafe-Teen-GAI-Risk",
        "local_dir": "YouthSafe",
        "description": "青少年安全护栏模型（基于LlamaGuard-7b微调的PEFT模型）",
        "type": "model",
        "expected_files": ["README.md", "adapter_config.json", "adapter_model.safetensors"],
        "size_hint": "~1GB",
        "note": "此为安全分类模型，YAIR数据集本体需通过论文渠道申请",
    },
    {
        "repo_id": "BAAI/CCI2-Data",
        "local_dir": "CCI2",
        "description": "中文通用指令数据集 CCI 2.0（501GB，分片存储）",
        "type": "dataset",
        "expected_files": [],
        "size_hint": "~501GB",
        "warning": "体积极大，建议按需下载特定分片而非全量",
    },
    {
        "repo_id": "HIT-SCIR-SC/QiaoBan",
        "local_dir": "QiaoBan",
        "description": "中文儿童情感支持对话数据集",
        "type": "dataset",
        "expected_files": ["README.md"],
        "size_hint": "~100MB",
    },
    {
        "repo_id": "rescommons/ASD_V3_all_ages",
        "local_dir": "ASD_Screening_V3",
        "description": "自闭症筛查数据集V3（含儿童2,514例记录）",
        "type": "dataset",
        "expected_files": ["README.md"],
        "size_hint": "~50MB",
    },
]


def calculate_sha256(filepath, chunk_size=8192):
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def verify_download(target_dir, expected_files):
    if not expected_files:
        return True
    missing = []
    for fname in expected_files:
        fpath = target_dir / fname
        if not fpath.exists() or fpath.stat().st_size == 0:
            missing.append(fname)
    if missing:
        logger.warning(f"  缺失或空文件: {', '.join(missing)}")
        return False
    return True


def download_with_retry(repo_id, local_dir, repo_type="dataset", max_retries=3):
    target = DOWNLOAD_DIR / local_dir
    target.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"  尝试 {attempt}/{max_retries}: 下载 {repo_id} ...")
            snapshot_download(
                repo_id=repo_id,
                repo_type=repo_type,
                local_dir=str(target),
                local_dir_use_symlinks=False,
                resume_download=True,
            )
            logger.info(f"  下载成功: {repo_id}")
            return True
        except Exception as e:
            logger.error(f"  下载失败: {e}")
            if attempt == max_retries:
                return False
    return False


def preprocess_tinydialogues():
    src_dir = DOWNLOAD_DIR / "TinyDialogues"
    out_dir = DOWNLOAD_DIR / "TinyDialogues_processed"
    out_dir.mkdir(exist_ok=True)
    logger.info("[预处理] TinyDialogues - 按年龄段分离...")
    age_groups = {"age2": [], "age5": [], "age10": [], "age15": []}
    for jsonl_file in src_dir.rglob("*.jsonl"):
        logger.info(f"  处理: {jsonl_file.name}")
    report = {
        "dataset": "TinyDialogues",
        "processed_at": datetime.now().isoformat(),
        "age_groups": {k: len(v) for k, v in age_groups.items()},
        "note": "请根据实际下载的文件格式完善解析逻辑",
    }
    with open(out_dir / "preprocess_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info(f"[预处理] TinyDialogues 完成，报告已保存")
    return report


def preprocess_qiaoban():
    src_dir = DOWNLOAD_DIR / "QiaoBan"
    out_dir = DOWNLOAD_DIR / "QiaoBan_processed"
    out_dir.mkdir(exist_ok=True)
    logger.info("[预处理] QiaoBan - 情感标签标准化...")
    report = {
        "dataset": "QiaoBan",
        "processed_at": datetime.now().isoformat(),
        "note": "待根据实际数据格式补充",
    }
    with open(out_dir / "preprocess_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report


def generate_usage_guide():
    guide = {
        "project": "伴读书童AI",
        "version": "2.0",
        "generated_at": datetime.now().isoformat(),
        "datasets": {},
        "integration": {
            "training_pipeline": {
                "stage1_pretrain": ["CCI2(筛选后)", "TinyDialogues"],
                "stage2_finetune": ["QiaoBan", "内部医学对话"],
                "stage3_safety": ["YouthSafe模型", "ASD Screening"],
                "stage4_culture": ["内部故事库", "文化对话"],
            },
            "data_mixing_ratio": {
                "通用对话": 0.4,
                "儿童专用对话": 0.3,
                "医学/安全": 0.2,
                "文化/价值观": 0.1,
            },
        },
        "note": "详见 数据预处理指南.md",
    }
    for ds in DATASETS:
        guide["datasets"][ds["local_dir"]] = {
            "repo_id": ds["repo_id"],
            "type": ds["type"],
            "description": ds["description"],
            "size_hint": ds.get("size_hint", "unknown"),
            "local_path": str(DOWNLOAD_DIR / ds["local_dir"]),
        }
    guide_path = DOWNLOAD_DIR / "dataset_usage_guide.json"
    with open(guide_path, "w", encoding="utf-8") as f:
        json.dump(guide, f, ensure_ascii=False, indent=2)
    logger.info(f"[指南] 数据集使用指南已生成: {guide_path}")
    return guide


def main():
    print("=" * 70)
    print("伴读书童AI - 外部数据集下载与预处理脚本 v2.0")
    print("=" * 70)
    print(f"下载目录: {DOWNLOAD_DIR}")
    print(f"日志目录: {LOG_DIR}")
    print("=" * 70)
    print()

    results = []
    for ds in DATASETS:
        print(f"\n{'─' * 60}")
        print(f"数据集: {ds['repo_id']}")
        print(f"类型: {ds['type']} | 预计大小: {ds.get('size_hint', 'unknown')}")
        print(f"描述: {ds['description']}")
        if "warning" in ds:
            print(f"注意: {ds['warning']}")
        print(f"{'─' * 60}")
        success = download_with_retry(
            repo_id=ds["repo_id"],
            local_dir=ds["local_dir"],
            repo_type=ds["type"],
        )
        if success:
            target = DOWNLOAD_DIR / ds["local_dir"]
            verified = verify_download(target, ds.get("expected_files", []))
            results.append({
                "name": ds["repo_id"],
                "status": "success" if verified else "partial",
                "path": str(target),
            })
        else:
            results.append({
                "name": ds["repo_id"],
                "status": "failed",
                "path": "",
            })

    print(f"\n{'=' * 70}")
    print("阶段2: 预处理")
    print(f"{'=' * 70}")
    preprocess_tasks = {
        "TinyDialogues": preprocess_tinydialogues,
        "QiaoBan": preprocess_qiaoban,
    }
    for name, func in preprocess_tasks.items():
        target_dir = DOWNLOAD_DIR / name
        if target_dir.exists() and any(target_dir.iterdir()):
            try:
                func()
            except Exception as e:
                logger.error(f"[预处理] {name} 失败: {e}")
        else:
            logger.info(f"[预处理] 跳过 {name}（未下载）")

    print(f"\n{'=' * 70}")
    print("阶段3: 生成使用指南")
    print(f"{'=' * 70}")
    generate_usage_guide()

    print(f"\n{'=' * 70}")
    print("下载汇总")
    print(f"{'=' * 70}")
    success_count = sum(1 for r in results if r["status"] == "success")
    partial_count = sum(1 for r in results if r["status"] == "partial")
    failed_count = sum(1 for r in results if r["status"] == "failed")
    for r in results:
        icon = "✅" if r["status"] == "success" else "⚠️" if r["status"] == "partial" else "❌"
        print(f"{icon} {r['name']}: {r['status']}")
    print(f"\n总计: {success_count} 成功 | {partial_count} 部分 | {failed_count} 失败")
    print(f"{'=' * 70}")

    summary = {
        "timestamp": datetime.now().isoformat(),
        "results": results,
        "stats": {
            "success": success_count,
            "partial": partial_count,
            "failed": failed_count,
        },
    }
    with open(LOG_DIR / f"summary_{datetime.now():%Y%m%d_%H%M%S}.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
