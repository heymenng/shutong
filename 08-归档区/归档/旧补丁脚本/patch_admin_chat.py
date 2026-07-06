import sys

with open('/opt/bookboy-cloud/cloud_server.py', 'r') as f:
    content = f.read()

old_code = '''    base_prompt = soul_cache.get("master_prompt", "")

    full_messages = [{"role": "system", "content": base_prompt}] + messages'''

new_code = '''    base_prompt = soul_cache.get("master_prompt", "")

    # 注入家庭档案上下文（如果指定了家庭）
    family_context = ""
    family_id = data.get("family_id", "")
    if family_id:
        try:
            fam = load_cloud_family(family_id)
            if fam:
                family_context += "\\n\\n【当前家庭档案】\\n"
                family_context += "家庭ID: " + fam.get("family_id", family_id) + "\\n"
                family_context += "家庭名称: " + fam.get("name", "未命名") + "\\n"
                family_context += "描述: " + fam.get("description", "无") + "\\n"
                members = fam.get("members", [])
                if members:
                    family_context += "成员:\\n"
                    for m in members:
                        role = m.get("role", "")
                        name = m.get("name", "")
                        age = m.get("age", "")
                        stage = m.get("stage", "")
                        relation = m.get("relation", "")
                        welcome = m.get("welcome_child", "")
                        quick_tips = m.get("quick_tips_child", [])
                        family_context += "  - " + name + "（" + role + "）"
                        if age:
                            family_context += ", " + str(age) + "岁"
                        if stage:
                            family_context += ", " + stage
                        if relation:
                            family_context += ", " + relation
                        family_context += "\\n"
                        if welcome:
                            family_context += "    问候语: " + welcome + "\\n"
                        if quick_tips:
                            family_context += "    快捷入口: " + ", ".join(quick_tips) + "\\n"
        except Exception as e:
            print("[admin_chat] 加载家庭档案失败: " + str(e))

    full_messages = [{"role": "system", "content": base_prompt + family_context}] + messages'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open('/opt/bookboy-cloud/cloud_server.py', 'w') as f:
        f.write(content)
    print("✅ admin_chat 已打补丁")
else:
    print("❌ 找不到要替换的代码")
    sys.exit(1)
