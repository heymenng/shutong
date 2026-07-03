"""
伴读书童AI · 家长助手模块

参考“养龙虾”思路：让家长把书童当成一个能写文案、整理资料、
生成家庭记录的智能助手，生成内容自动存到对应家庭目录。

功能：
- 朋友圈/育儿文案生成
- 给老师的信/请假条生成
- 家庭周报/月报生成
- 育儿心得/成长记录整理
- 自定义文案生成

输出统一保存到：
    档案区/家庭群/<分类>/<family_id>/家长创作/
"""
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_FAMILY_BASE = PROJECT_ROOT / "档案区" / "家庭群"


# 文案模板库
TEMPLATES = {
    "moments": {
        "name": "朋友圈文案",
        "description": "把孩子的成长瞬间写成温暖的朋友圈",
        "icon": "📱",
        "prompt_prefix": "请帮我写一段适合发微信朋友圈的文案，温暖、真实、不夸张。",
        "fields": ["主题/场景", "孩子名字", "想表达的心情/金句"],
    },
    "teacher_letter": {
        "name": "给老师的信",
        "description": "给老师写一封信或请假条",
        "icon": "✉️",
        "prompt_prefix": "请帮我写一封给学校老师的正式短信/邮件/请假条，语气得体、简洁。",
        "fields": ["信件类型", "老师称呼", "主要内容/事由"],
    },
    "weekly_report": {
        "name": "家庭周报",
        "description": "整理一周家庭成长记录",
        "icon": "📅",
        "prompt_prefix": "请根据以下要点，整理成一份温馨的家庭周报，记录孩子成长和家庭生活。",
        "fields": ["本周大事", "孩子成长", "下周计划"],
    },
    "growth_note": {
        "name": "育儿心得",
        "description": "把育儿感悟整理成文章或笔记",
        "icon": "🌱",
        "prompt_prefix": "请帮我把以下育儿感悟整理成一篇流畅的育儿心得或成长记录。",
        "fields": ["标题/主题", "感悟要点"],
    },
    "summary": {
        "name": "工作总结",
        "description": "帮家长整理工作相关总结或汇报",
        "icon": "💼",
        "prompt_prefix": "请帮我整理以下工作内容，写成一份简洁、有条理的工作总结或汇报。",
        "fields": ["工作事项", "成果/数据", "下一步计划"],
    },
    "custom": {
        "name": "自定义",
        "description": "告诉书童你想写什么",
        "icon": "✨",
        "prompt_prefix": "请根据我的需求生成文案。",
        "fields": ["你的需求"],
    },
}


def get_family_dir(family_id: str) -> Optional[Path]:
    """根据 family_id 找到家庭目录"""
    if not ARCHIVE_FAMILY_BASE.exists():
        return None
    for family_json in ARCHIVE_FAMILY_BASE.rglob("family.json"):
        try:
            data = json.loads(family_json.read_text(encoding="utf-8"))
            if data.get("family_id") == family_id:
                return family_json.parent
        except Exception:
            continue
    return None


def get_output_dir(family_id: str) -> Optional[Path]:
    """获取该家庭的家长创作输出目录"""
    family_dir = get_family_dir(family_id)
    if not family_dir:
        return None
    output_dir = family_dir / "家长创作"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def get_templates() -> Dict:
    """返回所有文案模板"""
    return TEMPLATES


def build_prompt(template_id: str, inputs: Dict, family_name: str = "") -> str:
    """根据模板和输入构建生成 prompt"""
    template = TEMPLATES.get(template_id, TEMPLATES["custom"])
    prompt = template["prompt_prefix"]
    if family_name:
        prompt += f"\n\n这是为【{family_name}】家庭生成的内容。"
    prompt += "\n\n用户需求："
    for field in template["fields"]:
        key = field.replace("/", "_")
        value = inputs.get(key, inputs.get(field, ""))
        prompt += f"\n- {field}：{value}"
    prompt += "\n\n要求："
    prompt += "\n1. 语言自然、真实、不堆砌辞藻"
    prompt += "\n2. 符合中国家庭表达习惯"
    prompt += "\n3. 生成的内容可以直接使用，也可以稍作修改"
    prompt += "\n4. 不要出现过于夸张或煽情的表达"
    prompt += "\n5. 如果是信件/邮件，给出完整格式"
    return prompt


def sanitize_filename(title: str) -> str:
    """把标题转成合法文件名"""
    title = title.strip() or "未命名"
    title = re.sub(r'[\\/:*?"<>|]', "_", title)
    title = re.sub(r"\s+", "_", title)
    return title[:50]


def save_creation(family_id: str, template_id: str, title: str, content: str) -> Optional[str]:
    """保存生成的文案到家庭目录，返回保存的文件路径"""
    output_dir = get_output_dir(family_id)
    if not output_dir:
        return None
    
    template = TEMPLATES.get(template_id, TEMPLATES["custom"])
    safe_title = sanitize_filename(title)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{template_id}_{safe_title}.md"
    file_path = output_dir / filename
    
    header = f"""# {title}

> **类型**：{template['name']}  
> **家庭**：{family_id}  
> **生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
> **来源**：伴读书童AI · 家长助手

---

"""
    file_path.write_text(header + content, encoding="utf-8")
    return str(file_path)


def list_creations(family_id: str) -> List[Dict]:
    """列出某家庭已保存的家长创作"""
    output_dir = get_output_dir(family_id)
    if not output_dir or not output_dir.exists():
        return []
    
    creations = []
    for file_path in sorted(output_dir.glob("*.md"), reverse=True):
        try:
            content = file_path.read_text(encoding="utf-8")
            # 提取标题
            title = file_path.stem
            first_line = content.split("\n")[0] if content else ""
            if first_line.startswith("# "):
                title = first_line[2:].strip()
            creations.append({
                "filename": file_path.name,
                "title": title,
                "path": str(file_path.relative_to(PROJECT_ROOT)),
                "created": datetime.fromtimestamp(file_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            })
        except Exception:
            continue
    return creations


def load_creation(family_id: str, filename: str) -> Optional[str]:
    """读取某个已保存的创作内容"""
    output_dir = get_output_dir(family_id)
    if not output_dir:
        return None
    file_path = output_dir / filename
    if not file_path.exists():
        return None
    return file_path.read_text(encoding="utf-8")


def delete_creation(family_id: str, filename: str) -> bool:
    """删除某个创作"""
    output_dir = get_output_dir(family_id)
    if not output_dir:
        return False
    file_path = output_dir / filename
    if not file_path.exists():
        return False
    file_path.unlink()
    return True
