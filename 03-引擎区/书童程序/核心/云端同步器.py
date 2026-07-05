"""伴读书童AI - 云端同步器

职责：
1. 扫描本地所有家庭
2. 调用数据脱敏器生成脱敏数据
3. 同步到云端数据区（每个家庭独立目录）
4. 支持增量同步和全量同步
5. 生成云端索引和聚合统计

当前实现：
- 本地模式：把脱敏数据写入项目根目录的 云端数据区/
- 后续可扩展为 HTTP 上传到真正的云端服务器
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .数据脱敏器 import DataSanitizer, sanitize_family


class CloudSyncManager:
    """云端同步管理器"""

    def __init__(self,
                 archive_dir: Optional[str] = None,
                 cloud_dir: Optional[str] = None,
                 salt: Optional[str] = None):
        """
        Args:
            archive_dir: 本地档案区根目录，默认 项目根目录/04-工作区/档案区/家庭群
            cloud_dir: 云端数据区根目录，默认 项目根目录/04-工作区/云端数据区
            salt: 哈希盐值
        """
        project_root = Path(__file__).resolve().parents[3]

        self.archive_dir = Path(archive_dir) if archive_dir else project_root / "04-工作区" / "档案区" / "家庭群"
        self.cloud_dir = Path(cloud_dir) if cloud_dir else project_root / "04-工作区" / "云端数据区"
        self.sanitizer = DataSanitizer(salt=salt)

        self.cloud_dir.mkdir(parents=True, exist_ok=True)
        (self.cloud_dir / "families").mkdir(parents=True, exist_ok=True)

    def discover_families(self) -> List[dict]:
        """
        扫描本地档案区，发现所有家庭
        返回家庭列表，每个包含 family_id, family_json_path, archive_dir
        """
        families = []
        if not self.archive_dir.exists():
            return families

        for family_json in self.archive_dir.rglob("family.json"):
            try:
                with open(family_json, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                family_id = data.get("family_id")
                if not family_id:
                    continue

                families.append({
                    "family_id": family_id,
                    "family_json_path": str(family_json),
                    "archive_dir": str(family_json.parent),
                    "name": data.get("name", "未命名家庭"),
                })
            except Exception as e:
                print(f"[云端同步] 扫描家庭失败 {family_json}: {e}")

        return families

    def sync_family(self, family_id: str, family_json_path: str, archive_dir: str,
                    force: bool = False) -> dict:
        """
        同步单个家庭到云端
        
        Returns:
            {"success": bool, "family_hash": str, "path": str, "error": str or None}
        """
        try:
            result = sanitize_family(family_id, family_json_path, archive_dir)
            family_hash = result["family_profile"]["family_hash"]

            family_cloud_dir = self.cloud_dir / "families" / family_hash
            family_cloud_dir.mkdir(parents=True, exist_ok=True)

            # 检查是否需要增量同步
            sync_meta_path = family_cloud_dir / "sync_meta.json"
            if not force and sync_meta_path.exists():
                with open(sync_meta_path, 'r', encoding='utf-8') as f:
                    old_meta = json.load(f)
                # 简单增量：如果已经存在且时间很近，跳过
                # 实际生产环境应比对内容哈希
                last_sync = datetime.fromisoformat(old_meta.get("last_sync", "2000-01-01T00:00:00"))
                if (datetime.now() - last_sync).total_seconds() < 3600:
                    return {
                        "success": True,
                        "family_hash": family_hash,
                        "path": str(family_cloud_dir),
                        "error": None,
                        "skipped": True
                    }

            # 写入云端数据区
            with open(family_cloud_dir / "family_profile.json", 'w', encoding='utf-8') as f:
                json.dump(result["family_profile"], f, ensure_ascii=False, indent=2)

            with open(family_cloud_dir / "children_profiles.json", 'w', encoding='utf-8') as f:
                json.dump(result["children_profiles"], f, ensure_ascii=False, indent=2)

            with open(family_cloud_dir / "health_events.json", 'w', encoding='utf-8') as f:
                json.dump(result["health_events"], f, ensure_ascii=False, indent=2)

            with open(family_cloud_dir / "outcome_metrics.json", 'w', encoding='utf-8') as f:
                json.dump(result["outcome_metrics"], f, ensure_ascii=False, indent=2)

            # 写入同步元数据
            sync_meta = {
                "family_hash": family_hash,
                "local_family_id": family_id,
                "last_sync": datetime.now().isoformat(),
                "version": "1.0",
                "children_count": len(result["children_profiles"]),
                "health_events_count": len(result["health_events"])
            }
            with open(sync_meta_path, 'w', encoding='utf-8') as f:
                json.dump(sync_meta, f, ensure_ascii=False, indent=2)

            return {
                "success": True,
                "family_hash": family_hash,
                "path": str(family_cloud_dir),
                "error": None,
                "skipped": False
            }

        except Exception as e:
            return {
                "success": False,
                "family_hash": None,
                "path": None,
                "error": str(e),
                "skipped": False
            }

    def sync_all(self, force: bool = False) -> dict:
        """
        同步所有家庭到云端
        
        Returns:
            {"total": int, "success": int, "failed": int, "skipped": int, "details": [...]}
        """
        families = self.discover_families()
        details = []
        success = 0
        failed = 0
        skipped = 0

        for family in families:
            result = self.sync_family(
                family["family_id"],
                family["family_json_path"],
                family["archive_dir"],
                force=force
            )
            details.append({
                "family_id": family["family_id"],
                "name": family["name"],
                **result
            })

            if result.get("success"):
                if result.get("skipped"):
                    skipped += 1
                else:
                    success += 1
            else:
                failed += 1

        # 更新家庭索引
        self._update_family_index(families, details)

        return {
            "total": len(families),
            "success": success,
            "failed": failed,
            "skipped": skipped,
            "details": details,
            "sync_at": datetime.now().isoformat()
        }

    def _update_family_index(self, families: List[dict], details: List[dict]):
        """更新云端家庭索引"""
        index = []
        for family, detail in zip(families, details):
            if detail.get("success"):
                index.append({
                    "family_hash": detail["family_hash"],
                    "last_sync": datetime.now().isoformat(),
                    "name_hash": self.sanitizer.hash_id(f"name:{family['family_id']}"),
                    "children_count": self._count_children(detail["family_hash"])
                })

        with open(self.cloud_dir / "family_index.json", 'w', encoding='utf-8') as f:
            json.dump({
                "total": len(index),
                "sync_at": datetime.now().isoformat(),
                "families": index
            }, f, ensure_ascii=False, indent=2)

    def _count_children(self, family_hash: str) -> int:
        """统计某个云端家庭的孩子数量"""
        path = self.cloud_dir / "families" / family_hash / "children_profiles.json"
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return len(data)
        return 0

    def aggregate_statistics(self, dimension: str, filters: Optional[dict] = None,
                            group_by: Optional[str] = None) -> dict:
        """
        聚合统计查询
        
        Args:
            dimension: 统计维度，如 health_event, family_profile, child_profile
            filters: 过滤条件
            group_by: 分组字段
        """
        filters = filters or {}

        if dimension == "health_event":
            return self._aggregate_health_events(filters, group_by)
        elif dimension == "family_profile":
            return self._aggregate_family_profiles(filters, group_by)
        elif dimension == "child_profile":
            return self._aggregate_child_profiles(filters, group_by)
        else:
            return {"error": f"未知统计维度: {dimension}"}

    def _aggregate_health_events(self, filters: dict, group_by: Optional[str]) -> dict:
        """聚合健康事件统计"""
        event_type = filters.get("event_type")
        season = filters.get("season") or self.sanitizer._current_season()

        # 收集所有事件
        all_events = []
        for family_dir in (self.cloud_dir / "families").iterdir():
            if not family_dir.is_dir():
                continue
            events_path = family_dir / "health_events.json"
            if events_path.exists():
                with open(events_path, 'r', encoding='utf-8') as f:
                    events = json.load(f)
                    for e in events:
                        if event_type and e.get("event_type") != event_type:
                            continue
                        if season and e.get("season") != season:
                            continue
                        all_events.append(e)

        # 加载家庭画像用于分组
        family_profiles = {}
        for e in all_events:
            fh = e.get("family_hash")
            if fh not in family_profiles:
                profile_path = self.cloud_dir / "families" / fh / "family_profile.json"
                if profile_path.exists():
                    with open(profile_path, 'r', encoding='utf-8') as f:
                        family_profiles[fh] = json.load(f)

        # 统计
        total_children = self._total_children()
        affected_children = set()

        # 按组统计
        groups = {}
        if group_by:
            for e in all_events:
                fh = e.get("family_hash")
                profile = family_profiles.get(fh, {})
                group_value = profile.get(group_by, "未知")
                if group_value not in groups:
                    groups[group_value] = {"affected": set(), "count": 0}
                groups[group_value]["affected"].add(e.get("child_hash"))
                groups[group_value]["count"] += 1
                affected_children.add(e.get("child_hash"))

            # 转换 set 为 count
            result_groups = []
            for gv, data in groups.items():
                # 获取该组总孩子数
                group_total = self._count_children_by_group(group_by, gv)
                affected_count = len(data["affected"])
                rate = round(affected_count / group_total * 100, 1) if group_total > 0 else 0
                # 样本量保护
                if group_total < 5:
                    result_groups.append({
                        "group": gv,
                        "total": "样本不足",
                        "affected": "样本不足",
                        "rate": "样本不足"
                    })
                else:
                    result_groups.append({
                        "group": gv,
                        "total": group_total,
                        "affected": affected_count,
                        "rate": f"{rate}%"
                    })
        else:
            affected_count = len(set(e.get("child_hash") for e in all_events))
            rate = round(affected_count / total_children * 100, 1) if total_children > 0 else 0
            result_groups = [{
                "group": "全部",
                "total": total_children,
                "affected": affected_count,
                "rate": f"{rate}%"
            }]

        return {
            "dimension": "health_event",
            "filters": filters,
            "group_by": group_by,
            "total_families": self._total_families(),
            "total_children": total_children,
            "total_events": len(all_events),
            "affected_children": len(affected_children),
            "groups": result_groups
        }

    def _aggregate_family_profiles(self, filters: dict, group_by: Optional[str]) -> dict:
        """聚合家庭画像统计"""
        profiles = []
        for family_dir in (self.cloud_dir / "families").iterdir():
            if not family_dir.is_dir():
                continue
            profile_path = family_dir / "family_profile.json"
            if profile_path.exists():
                with open(profile_path, 'r', encoding='utf-8') as f:
                    profiles.append(json.load(f))

        if not group_by:
            return {"total_families": len(profiles), "profiles": profiles}

        groups = {}
        for p in profiles:
            value = p.get(group_by, "未知")
            groups[value] = groups.get(value, 0) + 1

        return {
            "dimension": "family_profile",
            "group_by": group_by,
            "total_families": len(profiles),
            "groups": [{"group": k, "count": v} for k, v in groups.items()]
        }

    def _aggregate_child_profiles(self, filters: dict, group_by: Optional[str]) -> dict:
        """聚合孩子画像统计"""
        children = []
        for family_dir in (self.cloud_dir / "families").iterdir():
            if not family_dir.is_dir():
                continue
            profile_path = family_dir / "children_profiles.json"
            if profile_path.exists():
                with open(profile_path, 'r', encoding='utf-8') as f:
                    children.extend(json.load(f))

        # 关注标签统计
        tag_counts = {}
        for c in children:
            for tag in c.get("attention_tags", []):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        if not group_by:
            return {
                "dimension": "child_profile",
                "total_children": len(children),
                "top_attention_tags": [{"tag": k, "count": v} for k, v in top_tags]
            }

        groups = {}
        for c in children:
            value = c.get(group_by, "未知")
            groups[value] = groups.get(value, 0) + 1

        return {
            "dimension": "child_profile",
            "group_by": group_by,
            "total_children": len(children),
            "groups": [{"group": k, "count": v} for k, v in groups.items()],
            "top_attention_tags": [{"tag": k, "count": v} for k, v in top_tags]
        }

    def _total_families(self) -> int:
        """云端家庭总数"""
        families_dir = self.cloud_dir / "families"
        if not families_dir.exists():
            return 0
        return sum(1 for d in families_dir.iterdir() if d.is_dir())

    def _total_children(self) -> int:
        """云端孩子总数"""
        total = 0
        for family_dir in (self.cloud_dir / "families").iterdir():
            if not family_dir.is_dir():
                continue
            profile_path = family_dir / "children_profiles.json"
            if profile_path.exists():
                with open(profile_path, 'r', encoding='utf-8') as f:
                    total += len(json.load(f))
        return total

    def _count_children_by_group(self, group_by: str, group_value: str) -> int:
        """按家庭画像分组统计孩子数"""
        count = 0
        for family_dir in (self.cloud_dir / "families").iterdir():
            if not family_dir.is_dir():
                continue
            profile_path = family_dir / "family_profile.json"
            children_path = family_dir / "children_profiles.json"
            if profile_path.exists() and children_path.exists():
                with open(profile_path, 'r', encoding='utf-8') as f:
                    profile = json.load(f)
                if profile.get(group_by) == group_value:
                    with open(children_path, 'r', encoding='utf-8') as f:
                        count += len(json.load(f))
        return count


# 便捷函数
def sync_all_families(archive_dir: Optional[str] = None,
                      cloud_dir: Optional[str] = None,
                      force: bool = False) -> dict:
    """同步所有家庭到云端"""
    manager = CloudSyncManager(archive_dir=archive_dir, cloud_dir=cloud_dir)
    return manager.sync_all(force=force)


def query_cloud_stats(dimension: str,
                      filters: Optional[dict] = None,
                      group_by: Optional[str] = None,
                      cloud_dir: Optional[str] = None) -> dict:
    """查询云端聚合统计"""
    manager = CloudSyncManager(cloud_dir=cloud_dir)
    return manager.aggregate_statistics(dimension, filters, group_by)


if __name__ == "__main__":
    print("=== 同步所有家庭 ===")
    result = sync_all_families(force=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    print("\n=== 健康事件统计：流感 ===")
    stats = query_cloud_stats(
        dimension="health_event",
        filters={"event_type": "流感"},
        group_by="parent_highest_edu"
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))

    print("\n=== 家庭学历分布 ===")
    edu_stats = query_cloud_stats(
        dimension="family_profile",
        group_by="parent_highest_edu"
    )
    print(json.dumps(edu_stats, ensure_ascii=False, indent=2))
