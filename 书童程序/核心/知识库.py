"""伴读书童AI - 知识库模块"""

import os
from pathlib import Path
from ..配置 import DATA_DIR

class KnowledgeBase:
    def __init__(self):
        self.base_path = DATA_DIR
        self.knowledge_dirs = [
            "核心规律",
            "对话场景", 
            "故事库",
            "安全应急",
            "知识分类"
        ]
    
    def list_files(self):
        files = []
        for dir_name in self.knowledge_dirs:
            dir_path = self.base_path / dir_name
            if dir_path.exists():
                for md_file in dir_path.glob("*.md"):
                    files.append(str(md_file))
        return files
    
    def get_stats(self):
        stats = {}
        total_files = 0
        for dir_name in self.knowledge_dirs:
            dir_path = self.base_path / dir_name
            if dir_path.exists():
                count = len(list(dir_path.glob("*.md")))
                stats[dir_name] = count
                total_files += count
        stats["total"] = total_files
        return stats
    
    def retrieve(self, query, max_chars=2000):
        """根据查询检索相关知识"""
        import re
        
        # 提取关键词（简单分词）
        keywords = [w for w in re.findall(r'[\u4e00-\u9fff]+', query) if len(w) >= 2]
        if not keywords:
            return ""
        
        results = []
        for dir_name in self.knowledge_dirs:
            dir_path = self.base_path / dir_name
            if not dir_path.exists():
                continue
            for md_file in dir_path.glob("*.md"):
                try:
                    content = md_file.read_text(encoding='utf-8')
                    score = sum(1 for kw in keywords if kw in content)
                    if score > 0:
                        results.append((score, str(md_file.name), content))
                except:
                    continue
        
        # 按相关性排序
        results.sort(key=lambda x: x[0], reverse=True)
        
        # 提取最相关的片段
        retrieved = []
        total_len = 0
        for score, name, content in results[:3]:
            # 找到包含关键词的段落
            paragraphs = content.split('\n\n')
            relevant = []
            for p in paragraphs:
                if any(kw in p for kw in keywords[:3]):
                    relevant.append(p)
            
            if relevant:
                snippet = '\n\n'.join(relevant[:3])
                if total_len + len(snippet) < max_chars:
                    retrieved.append(f"【{name}】\n{snippet}")
                    total_len += len(snippet)
        
        return '\n\n---\n\n'.join(retrieved)
