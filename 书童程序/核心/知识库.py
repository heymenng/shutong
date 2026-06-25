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
    
    def _extract_keywords(self, query):
        """
        从查询中提取关键词，支持中文、英文和数字。
        对中文进行细粒度分词（2-4字子串），提高匹配率。
        返回按重要性排序的关键词列表。
        """
        import re
        
        # 提取中文文本
        cn_text = ''.join(re.findall(r'[\u4e00-\u9fff]+', query))
        
        # 生成 2-4 字子串（细粒度匹配）
        cn_words = []
        for length in range(2, 5):
            for i in range(len(cn_text) - length + 1):
                cn_words.append(cn_text[i:i+length])
        
        # 英文/数字词（至少2字符）
        en_words = [w.lower() for w in re.findall(r'[a-zA-Z0-9_]{2,}', query)]
        
        keywords = cn_words + en_words
        # 去重但保留顺序（较长词优先）
        seen = set()
        unique = []
        # 按长度降序，优先长词
        sorted_words = sorted(keywords, key=len, reverse=True)
        for w in sorted_words:
            if w not in seen:
                seen.add(w)
                unique.append(w)
        return unique
    
    def _score_content(self, content, keywords):
        """
        计算内容与查询的相关性得分。
        
        权重：
        - 标题匹配：+20 分/词
        - 段落标题匹配：+5 分/词
        - 正文匹配：+1 分/次，最多 10 分/词
        - 关键词越靠前：额外加分
        """
        import re
        score = 0
        lines = content.split('\n')
        
        for kw in keywords:
            kw_lower = kw.lower()
            
            # 1. 文件标题匹配（第一行 # 标题）
            if lines and kw in lines[0]:
                score += 20
            
            # 2. 各级标题匹配
            for line in lines:
                if line.startswith('#') and kw in line:
                    score += 5
            
            # 3. 正文匹配（考虑频次，封顶）
            count = content.lower().count(kw_lower)
            score += min(count, 10)
            
            # 4. 前 500 字匹配加权
            prefix = content[:500].lower()
            if kw_lower in prefix:
                score += 3
        
        return score
    
    def _extract_snippet(self, content, keywords, max_len=800):
        """
        从内容中提取最相关的片段。
        优先提取包含最多关键词的段落，并保留上下文。
        """
        import re
        
        # 按标题和段落拆分
        # 保留标题与其后段落的关联
        sections = re.split(r'\n(?=#{1,4}\s)', content)
        
        section_scores = []
        for section in sections:
            if not section.strip():
                continue
            score = 0
            for kw in keywords:
                kw_lower = kw.lower()
                # 标题匹配（段落第一行）
                first_line = section.split('\n')[0] if section else ''
                if kw in first_line:
                    score += 10
                # 内容频次
                score += section.lower().count(kw_lower)
            section_scores.append((score, section.strip()))
        
        # 按得分排序
        section_scores.sort(key=lambda x: x[0], reverse=True)
        
        # 取前几个片段，控制总长度
        selected = []
        total_len = 0
        for score, section in section_scores[:3]:
            if score == 0:
                continue
            # 截取到合理长度
            section_text = section[:max_len]
            if total_len + len(section_text) > max_len:
                remaining = max_len - total_len
                if remaining > 100:
                    selected.append(section_text[:remaining])
                break
            selected.append(section_text)
            total_len += len(section_text)
        
        return '\n\n'.join(selected)
    
    def retrieve(self, query, max_chars=2000):
        """
        根据查询检索相关知识。
        优化：标题加权、段落加权、智能片段提取、支持中英文。
        """
        keywords = self._extract_keywords(query)
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
                    score = self._score_content(content, keywords)
                    if score > 0:
                        results.append((score, str(md_file.name), content))
                except Exception:
                    continue
        
        # 按相关性排序
        results.sort(key=lambda x: x[0], reverse=True)
        
        # 提取最相关的片段
        retrieved = []
        total_len = 0
        for score, name, content in results[:5]:  # 放宽到前5个文件
            snippet = self._extract_snippet(content, keywords, max_len=max_chars // 3)
            if snippet and total_len + len(snippet) < max_chars:
                # 避免标题重复显示
                clean_snippet = snippet
                first_line = clean_snippet.split('\n')[0] if clean_snippet else ''
                if first_line.startswith('#'):
                    clean_snippet = clean_snippet.lstrip('#').strip() + clean_snippet[len(first_line):]
                retrieved.append(f"【{name}】\n{clean_snippet.strip()}")
                total_len += len(snippet)
        
        return '\n\n---\n\n'.join(retrieved)
