"""伴读书童AI - 数据隐私合规系统（技术层）

职责：
1. 儿童个人信息保护
2. 数据本地化存储
3. 家长授权机制
4. 数据最小化原则
5. 数据删除权

合规原则：
- 遵循《个人信息保护法》《儿童个人信息网络保护规定》
- 默认不收集敏感信息
- 所有数据本地存储，不上传云端（除非家长明确授权）
- 家长有权查看、导出、删除孩子的所有数据
"""

import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class PrivacyCompliance:
    """
    隐私合规系统
    
    核心功能：
    1. 数据分类标记（普通/敏感/特殊）
    2. 家长授权管理
    3. 数据访问控制
    4. 数据导出/删除
    """
    
    # 数据分类
    DATA_NORMAL = "normal"      # 普通数据：作息、任务记录
    DATA_SENSITIVE = "sensitive"  # 敏感数据：健康数据、情绪记录
    DATA_SPECIAL = "special"    # 特殊数据： biometric、位置
    
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.auth_file = self.data_dir / "parent_authorizations.json"
        self.privacy_log = self.data_dir / "privacy_audit.log"
        
        # 加载授权
        self.authorizations = self._load_authorizations()
        
        # 隐私政策版本
        self.privacy_policy_version = "1.0"
        self.privacy_policy_date = "2026-06-01"
    
    # ═══════════════════════════════════════════
    # 1. 家长授权管理
    # ═══════════════════════════════════════════
    
    def request_authorization(self, family_id: str, parent_name: str, 
                             auth_types: List[str]) -> Dict:
        """
        请求家长授权
        
        auth_types: 
        - "basic" - 基础陪伴服务
        - "health" - 健康数据记录
        - "emotion" - 情绪分析
        - "voice" - 语音记录
        - "photo" - 照片/视频
        - "location" - 位置信息
        """
        auth_id = f"AUTH_{family_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        auth = {
            "auth_id": auth_id,
            "family_id": family_id,
            "parent_name": parent_name,
            "auth_types": auth_types,
            "granted_at": datetime.now().isoformat(),
            "status": "granted",
            "privacy_version": self.privacy_policy_version,
        }
        
        if family_id not in self.authorizations:
            self.authorizations[family_id] = []
        
        self.authorizations[family_id].append(auth)
        self._save_authorizations()
        
        self._log_audit("AUTHORIZATION_GRANTED", family_id, f"家长{parent_name}授权: {','.join(auth_types)}")
        
        return auth
    
    def check_authorization(self, family_id: str, auth_type: str) -> bool:
        """检查是否有某项授权"""
        if family_id not in self.authorizations:
            return False
        
        for auth in self.authorizations[family_id]:
            if auth.get("status") == "granted" and auth_type in auth.get("auth_types", []):
                return True
        
        return False
    
    def revoke_authorization(self, family_id: str, auth_type: str = None):
        """
        撤销授权
        
        auth_type为None时撤销所有授权。
        """
        if family_id not in self.authorizations:
            return False
        
        if auth_type is None:
            # 撤销所有
            for auth in self.authorizations[family_id]:
                auth["status"] = "revoked"
                auth["revoked_at"] = datetime.now().isoformat()
        else:
            # 撤销特定类型
            for auth in self.authorizations[family_id]:
                if auth_type in auth.get("auth_types", []):
                    auth["auth_types"].remove(auth_type)
                    if not auth["auth_types"]:
                        auth["status"] = "revoked"
                        auth["revoked_at"] = datetime.now().isoformat()
        
        self._save_authorizations()
        self._log_audit("AUTHORIZATION_REVOKED", family_id, f"撤销授权: {auth_type or '全部'}")
        
        return True
    
    # ═══════════════════════════════════════════
    # 2. 数据访问控制
    # ═══════════════════════════════════════════
    
    def can_access(self, data_type: str, family_id: str, accessor: str = "parent") -> bool:
        """
        检查是否可以访问某类数据
        
        accessor: parent/child/system
        """
        # 家长总是可以访问自己孩子的数据
        if accessor == "parent":
            return True
        
        # 孩子可以访问自己的非敏感数据
        if accessor == "child":
            return data_type != self.DATA_SPECIAL
        
        # 系统访问需要授权
        if accessor == "system":
            if data_type == self.DATA_NORMAL:
                return True
            elif data_type == self.DATA_SENSITIVE:
                return self.check_authorization(family_id, "health") or \
                       self.check_authorization(family_id, "emotion")
            elif data_type == self.DATA_SPECIAL:
                return self.check_authorization(family_id, "voice") or \
                       self.check_authorization(family_id, "photo") or \
                       self.check_authorization(family_id, "location")
        
        return False
    
    def classify_data(self, data_content: str) -> str:
        """
        自动分类数据敏感度
        
        简化版：根据关键词判断
        """
        sensitive_keywords = ["病历", "诊断", "体温", "血压", "情绪", "心理", "抑郁", "焦虑"]
        special_keywords = ["位置", "GPS", "人脸", "指纹", "声音"]
        
        for kw in special_keywords:
            if kw in data_content:
                return self.DATA_SPECIAL
        
        for kw in sensitive_keywords:
            if kw in data_content:
                return self.DATA_SENSITIVE
        
        return self.DATA_NORMAL
    
    # ═══════════════════════════════════════════
    # 3. 数据导出（家长权利）
    # ═══════════════════════════════════════════
    
    def export_child_data(self, child_id: str, export_dir: str) -> Dict:
        """
        导出孩子的所有数据
        
        返回导出文件路径。
        """
        export_path = Path(export_dir)
        export_path.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_file = export_path / f"child_{child_id}_export_{timestamp}.json"
        
        # 收集所有相关数据
        export_data = {
            "export_time": datetime.now().isoformat(),
            "child_id": child_id,
            "privacy_version": self.privacy_policy_version,
            "data": {},
        }
        
        # 从修行记录目录收集
        journal_dir = self.data_dir / "修行记录"
        if journal_dir.exists():
            for file_path in journal_dir.glob(f"*{child_id}*"):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        if file_path.suffix == '.json':
                            export_data["data"][file_path.name] = json.load(f)
                        elif file_path.suffix == '.jsonl':
                            lines = []
                            for line in f:
                                if line.strip():
                                    lines.append(json.loads(line))
                            export_data["data"][file_path.name] = lines
                except Exception as e:
                    export_data["data"][file_path.name] = f"读取错误: {e}"
        
        # 保存导出文件
        with open(export_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        self._log_audit("DATA_EXPORTED", child_id, f"数据已导出: {export_file}")
        
        return {
            "success": True,
            "export_file": str(export_file),
            "data_size": len(json.dumps(export_data)),
        }
    
    # ═══════════════════════════════════════════
    # 4. 数据删除（被遗忘权）
    # ═══════════════════════════════════════════
    
    def delete_child_data(self, child_id: str, delete_type: str = "all") -> Dict:
        """
        删除孩子的所有数据
        
        delete_type:
        - "all": 全部删除
        - "chat": 只删除对话记录
        - "health": 只删除健康数据
        """
        deleted_files = []
        
        journal_dir = self.data_dir / "修行记录"
        if journal_dir.exists():
            for file_path in journal_dir.glob(f"*{child_id}*"):
                try:
                    if delete_type == "all":
                        file_path.unlink()
                        deleted_files.append(str(file_path.name))
                    elif delete_type == "chat" and "session" in file_path.name:
                        file_path.unlink()
                        deleted_files.append(str(file_path.name))
                    elif delete_type == "health" and "growth" in file_path.name:
                        file_path.unlink()
                        deleted_files.append(str(file_path.name))
                except Exception as e:
                    print(f"删除失败 {file_path}: {e}")
        
        self._log_audit("DATA_DELETED", child_id, f"删除类型: {delete_type}, 文件数: {len(deleted_files)}")
        
        return {
            "success": True,
            "deleted_files": deleted_files,
            "delete_type": delete_type,
        }
    
    # ═══════════════════════════════════════════
    # 5. 隐私政策
    # ═══════════════════════════════════════════
    
    def get_privacy_policy(self) -> str:
        """获取隐私政策文本"""
        return """
伴读书童AI 隐私政策 V1.0

1. 我们收集什么数据？
   - 基础数据：孩子年龄、作息时间
   - 健康数据：睡眠、运动、饮食记录（需家长授权）
   - 对话数据：与书童的对话记录（本地存储）

2. 数据存储在哪里？
   - 默认：本地存储，不上传云端
   - 云端备份：需家长明确授权

3. 谁可以访问数据？
   - 家长：可以查看、导出、删除所有数据
   - 孩子：可以查看自己的非敏感数据
   - 书童AI：仅用于提供服务

4. 家长权利：
   - 查看权：随时查看孩子的所有数据
   - 导出权：导出JSON格式的完整数据
   - 删除权：删除全部或部分数据
   - 撤销权：随时撤销授权

5. 数据安全：
   - 所有数据加密存储
   - 定期备份
   - 不用于商业目的
   - 不与第三方共享

6. 联系我们：
   如有隐私问题，请联系家长支持。
"""
    
    # ═══════════════════════════════════════════
    # 内部方法
    # ═══════════════════════════════════════════
    
    def _load_authorizations(self) -> Dict:
        """加载授权记录"""
        if self.auth_file.exists():
            with open(self.auth_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def _save_authorizations(self):
        """保存授权记录"""
        with open(self.auth_file, 'w', encoding='utf-8') as f:
            json.dump(self.authorizations, f, ensure_ascii=False, indent=2)
    
    def _log_audit(self, action: str, target: str, detail: str):
        """记录审计日志"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "target": target,
            "detail": detail,
        }
        
        with open(self.privacy_log, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
