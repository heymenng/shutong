import sys

with open('/opt/bookboy-cloud/cloud_server.py', 'r') as f:
    content = f.read()

# 找到 admin_chat 里注入家庭档案的代码块，替换成支持全家庭查询的版本
old_block = '''    # 注入家庭档案上下文（如果指定了家庭）
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
            print("[admin_chat] 加载家庭档案失败: " + str(e))'''

new_block = '''    # 注入家庭档案上下文（师父可查所有家庭，AI 不许瞎猜）
    family_context = ""
    family_id = data.get("family_id", "")
    try:
        if family_id:
            # 指定了家庭，只注入该家庭
            fam = load_cloud_family(family_id)
            if fam:
                family_context = _format_family_context(fam)
        else:
            # 未指定家庭，注入所有家庭档案（师父有权查所有人）
            all_families = list_cloud_families()
            if all_families:
                family_context = "\\n\\n【系统内所有家庭档案】\\n"
                for fam_summary in all_families:
                    fid = fam_summary.get("family_id")
                    fam = load_cloud_family(fid)
                    if fam:
                        family_context += _format_family_context(fam, compact=True)
    except Exception as e:
        print("[admin_chat] 加载家庭档案失败: " + str(e))

def _format_family_context(fam, compact=False):
    ctx = ""
    fid = fam.get("family_id", "")
    name = fam.get("name", "未命名")
    desc = fam.get("description", "")
    members = fam.get("members", [])
    if compact:
        ctx += "--- " + name + "(" + fid + ") ---\\n"
    else:
        ctx += "\\n\\n【当前家庭档案】\\n"
        ctx += "家庭ID: " + fid + "\\n"
        ctx += "家庭名称: " + name + "\\n"
        if desc:
            ctx += "描述: " + desc + "\\n"
    if members:
        for m in members:
            role = m.get("role", "")
            mname = m.get("name", "")
            age = m.get("age", "")
            stage = m.get("stage", "")
            relation = m.get("relation", "")
            welcome = m.get("welcome_child", "")
            quick_tips = m.get("quick_tips_child", [])
            ctx += "  - " + mname + "（" + role + "）"
            if age:
                ctx += ", " + str(age) + "岁"
            if stage:
                ctx += ", " + stage
            if relation:
                ctx += ", " + relation
            ctx += "\\n"
            if welcome and not compact:
                ctx += "    问候语: " + welcome + "\\n"
            if quick_tips and not compact:
                ctx += "    快捷入口: " + ", ".join(quick_tips) + "\\n"
    return ctx'''

if old_block in content:
    content = content.replace(old_block, new_block)
    with open('/opt/bookboy-cloud/cloud_server.py', 'w') as f:
        f.write(content)
    print("✅ admin_chat 已更新为支持全家庭查询")
else:
    print("❌ 找不到要替换的代码块")
    sys.exit(1)
