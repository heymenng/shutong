with open('/tmp/cloud_server_remote.py', 'r') as f:
    lines = f.readlines()

# 找到 _format_family_context 定义行
for i, line in enumerate(lines):
    if 'def _format_family_context(fam, compact=False):' in line:
        # 检查下一行是否是 @app.route
        if i + 1 < len(lines) and '@app.route' in lines[i + 1]:
            # 插入函数体
            func_body = '''    ctx = ""
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
    return ctx

'''
            lines.insert(i + 1, func_body)
            break

with open('/tmp/cloud_server_remote.py', 'w') as f:
    f.writelines(lines)

print("✅ 远程文件已修复")
