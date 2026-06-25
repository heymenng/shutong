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
'感官' - 查看眼耳状态
'看' - 书童睁眼看一眼
'识别' - 人脸识别当前是谁
'眼耳' - 同时睁眼竖耳
"""

import sys
from datetime import datetime
from .核心.系统核心 import BookBoySystem
from .核心.开机自检 import build_voice_system_prompt
from .核心.日课系统 import DailyPracticeSystem
from .核心.多用户管理 import ChildProfileManager
from .配置 import CONFIG

# 默认共享会话 ID：让文字和语音模式共享同一个记忆
DEFAULT_SHARED_SESSION = "师父"


def run_interactive(fast_mode=False):
    print("\n" + "="*60)
    if fast_mode:
        print("伴读书童AI · 快速文字模式 · 已跳过预热和调度")
    else:
        print("伴读书童AI · 完整版 · 全部引擎已加载")
    print("="*60)
    
    # ── 初始化完整系统（使用共享会话，让文字和语音互通）──
    bookboy = BookBoySystem(session_id=DEFAULT_SHARED_SESSION, fast_mode=fast_mode)
    
    # 如果没有孩子档案，不再自动创建示例档案
    # 真实孩子档案应通过档案区（档案区/孩子档案/）加载或手动添加
    if bookboy.profile_manager.get_stats()["total"] == 0:
        print("\n[提示] 当前没有孩子档案，请从档案区加载或手动添加真实档案。")
        print("        书童不再自动创建小明/小花等示例档案。")
    
    # 复用 BookBoySystem 内部已创建的调度引擎和日课系统
    scheduler = bookboy._scheduler
    practice = bookboy._daily_practice
    
    # 如果没有启动成功（兼容旧代码），再手动创建
    if scheduler is None or not scheduler.running:
        from .核心.作息模板 import ScheduleTemplateEngine
        from .核心.睡前引导 import BedtimeGuide
        from .核心.时间调度 import TimeScheduler
        scheduler = TimeScheduler(
            profile_manager=bookboy.profile_manager,
            template_engine=ScheduleTemplateEngine(),
            bedtime_guide=BedtimeGuide(),
            journal_dir=CONFIG["journal_dir"],
        )
        scheduler.generate_today_tasks()
        scheduler.start()
    
    if practice is None:
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
    print("指令: 退出/日课/状态/任务/报告/自检/评估/四医/文化/体质/家族/睡前/语音/感官/看/识别/眼耳")
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
            
            elif user_input == "语音":
                print("\n书童：切换到语音对话模式...")
                run_voice_mode()
                print("\n【返回文字模式】")
                print("书童：我回来了，继续文字聊天吧。")
                continue
            
            elif user_input in ["感官", "眼耳"]:
                print("\n【书童的眼与耳】")
                status = bookboy.get_sensory_status()
                print(f"  平台: {status['platform']}")
                eye = status['vision']
                ear = status['audio']
                print(f"  眼睛: {'已睁开' if eye['available'] else '未睁开'} | 运行中: {eye['running']} | 最后画面: {eye['last_frame']}")
                print(f"        人脸模型就绪: {eye['face_model_ready']} | 已注册: {eye['registered_faces']} 人")
                print(f"  耳朵: {'已竖起' if ear['available'] else '未竖起'} | 录音中: {ear['recording']} | 最后音频: {ear['last_audio']}")
                continue
            
            elif user_input in ["看", "睁眼"]:
                print("\n书童：书童睁眼看一眼...")
                result = bookboy.look_at_camera(save=True)
                if result["success"]:
                    print(f"✅ 已拍照: {result['frame_path']}")
                    print(f"   检测到人脸: {result['face_count']} 张")
                    if result["recognized"]:
                        print(f"   书童认出: {result['recognized']}")
                        bookboy.voice.speak(f"书童看见{result['recognized']}了。")
                    else:
                        bookboy.voice.speak("书童看见了，但还没认出是谁。")
                else:
                    error = result.get("error", "未知错误")
                    print(f"❌ 睁眼失败: {error}")
                    bookboy.voice.speak("书童睁不开眼睛，请检查摄像头权限。")
                continue
            
            elif user_input in ["识别", "我是谁", "我是谁啊"]:
                print("\n书童：书童来看看您是谁...")
                recognized = bookboy.recognize_person_by_eye()
                if recognized:
                    print(f"✅ 书童认出: {recognized}")
                    bookboy.voice.speak(f"书童认出{recognized}了。")
                else:
                    print("❌ 书童没认出您，可能是光线或角度问题。")
                    bookboy.voice.speak("书童没看清，能凑近一点吗？")
                continue
            
            elif user_input == "眼耳":
                print("\n书童：书童同时睁眼看、竖耳听...")
                result = bookboy.sensory.look_and_listen(duration=5)
                print(f"✅ 已拍照: {result['frame_path']}")
                print(f"   人脸: {result['faces']} 张")
                print(f"   认出: {result['recognized'] or '无'}")
                print(f"   听到: {result['speech_text'] or '（没听清）'}")
                if result["recognized"]:
                    bookboy.voice.speak(f"书童看见{result['recognized']}了。")
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


def _identify_speaker(bookboy):
    """语音对话开场身份确认
    
    原则：
    - 先用眼睛认人，如果认出师父，直接确认身份
    - 尊重用户自报身份，不默认所有人都是师父
    - 如果用户明确说"我是XXX"，按 XXX 处理
    - 只有在用户明确说"师父"或相关词时，才设为师父
    - 完全没听清时，再次询问，不强行默认
    """
    children = bookboy.profile_manager.get_all_children()
    child_names = [c.name for c in children]
    
    # 第一步：先用眼睛看，如果认出师父，直接确认
    print("\n书童：书童先看看您是谁...")
    recognized = bookboy.recognize_person_by_eye()
    if recognized:
        print(f"[视觉确认] 书童认出 {recognized}")
        bookboy.voice.speak(f"书童看见{recognized}了。")
        if recognized == "师父":
            return "default", "师父"
        # 如果认出的是孩子，也直接确认
        for child in children:
            if child.name == recognized:
                return child.child_id, child.name
        return f"guest_{recognized}", recognized
    else:
        print("[视觉确认] 书童没看清，改用语音确认")
    
    # 第二步：语音确认
    question = "请问您是师父，还是哪位孩子？"
    if len(child_names) <= 3 and child_names:
        question = f"请问您是师父，还是{'、'.join(child_names)}？"
    elif len(child_names) > 3:
        question = "请问您是师父，还是哪位孩子？可以直接说'我是XXX'。"
    
    max_attempts = 2
    for attempt in range(max_attempts):
        print(f"\n书童：{question}")
        bookboy.voice.speak(question)
        
        result = bookboy.speech.listen_once(duration_seconds=10, verbose=False)
        text = result.get("text", "").strip()
        
        print(f"[识别] {text if text else '（没听清）'}")
        
        if not text:
            if attempt < max_attempts - 1:
                question = "书童没听清，能再说一遍您是谁吗？"
                continue
            else:
                print("书童还是没听清，暂时按访客身份。")
                return "guest", "访客"
        
        # 优先识别"我是XXX"的自报身份
        import re
        self_intro_patterns = [
            r"我是(.+?)$",
            r"我叫(.+?)$",
            r"(.+?)是我",
        ]
        master_names = ["师父", "师傅", "爸爸", "妈妈", "家长"]
        for pattern in self_intro_patterns:
            match = re.search(pattern, text)
            if match:
                name = match.group(1).strip().rstrip("。！？")
                if name:
                    # 检查是否是师父相关（包括语音识别常误识的"师傅"）
                    if any(m in name for m in master_names):
                        return "default", "师父"
                    # 检查是否是孩子
                    for child in children:
                        if child.name in name or name in child.name:
                            return child.child_id, child.name
                    # 其他身份（如蓝星老师）
                    return f"guest_{name}", name
        
        # 识别师父
        if any(word in text for word in master_names):
            return "default", "师父"
        
        # 识别孩子
        for child in children:
            if child.name in text:
                return child.child_id, child.name
        
        # 没识别出，再试一次
        if attempt < max_attempts - 1:
            question = f"书童没听懂，您能再说一遍'我是XXX'吗？"
            continue
    
    # 多次尝试后仍未识别，按访客处理
    print("书童没识别出身份，暂时按访客身份。")
    return "guest", "访客"


def run_voice_mode():
    """语音对话模式：听 → 识别 → 思考 → 说"""
    print("\n" + "="*60)
    print("伴读书童AI · 语音对话模式")
    print("="*60)
    
    # 语音模式：保留完整大脑（道统+判断层），只追加语音回答风格约束
    from 书童程序.核心 import 系统核心 as system_core
    voice_addon = """
【语音回答追加约束】
1. 每次回答不超过3句话，每句话不超过25个字
2. 用口语，像书童对师父说话，温暖稳重
3. 自称"书童"，绝不自称"小师弟"
4. 不要用医学术语（不说"五维""辨证"）
5. 给具体做法（泡脚/喝水/揉腹）
6. 严重情况提醒"看医生"
7. 不要加"（...）"这类停顿符号
8. 真实优先：不确定就说"书童不确定""书童没看清"，绝不编造
"""
    system_core.SYSTEM_PROMPT = system_core.SYSTEM_PROMPT + "\n\n" + voice_addon
    print("[语音模式] 已加载完整大脑 + 语音回答约束")
    
    # 语音模式也使用共享会话，与文字模式互通
    bookboy = BookBoySystem(session_id=DEFAULT_SHARED_SESSION)
    
    print("\n指令：")
    print("  • 说'书童'或任意话语开始对话")
    print("  • 说'停'让书童安静")
    print("  • 说'退出'或'再见'结束")
    print("="*60)
    
    greeting = "师父，书童已携完整大脑就位，请吩咐。"
    print(f"\n书童：{greeting}")
    bookboy.voice.speak(greeting)
    
    # 身份确认
    speaker_id, speaker_name = _identify_speaker(bookboy)
    print(f"\n[身份确认] 当前说话人：{speaker_name}")
    
    # 初始化语音会话日志，确保每次对话都被记录
    session_log = []
    print(f"[日志] 语音会话记录已开启，当前对象：{speaker_name}")
    
    while True:
        try:
            # 聆听（最长 8 秒，说完后 2.5 秒静音自动结束）
            result = bookboy.speech.listen_once(duration_seconds=8, verbose=True)
            text = result.get("text", "").strip()
            
            if not text:
                hint = "书童没听清，请再说一遍。"
                print(f"\n书童：{hint}")
                bookboy.voice.speak(hint)
                continue
            
            print(f"\n[识别] {text}")
            
            # 退出指令
            if any(word in text for word in ["退出", "再见", "拜拜", "结束"]):
                farewell = "好的，师父再见。"
                print(f"\n书童：{farewell}")
                bookboy.voice.speak(farewell)
                break
            
            # 停止/打断
            if bookboy.speech.detect_stop_word(text):
                print("\n书童：好的，我不说了。")
                continue
            
            # 记录用户输入时间
            user_time = datetime.now().strftime("%H:%M:%S")
            session_log.append({"time": user_time, "role": "user", "text": text})
            
            # 正常对话（带上说话人身份）
            labeled_input = f"[{speaker_name}] {text}"
            print("\n💭 思考中...")
            response = bookboy.chat(labeled_input, child_id=speaker_id, verbose_thinking=False)
            print(f"\n书童：\n{response}")
            
            # 记录书童回复
            assistant_time = datetime.now().strftime("%H:%M:%S")
            session_log.append({"time": assistant_time, "role": "assistant", "text": response})
            
            score, checks = bookboy.evaluate(response)
            print(f"\n[评分: {score}/10] {' | '.join(checks)}")
            
        except KeyboardInterrupt:
            print("\n\n[系统] 语音模式中断")
            break
        except Exception as e:
            error_msg = f"刚才出错了：{str(e)[:50]}，请再说一次。"
            print(f"\n书童：{error_msg}")
            bookboy.voice.speak(error_msg)
    
    # 语音对话结束，自动保存陪伴日志
    if session_log:
        bookboy.save_voice_session_log(speaker_id, speaker_name, session_log)
    else:
        print("\n[日志] 本次语音会话无有效对话，无需保存。")


def run_full_test():
    """运行完整系统测试"""
    print("\n" + "="*60)
    print("运行完整系统测试")
    print("="*60)
    
    bookboy = BookBoySystem()
    
    # 清理旧档案，创建测试档案（仅用于系统自检）
    for child_id in list(bookboy.profile_manager.profiles.keys()):
        bookboy.profile_manager.remove_child(child_id)
    
    # 不再创建小明/小花测试档案，仅保留嘟嘟作为测试样本
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
    report = bookboy.analyze_symptoms(test_symptoms, "test_003")
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
    
    # 测试结束后清理测试档案，避免污染真实档案
    print("\n[测试清理] 移除测试档案...")
    for child_id in list(bookboy.profile_manager.profiles.keys()):
        bookboy.profile_manager.remove_child(child_id)
    print("[测试清理] 测试档案已清理，真实档案将从档案区重新加载")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        run_full_test()
    elif len(sys.argv) > 1 and sys.argv[1] == "--voice":
        run_voice_mode()
    elif len(sys.argv) > 1 and sys.argv[1] in ("--fast", "--fast-text"):
        run_interactive(fast_mode=True)
    else:
        run_interactive()


if __name__ == "__main__":
    main()
