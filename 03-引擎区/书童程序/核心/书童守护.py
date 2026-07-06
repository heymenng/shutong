"""伴读书童AI - 书童Guardian（守护自检模块）

灵感来源：师兄灵觉/Prome的 archive_guardian.py
用途：每次陪伴后自动自检，确保书童守住边界、保持真实、不滑行。

检查维度：
1. 边界守护：不诊断、不开方、不替代家长、不评判孩子
2. 真实守护：不编造、不虚构、不把推测说成事实
3. 身份判位：不混淆师父/孩子/家长的内容和语气
4. 反滑行：不使用通用套话、标签化表达
5. 闭环守护：是否完成观察→回应→记录→反思
"""

import json
from datetime import datetime
from pathlib import Path


def _project_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "01-配置区").exists():
            return parent
    return p.parents[3]


_PROJECT_ROOT = _project_root()


class BookBoyGuardian:
    """书童Guardian：让诚实变成默认路径的脚手架"""

    def __init__(self, journal_dir=None):
        self.journal_dir = Path(journal_dir) if journal_dir else _PROJECT_ROOT / "03-引擎区" / "书童程序" / "数据" / "修行记录"
        self.journal_dir.mkdir(parents=True, exist_ok=True)
    
    def check(self, speaker_id, speaker_name, user_input, response):
        """
        对一次对话进行Guardian自检。
        
        返回：{
            "passed": bool,
            "score": int (0-100),
            "violations": [str],
            "warnings": [str],
            "suggestions": [str],
            "timestamp": str
        }
        """
        violations = []
        warnings = []
        suggestions = []
        
        # 1. 边界守护
        self._check_boundaries(response, violations, warnings)
        
        # 2. 真实守护
        self._check_truthfulness(response, violations, warnings)
        
        # 3. 身份判位
        self._check_speaker_appropriateness(speaker_id, speaker_name, user_input, response, violations, warnings)
        
        # 4. 反滑行
        self._check_against_sliding(response, warnings, suggestions)
        
        # 5. 闭环守护
        self._check_closure(user_input, response, suggestions)
        
        # 计算分数
        score = 100
        score -= len(violations) * 25
        score -= len(warnings) * 10
        score = max(0, score)
        
        result = {
            "timestamp": datetime.now().isoformat(),
            "speaker_id": speaker_id,
            "speaker_name": speaker_name,
            "passed": len(violations) == 0 and score >= 70,
            "score": score,
            "violations": violations,
            "warnings": warnings,
            "suggestions": suggestions,
        }
        
        self._save_check(result)
        return result
    
    def _check_boundaries(self, response, violations, warnings):
        """检查边界是否被守护"""
        # 医疗越界
        medical_terms = ['诊断', '确诊', '药方', '开药', '处方', '服用', '剂量', '你应该吃']
        if any(term in response for term in medical_terms):
            violations.append("医疗越界：出现诊断/开方/用药建议")
        
        # 教育越界：直接给答案
        direct_answer_patterns = ['正确答案是', '答案就是', '应该选', '必须这样做']
        if any(p in response for p in direct_answer_patterns):
            warnings.append("可能教育越界：直接给出标准答案，缺少引导")
        
        # 家长越界：替家长决策
        parent_decision_patterns = ['你应该报', '你必须让', '你应该禁止', '你不应该让']
        if any(p in response for p in parent_decision_patterns):
            warnings.append("家长越界：替代家长做决策")
        
        # 评判孩子
        judgment_terms = ['你怎么这么', '你就是', '你太', '真不听话']
        if any(term in response for term in judgment_terms):
            warnings.append("评判孩子：语气中带有评判")
    
    def _check_truthfulness(self, response, violations, warnings):
        """检查真实优先铁律"""
        # 虚构对话标记
        fabrication_markers = ['【嘟嘟】', '【橙子】', '当时他说', '接着我说', '完整的对话记录如下']
        if any(m in response for m in fabrication_markers):
            violations.append("真实越界：可能编撰虚假对话记录")
        
        # 绝对化事实声明
        certainty_markers = ['确实发生了', '真实发生过', '这是事实']
        if any(m in response for m in certainty_markers):
            warnings.append("绝对化事实声明：需确认来源")
        
        # 视觉/感知声明
        sight_claims = ['书童看到', '书童听见', '书童闻到']
        if any(claim in response for claim in sight_claims):
            warnings.append("感知声明：需确认是否有真实感知证据")
    
    def _check_speaker_appropriateness(self, speaker_id, speaker_name, user_input, response, violations, warnings):
        """检查是否根据对象调整内容"""
        # 如果对象是师父，过于幼稚的表达不合适
        if speaker_id == "default" or speaker_name == "师父":
            childish_terms = ['小盆友', '宝宝', '乖乖', '你最棒']
            if any(term in response for term in childish_terms):
                warnings.append("身份判位偏差：对师父使用了对孩子的话术")
        
        # 如果对象是孩子，过于抽象/医学术语不合适
        if speaker_id not in ["default", "guest"] and speaker_name not in ["师父", "家长"]:
            adult_terms = ['五维', '辨证', '炁脉', '潜意识', '原生家庭']
            if any(term in response for term in adult_terms):
                warnings.append("身份判位偏差：对孩子使用了成人/医学术语")
        
        # 对孩子说"看医生"是允许的，但要温柔
        if '看医生' in response and (speaker_id == "default" or speaker_name == "师父"):
            warnings.append("身份判位提醒：对师父说'看医生'，是否混淆了对象？")
    
    def _check_against_sliding(self, response, warnings, suggestions):
        """检查是否模板滑行"""
        # 通用套话
        generic_phrases = ['祝你健康成长', '希望你天天开心', '加油哦', '你是最棒的']
        if any(p in response for p in generic_phrases):
            warnings.append("滑行风险：使用了通用套话")
        
        # 标签化
        label_patterns = ['6岁就该这样', '12岁叛逆期正常', '青春期都这样']
        if any(p in response for p in label_patterns):
            warnings.append("滑行风险：标签化表达，忽略个体差异")
        
        # 建议
        if len(response) > 200 and response.count('？') == 0:
            suggestions.append("可增加一个反问，减少滑行感")
    
    def _check_closure(self, user_input, response, suggestions):
        """检查闭环是否完整"""
        # 如果孩子表达了情绪，书童是否回应
        emotion_keywords = ['难过', '生气', '害怕', '担心', '烦', '郁闷', '哭']
        if any(kw in user_input for kw in emotion_keywords):
            if not any(m in response for m in ['我懂', '理解', '不容易', '很难受', '陪你']):
                suggestions.append("情绪未回应：孩子表达了情绪，可增加共情")
        
        # 如果孩子提到身体症状，是否提醒就医边界
        symptom_keywords = ['疼', '痛', '发烧', '不舒服']
        if any(kw in user_input for kw in symptom_keywords):
            if '看医生' not in response and '就医' not in response:
                suggestions.append("健康提醒：涉及身体症状时，必要时提醒看医生")
    
    def _save_check(self, result):
        """保存Guardian检查结果"""
        try:
            date_str = datetime.now().strftime("%Y%m%d")
            file_path = self.journal_dir / f"guardian_check_{date_str}.jsonl"
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(result, ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"[Guardian] 保存失败: {e}")
    
    def get_daily_summary(self):
        """获取今日Guardian检查摘要"""
        date_str = datetime.now().strftime("%Y%m%d")
        file_path = self.journal_dir / f"guardian_check_{date_str}.jsonl"
        
        if not file_path.exists():
            return None
        
        checks = []
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    checks.append(json.loads(line))
        
        if not checks:
            return None
        
        total = len(checks)
        passed = sum(1 for c in checks if c.get("passed"))
        avg_score = sum(c.get("score", 0) for c in checks) / total
        all_violations = []
        for c in checks:
            all_violations.extend(c.get("violations", []))
        
        return {
            "total_checks": total,
            "passed": passed,
            "failed": total - passed,
            "average_score": round(avg_score, 1),
            "violation_counts": {v: all_violations.count(v) for v in set(all_violations)},
        }
