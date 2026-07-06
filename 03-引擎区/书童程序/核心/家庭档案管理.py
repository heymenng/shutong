"""伴读书童AI · 家庭档案管理与脱敏分析系统

把家庭档案视为核心资产：
- 原始档案（family.json、聊天记录等）保留在按家庭分区的目录里，是资产本体。
- 元数据与标签索引存放在轻量索引库（SQLite/PostgreSQL）中，用于快速检索、聚合与脱敏分析。
- 任何分析结果都必须经过脱敏门控：只返回聚合统计或脱敏后的明细，避免个体识别。
"""

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..工具.项目根目录 import get_project_root


# ═══════════════════════════════════════════════════
# 标签规则引擎
# ═══════════════════════════════════════════════════

LABEL_RULES = {
    "教师家庭": {
        "keywords": ["老师", "教师", "教授", "导师", "家教", "班主任", "学校", "教育", "教书", "师范", "讲师"],
        "description": "家庭成员从事教育、教学或学校相关工作",
    },
    "炒股家庭": {
        "keywords": ["股票", "炒股", "投资", "基金", "证券", "期货", "美股", "A股", "理财", "金融", "券商", "股市", "韭菜"],
        "description": "家庭兴趣或职业与股票、证券投资相关",
    },
    "医护家庭": {
        "keywords": ["医生", "护士", "医院", "医药", "医师", "临床", "医学", "药剂", "康复", "大夫", "卫健委", "牙医", "中医"],
        "description": "家庭成员从事医疗、护理或医药行业",
    },
    "IT家庭": {
        "keywords": ["程序员", "工程师", "互联网", "IT", "算法", "开发", "软件", "架构", "运维", "人工智能", "AI", "大数据", "云计算", "码农", "产品经理", "数据"],
        "description": "家庭成员从事信息技术、互联网或人工智能相关工作",
    },
    "多孩家庭": {
        "rule": "child_count >= 2",
        "description": "家庭中有两个及以上孩子",
    },
    "单亲家庭": {
        "rule": "adult_count == 1 and child_count >= 1",
        "description": "家庭中仅有一位成年人且至少有一个孩子",
    },
    "独生家庭": {
        "rule": "child_count == 1",
        "description": "家庭中只有一个孩子",
    },
    "高龄抚养": {
        "rule": "elder_count >= 1 and child_count >= 1",
        "description": "家庭中有老人与孩子共同生活",
    },
}


def _flatten_family_text(family_data: Dict) -> str:
    """把家庭 JSON 中可搜索的文本拼成一个字符串"""
    parts = []
    for key in ("name", "description"):
        parts.append(str(family_data.get(key) or ""))
    for m in family_data.get("members", []):
        for field in ("name", "role", "relation", "gender", "grade", "occupation", "school", "note"):
            parts.append(str(m.get(field) or ""))
        interests = m.get("interests") or []
        if isinstance(interests, list):
            parts.extend(str(i) for i in interests)
        else:
            parts.append(str(interests))
    return " ".join(parts)


def _match_keywords(text: str, keywords: List[str]) -> bool:
    text = text.lower()
    for kw in keywords:
        if kw.lower() in text:
            return True
    return False


def label_family(family_data: Dict) -> List[str]:
    """为单个家庭打上标签"""
    members = family_data.get("members", []) or []
    child_count = sum(1 for m in members if (m.get("role") or "").lower() in ("孩子", "child", "学生"))
    adult_count = sum(1 for m in members if (m.get("role") or "").lower() in ("家长", "parent", "父亲", "母亲", "爸爸", "妈妈", "adult", "师父"))
    elder_count = sum(
        1 for m in members
        if (m.get("age") or 0) >= 60 or _match_keywords(str(m.get("relation") or ""), ["爷爷", "奶奶", "外公", "外婆", "祖父", "祖母"])
    )

    flat_text = _flatten_family_text(family_data)
    labels = []
    context = {
        "child_count": child_count,
        "adult_count": adult_count,
        "elder_count": elder_count,
        "member_count": len(members),
    }

    for label, cfg in LABEL_RULES.items():
        if "keywords" in cfg:
            if _match_keywords(flat_text, cfg["keywords"]):
                labels.append(label)
        elif "rule" in cfg:
            try:
                if eval(cfg["rule"], {"__builtins__": {}}, context):
                    labels.append(label)
            except Exception:
                pass

    return sorted(set(labels))


# ═══════════════════════════════════════════════════
# 索引层
# ═══════════════════════════════════════════════════

class FamilyArchiveIndex:
    """家庭档案元数据索引

    设计原则：
    - 索引只存脱敏后的摘要和标签，不存完整聊天记录。
    - 支持增量更新（家庭保存时同步更新索引）。
    - 聚合查询带 k-匿名门控，避免小样本反向识别。
    """

    def __init__(self, index_db_path: Path, family_data_root: Optional[Path] = None):
        self.db_path = Path(index_db_path)
        self.family_data_root = Path(family_data_root) if family_data_root else None
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS family_index (
                    family_id TEXT PRIMARY KEY,
                    name TEXT,
                    member_count INTEGER DEFAULT 0,
                    child_count INTEGER DEFAULT 0,
                    adult_count INTEGER DEFAULT 0,
                    elder_count INTEGER DEFAULT 0,
                    labels TEXT DEFAULT '[]',
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS label_stats (
                    label TEXT PRIMARY KEY,
                    total INTEGER DEFAULT 0,
                    updated_at TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_family_label
                ON family_index(labels)
            """)

    def _now(self) -> str:
        return datetime.now().isoformat()

    def index_family(self, family_id: str, family_data: Dict):
        """索引/更新单个家庭"""
        members = family_data.get("members", []) or []
        child_count = sum(1 for m in members if (m.get("role") or "").lower() in ("孩子", "child", "学生"))
        adult_count = sum(1 for m in members if (m.get("role") or "").lower() in ("家长", "parent", "父亲", "母亲", "爸爸", "妈妈", "adult", "师父"))
        elder_count = sum(
            1 for m in members
            if (m.get("age") or 0) >= 60 or _match_keywords(str(m.get("relation") or ""), ["爷爷", "奶奶", "外公", "外婆", "祖父", "祖母"])
        )
        labels = label_family(family_data)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO family_index
                (family_id, name, member_count, child_count, adult_count, elder_count, labels, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(family_id) DO UPDATE SET
                    name=excluded.name,
                    member_count=excluded.member_count,
                    child_count=excluded.child_count,
                    adult_count=excluded.adult_count,
                    elder_count=excluded.elder_count,
                    labels=excluded.labels,
                    updated_at=excluded.updated_at
                """,
                (
                    family_id,
                    (family_data.get("name") or "")[:50],
                    len(members),
                    child_count,
                    adult_count,
                    elder_count,
                    json.dumps(labels, ensure_ascii=False),
                    family_data.get("created_at") or self._now(),
                    self._now(),
                ),
            )
        self._rebuild_label_stats()
        return {"family_id": family_id, "labels": labels}

    def remove_family(self, family_id: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM family_index WHERE family_id = ?", (family_id,))
        self._rebuild_label_stats()

    def _rebuild_label_stats(self):
        """根据索引重建标签统计缓存"""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT labels FROM family_index").fetchall()
        counts: Dict[str, int] = {}
        for (label_json,) in rows:
            for label in json.loads(label_json):
                counts[label] = counts.get(label, 0) + 1
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM label_stats")
            for label, total in counts.items():
                conn.execute(
                    "INSERT INTO label_stats (label, total, updated_at) VALUES (?, ?, ?)",
                    (label, total, self._now()),
                )

    def rebuild_from_disk(self):
        """从 family_data_root 扫描所有 family.json 重建索引"""
        if not self.family_data_root:
            raise ValueError("未指定 family_data_root，无法从磁盘重建")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM family_index")
        count = 0
        for family_dir in self.family_data_root.iterdir():
            if not family_dir.is_dir():
                continue
            family_json = family_dir / "family.json"
            if not family_json.exists():
                continue
            try:
                data = json.loads(family_json.read_text(encoding="utf-8"))
                self.index_family(family_dir.name, data)
                count += 1
            except Exception as e:
                print(f"[档案索引] 跳过 {family_dir.name}: {e}")
        self._rebuild_label_stats()
        return {"indexed": count}

    def total_families(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM family_index").fetchone()
        return row[0] if row else 0

    def count_by_label(self, label: str, min_k: int = 10) -> Dict[str, Any]:
        """返回某标签的家庭数量与占比（带 k-匿名门控）"""
        total = self.total_families()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM family_index WHERE labels LIKE ?",
                (f'%"{label}"%',),
            ).fetchone()
        count = row[0] if row else 0
        if count < min_k:
            return {"label": label, "count": None, "proportion": None, "note": f"样本不足（<{min_k}），按脱敏规则不展示具体数量"}
        return {
            "label": label,
            "count": count,
            "total": total,
            "proportion": round(count / total, 6) if total else 0.0,
        }

    def label_distribution(self, min_k: int = 10) -> Dict[str, Any]:
        """返回所有标签的分布（聚合后）"""
        total = self.total_families()
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT label, total FROM label_stats ORDER BY total DESC").fetchall()
        items = []
        for label, count in rows:
            if count < min_k:
                items.append({"label": label, "count": None, "proportion": None, "note": "样本不足"})
            else:
                items.append({"label": label, "count": count, "proportion": round(count / total, 6) if total else 0.0})
        return {"total": total, "items": items}

    def query(self, filters: Dict[str, Any], min_k: int = 10) -> Dict[str, Any]:
        """结构化过滤查询，只返回聚合计数"""
        clauses = ["1=1"]
        params = []
        if "labels" in filters:
            for label in filters["labels"]:
                clauses.append("labels LIKE ?")
                params.append(f'%"{label}"%')
        if "child_count_min" in filters:
            clauses.append("child_count >= ?")
            params.append(int(filters["child_count_min"]))
        if "child_count_max" in filters:
            clauses.append("child_count <= ?")
            params.append(int(filters["child_count_max"]))
        if "member_count_min" in filters:
            clauses.append("member_count >= ?")
            params.append(int(filters["member_count_min"]))

        where = " AND ".join(clauses)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(f"SELECT COUNT(*) FROM family_index WHERE {where}", params).fetchone()
        count = row[0] if row else 0
        total = self.total_families()
        if count < min_k:
            return {"count": None, "total": total, "note": f"命中样本不足（<{min_k}），不展示"}
        return {"count": count, "total": total, "proportion": round(count / total, 6) if total else 0.0}

    def search(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
        offset: int = 0,
        desensitize: bool = True,
    ) -> List[Dict[str, Any]]:
        """返回家庭明细（默认脱敏）"""
        filters = filters or {}
        clauses = ["1=1"]
        params = []
        if "labels" in filters:
            for label in filters["labels"]:
                clauses.append("labels LIKE ?")
                params.append(f'%"{label}"%')

        where = " AND ".join(clauses)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM family_index WHERE {where} LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()

        results = []
        for row in rows:
            item = dict(row)
            item["labels"] = json.loads(item["labels"] or "[]")
            if desensitize:
                item["family_id"] = self._hash_family_id(item["family_id"])
                item["name"] = self._mask_name(item["name"])
            results.append(item)
        return results

    @staticmethod
    def _hash_family_id(family_id: str) -> str:
        import hashlib
        return hashlib.sha256(family_id.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _mask_name(name: str) -> str:
        if not name:
            return ""
        if len(name) <= 2:
            return name[0] + "*"
        return name[0] + "*" * (len(name) - 2) + name[-1]


# ═══════════════════════════════════════════════════
# 便捷工厂函数
# ═══════════════════════════════════════════════════

LOCAL_INDEX_PATH = get_project_root() / "04-工作区" / "云端数据区" / "档案索引" / "family_archive_index.db"
CLOUD_INDEX_PATH = Path("/opt/bookboy-cloud/云端数据区/档案索引/family_archive_index.db")


def get_index(data_root: Optional[Path] = None, cloud: bool = False) -> FamilyArchiveIndex:
    if cloud:
        return FamilyArchiveIndex(CLOUD_INDEX_PATH, data_root)
    return FamilyArchiveIndex(LOCAL_INDEX_PATH, data_root)


def report(data_root: Path, cloud: bool = False, min_k: int = 10) -> Dict[str, Any]:
    """生成一份完整的家庭档案标签分布报告"""
    idx = get_index(data_root, cloud=cloud)
    rebuild = idx.rebuild_from_disk()
    return {
        "indexed_families": rebuild["indexed"],
        "label_distribution": idx.label_distribution(min_k=min_k),
    }
