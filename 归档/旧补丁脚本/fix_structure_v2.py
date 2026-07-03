import re

with open('/opt/bookboy-cloud/cloud_server.py', 'r') as f:
    content = f.read()

# 找到 admin_chat 函数
admin_chat_match = re.search(r'(@app\.route\("/admin/chat".*?\n)(def admin_chat\(\):)', content, re.DOTALL)
if not admin_chat_match:
    print("❌ 找不到 admin_chat")
    exit(1)

# 找到 admin_chat 函数的开始位置
func_start = admin_chat_match.start(2)

# 找到下一个顶层函数定义（以 \ndef 开头，前面没有额外缩进）
next_func = re.search(r'\n(@app\.route|def [a-zA-Z_])', content[func_start+1:])
if next_func:
    func_end = func_start + 1 + next_func.start()
else:
    func_end = len(content)

func_body = content[func_start:func_end]

# 检查是否有内部嵌套的 _format_family_context
if 'def _format_family_context(fam, compact=False):' not in func_body:
    print("✅ 代码结构已经正确")
    exit(0)

# 提取内部的 _format_family_context 函数
inner_match = re.search(r'(    def _format_family_context\(fam, compact=False\):.*?)\n    full_messages = ', func_body, re.DOTALL)
if not inner_match:
    print("❌ 无法提取内部函数")
    exit(1)

inner_func = inner_match.group(1)
remaining = func_body[inner_match.end()-len('\n    full_messages = '):]

# 构建清理后的 admin_chat 函数体
clean_body = func_body[:inner_match.start()] + remaining

# 将提取的函数转换为模块级别（去掉一级缩进）
module_level_func = '\n'.join(line[4:] if line.startswith('    ') else line for line in inner_func.split('\n'))

# 替换内容
new_content = content[:func_start] + clean_body + content[func_end:]

# 在 admin_chat 之前插入模块级函数
insert_pos = new_content.find('@app.route("/admin/chat"')
new_content = new_content[:insert_pos] + module_level_func + '\n\n' + new_content[insert_pos:]

with open('/opt/bookboy-cloud/cloud_server.py', 'w') as f:
    f.write(new_content)

print("✅ 代码结构已修复")
