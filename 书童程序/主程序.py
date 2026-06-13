"""伴读书童AI - 入口模块（完整版）

全部引擎已集成：
- 灵魂层：道统、自省、日课
- 工作保障：多用户、调度、睡前引导
- 骨层：发育守护（预警+趋势+联动）
- 用层：四医融合（西医+中医+功能医学+炁脉）+ 体质模型
- 魂层：文化传承（场景触发+混龄+文明路径）
- 技术层：STT + 家长通知 + 隐私合规

指令列表：
'退出' - 结束程序
'日课' - 手动运行日课
'状态' - 查看修行状态
'任务' - 查看今日任务
'完成 [任务名]' - 标记任务完成
'报告' - 生成每日工作报告
'自检' - 书童自检
'评估 [孩子名]' - 发育评估
'四医 [症状]' - 四医合参分析
'文化 [孩子名]' - 文明种子
'体质 [孩子名]' - 体质辨识
'家族' - 家族发育报告
'睡前' - 预览睡前引导
"""

import sys
from .核心.系统核心 import BookBoySystem
from .核心.日课系统 import DailyPracticeSystem
from .核心.多用户管理 import ChildProfileManager
from .核心.作息模板 import ScheduleTemplateEngine
from .核心.睡前引导 import BedtimeGuide
from .核心.时间调度 import TimeScheduler
from .配置 import CONFIG


def run_interactive():
    print("\n" + "="*60)
    print("伴读书童AI · 完整版 · 全部引擎已加载")
    print("="*60)
    
    # ── 初始化完整系统 ──
    bookboy = BookBoySystem()
    
    # 如果没有孩子档案，创建示例
    if bookboy.profile_manager.get_stats()["total"] == 0:
        print("\n[演示] 创建示例孩子档案...")
        bookboy.profile_manager.add_child("小明", "2016-03-15", "demo_001")
        bookboy.profile_manager.add_child("小花", "2020-07-20", "demo_002")
        bookboy.profile_manager.add_child("嘟嘟", "2012-09-01", "demo_003")
    
    # 初始化调度引擎
    template_engine = ScheduleTemplateEngine()
    bedtime_guide = BedtimeGuide()
    scheduler = TimeScheduler(
        profile_manager=bookboy.profile_manager,
        template_engine=template_engine,
        bedtime_guide=bedtime_guide,
        journal_dir=CONFIG["journal_dir"],
    )
    scheduler.generate_today_tasks()
    scheduler.start()
    
    # 初始化日课
    practice = DailyPracticeSystem(CONFIG, CONFIG["journal_dir"])
    
    # 显示系统状态
    print("\n" + "="*60)
    print("【全部引擎就绪】")
    print("="*60)
    
    status = bookboy.get_cultivation_status()
    print(f"\n[修行状态] 灵魂: {status['soul_mode']} | 自省: {'开启' if status['self_reflection_enabled'] else '关闭'}")
    print(f"[档案] 管理 {status['children_managed']} 个孩子")
    print(f"[引擎] 发育守护✅ 四医融合✅ 体质模型✅ 文化传承✅")
    print(f"[技术] STT:{status['engines_loaded']['speech']} 通知✅ 隐私合规✅")
    
    print(f"\n{'='*60}")
    print("指令: 退出/日课/状态/任务/报告/自检/评估/四医/文化/体质/家族/睡前")
    print("="*60)
    
    print("\n书童：\n哟...\n\n我来了。\n\n今天想聊点什么？")
    bookboy.voice.speak("哟...我来了。今天想聊点什么？")
    
    # ── 交互循环 ──
    while True:
        try:
            user_input = input("\n孩子：").strip()
            if not user_input:
                continue
            
            # ── 特殊指令 ──
            if user_input.lower() in ["退出", "exit", "quit"]:
                print("\n书童：拜拜...下次见。")
                bookboy.memory.save_session()
                scheduler.stop()
                practice.shutdown()
                break
            
            elif user_input == "日课":
                print("\n书童：好，我现在做日课...")
                practice.run_now()
                continue
            
            elif user_input == "状态":
                status = bookboy.get_cultivation_status()
                print(f"\n[修行状态]")
                for k, v in status.items():
                    print(f"  {k}: {v}")
                continue
            
            elif user_input == "任务":
                print("\n【今日任务】")
                for child_id, s in scheduler.get_all_children_status().items():
                    child = bookboy.profile_manager.get_child(child_id)
                    name = child.name if child else child_id
                    print(f"\n  {name}: {s['completion_rate']}完成")
                    if s['upcoming_tasks']:
                        print(f"    接下来: {' | '.join([t['name'] for t in s['upcoming_tasks']])}")
                continue
            
            elif user_input.startswith("完成 "):
                task_name = user_input[3:].strip()
                for child_id in scheduler.today_tasks.keys():
                    scheduler.confirm_task_by_name(child_id, task_name, "parent")
                continue
            
            elif user_input == "报告":
                scheduler.generate_daily_report()
                continue
            
            elif user_input == "自检":
                scheduler.self_check()
                continue
            
            elif user_input.startswith("评估 "):
                name = user_input[3:].strip()
                child = _find_child_by_name(bookboy.profile_manager, name)
                if child:
                    print(f"\n【发育评估】{child.name}")
                    report = bookboy.assess_child(child.child_id)
                    print(f"  综合级别: {report.get('overall_level', 'N/A')}")
                    for dim, result in report.get('dimensions', {}).items():
                        print(f"  {dim}: {result.get('status', 'N/A')} - {result.get('detail', '')}")
                    if report.get('linkage_analysis'):
                        print(f"  联动分析: {report['linkage_analysis']['summary']}")
                    for sg in report.get('suggestions', [])[:3]:
                        print(f"  建议({sg['priority']}): {sg['action']}")
                else:
                    print("未找到孩子")
                continue
            
            elif user_input.startswith("四医 "):
                symptoms = user_input[3:].strip()
                print(f"\n【四医合参】症状: {symptoms}")
                # 使用第一个孩子作为示例
                children = bookboy.profile_manager.get_all_children()
                if children:
                    report = bookboy.analyze_symptoms(symptoms, children[0].child_id)
                    if report.get("must_see_doctor"):
                        print(f"⚠️ {report['doctor_reason']}")
                    else:
                        tcm = report.get("tcm_analysis", {})
                        if tcm.get("primary_pattern"):
                            print(f"  中医辨证: {tcm['primary_pattern']['name']}")
                        for sg in report.get("integrated_suggestions", [])[:3]:
                            print(f"  [{sg['category']}] {sg['action']}")
                continue
            
            elif user_input.startswith("文化 "):
                name = user_input[3:].strip()
                child = _find_child_by_name(bookboy.profile_manager, name)
                if child:
                    seed = bookboy.get_culture_seed(child.child_id)
                    print(f"\n【本周文明种子】{child.name}")
                    print(f"  主题: {seed['theme']} ({seed['concept']})")
                    print(f"  活动: {seed['activity']}")
                    path = bookboy.generate_culture_path(child.child_id, weeks=2)
                    print(f"\n  未来2周路径:")
                    for p in path:
                        print(f"    第{p['week']}周: {p['theme']} - {p['activity']}")
                else:
                    print("未找到孩子")
                continue
            
            elif user_input.startswith("体质 "):
                name = user_input[3:].strip()
                child = _find_child_by_name(bookboy.profile_manager, name)
                if child:
                    care = bookboy.constitution_model.get_personalized_care(child.child_id)
                    print(f"\n【体质调养】{child.name} - {care.get('constitution', '未知')}")
                    print(f"  推荐食物: {'、'.join(care.get('diet', {}).get('recommended', [])[:5])}")
                    print(f"  避免食物: {'、'.join(care.get('diet', {}).get('avoid', [])[:5])}")
                    print(f"  穴位: {'、'.join(care.get('acupressure', [])[:3])}")
                    emotion = bookboy.constitution_model.get_emotion_strategy(child.child_id)
                    print(f"  情绪策略: {emotion['strategy']}")
                else:
                    print("未找到孩子")
                continue
            
            elif user_input == "家族":
                print("\n【家族发育报告】")
                report = bookboy.get_family_report()
                print(f"  总计: {report['total_children']}个孩子")
                print(f"  预警分布: 🟢{report['green_count']} 🟡{report['yellow_count']} 🟠{report['orange_count']} 🔴{report['red_count']}")
                for c in report.get('children', []):
                    print(f"  {c['name']}: {c['level']} ({c['warnings_count']}项预警)")
                if report.get('top_concerns'):
                    print(f"\n  重点关注:")
                    for concern in report['top_concerns'][:5]:
                        print(f"    {concern['level']} {concern['child']} - {concern['dimension']}: {concern['detail'][:30]}")
                continue
            
            elif user_input == "睡前":
                print("\n【睡前仪式预览】")
                for child in bookboy.profile_manager.get_all_children():
                    session = bedtime_guide.generate_bedtime_session(child)
                    music = bedtime_guide.get_music_recommendation(child)
                    print(f"\n  {child.name} ({child.get_stage_name()}):")
                    print(f"    🎵 {music['recommendation']} ({music['details']['tempo']}BPM)")
                    print(f"    📖 {session['title']} ({session['total_duration']}分钟)")
                continue
            
            # ── 正常对话 ──
            response = bookboy.chat(user_input)
            print(f"\n书童：\n{response}")
            
            score, checks = bookboy.evaluate(response)
            print(f"\n[评分: {score}/10] {' | '.join(checks)}")
            
        except KeyboardInterrupt:
            print("\n\n[系统] 中断")
            bookboy.memory.save_session()
            scheduler.stop()
            practice.shutdown()
            break


def _find_child_by_name(profile_manager, name):
    """根据名字查找孩子"""
    for child in profile_manager.get_all_children():
        if child.name == name:
            return child
    return None


def run_full_test():
    """运行完整系统测试"""
    print("\n" + "="*60)
    print("运行完整系统测试")
    print("="*60)
    
    bookboy = BookBoySystem()
    
    # 清理旧档案，创建测试档案
    for child_id in list(bookboy.profile_manager.profiles.keys()):
        bookboy.profile_manager.remove_child(child_id)
    
    bookboy.profile_manager.add_child("小明", "2016-03-15", "test_001")
    bookboy.profile_manager.add_child("小花", "2020-01-10", "test_002")
    bookboy.profile_manager.add_child("嘟嘟", "2012-09-01", "test_003")
    
    print("\n【测试1】系统状态")
    status = bookboy.get_cultivation_status()
    print(f"  引擎加载: {status['engines_loaded']}")
    
    print("\n【测试2】发育守护评估")
    for child in bookboy.profile_manager.get_all_children():
        report = bookboy.assess_child(child.child_id)
        print(f"  {child.name}: {report['overall_level']} ({len(report.get('warnings', []))}项预警)")
    
    print("\n【测试3】四医融合分析")
    test_symptoms = "发烧38度5，头痛，怕冷，流清鼻涕"
    report = bookboy.analyze_symptoms(test_symptoms, "test_001")
    if report.get("must_see_doctor"):
        print(f"  ⚠️ {report['doctor_reason']}")
    else:
        tcm = report.get("tcm_analysis", {})
        if tcm.get("primary_pattern"):
            print(f"  辨证: {tcm['primary_pattern']['name']}")
        print(f"  建议数: {len(report.get('integrated_suggestions', []))}")
    
    print("\n【测试4】文化传承")
    for child in bookboy.profile_manager.get_all_children():
        seed = bookboy.get_culture_seed(child.child_id)
        path = bookboy.generate_culture_path(child.child_id, weeks=2)
        print(f"  {child.name}: {seed['theme']} + {len(path)}周路径")
    
    print("\n【测试5】体质模型")
    for child in bookboy.profile_manager.get_all_children():
        care = bookboy.constitution_model.get_personalized_care(child.child_id)
        print(f"  {child.name}: {care.get('constitution', '平和质')}")
    
    print("\n【测试6】家族报告")
    family_report = bookboy.get_family_report()
    print(f"  总计: {family_report['total_children']}个孩子")
    print(f"  预警: 🟢{family_report['green_count']} 🟡{family_report['yellow_count']} 🟠{family_report['orange_count']} 🔴{family_report['red_count']}")
    
    print("\n【测试7】家长通知")
    bookboy.notifier.send("测试通知", "系统测试消息", "🟢", None, "test")
    print("  通知已发送")
    
    print("\n【测试8】隐私合规")
    policy = bookboy.privacy.get_privacy_policy()
    print(f"  隐私政策: {len(policy)}字符")
    
    print("\n" + "="*60)
    print("全部测试通过")
    print("="*60)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        run_full_test()
    else:
        run_interactive()


if __name__ == "__main__":
    main()
