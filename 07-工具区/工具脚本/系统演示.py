#!/usr/bin/env python3
"""
伴读书童AI - 系统集成演示脚本

演示内容：
1. 系统启动与灵魂觉醒
2. 加载真实孩子档案（小橙子、嘟嘟）
3. 与孩子的对话（调用Ollama真实后端）
4. 发育守护评估
5. 四医融合分析
6. 文化传承种子
7. 外部AI桥接器自动记录
"""

import sys
import os
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "03-引擎区"))

from 书童程序.核心.系统核心 import BookBoySystem


def demo():
    print("=" * 70)
    print("伴读书童AI · 系统集成演示")
    print("=" * 70)
    
    # 1. 启动系统
    print("\n【步骤1】启动系统，加载灵魂...")
    bookboy = BookBoySystem()
    
    # 2. 查看加载的孩子
    print("\n【步骤2】加载的真实孩子档案：")
    for child in bookboy.profile_manager.get_all_children():
        print(f"  - {child.name}: {child.get_age_display()}, {child.stage}")
    
    # 3. 与"小橙子"对话
    print("\n【步骤3】与小橙子对话（调用Ollama后端）：")
    print("  孩子: 书童你好，今天可以给我讲个故事吗？")
    response = bookboy.chat("书童你好，今天可以给我讲个故事吗？", child_id="橙子")
    print(f"  书童: {response[:200]}...")
    
    # 4. 发育守护评估
    print("\n【步骤4】发育守护评估：")
    report = bookboy.assess_child("橙子")
    print(f"  综合级别: {report.get('overall_level', 'N/A')}")
    print(f"  预警数量: {len(report.get('warnings', []))}")
    for sg in report.get('suggestions', [])[:2]:
        print(f"  建议({sg['priority']}): {sg['action']}")
    
    # 5. 四医融合分析
    print("\n【步骤5】四医融合分析（症状：有点咳嗽、流鼻涕）：")
    medicine_report = bookboy.analyze_symptoms("有点咳嗽，流鼻涕，没发烧", "橙子")
    if medicine_report.get("must_see_doctor"):
        print(f"  ⚠️ {medicine_report['doctor_reason']}")
    else:
        tcm = medicine_report.get("tcm_analysis", {})
        if tcm.get("primary_pattern"):
            print(f"  中医辨证: {tcm['primary_pattern']['name']}")
        for sg in medicine_report.get("integrated_suggestions", [])[:2]:
            print(f"  [{sg['category']}] {sg['action']}")
    
    # 6. 文化传承
    print("\n【步骤6】文化传承种子：")
    seed = bookboy.get_culture_seed("橙子")
    print(f"  本周主题: {seed['theme']}")
    print(f"  核心概念: {seed['concept']}")
    print(f"  推荐活动: {seed['activity']}")
    
    # 7. 桥接器记录
    print("\n【步骤7】外部AI桥接器自动记录：")
    print("  运行桥接器，保存对话到记忆和陪伴日志...")
    os.system(
        f'cd {project_root / "03-引擎区"} && python3 -m 书童程序.核心.外部AI桥接器 '
        '--input "书童你好，今天可以给我讲个故事吗？" '
        '--response "当然可以，小橙子。今天给你讲一个关于大禹治水的故事..." '
        '--speaker child --child_id 小橙子 --no_voice'
    )
    
    print("\n" + "=" * 70)
    print("演示完成！")
    print("=" * 70)


if __name__ == "__main__":
    demo()
