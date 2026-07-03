import sys

with open('/opt/bookboy-cloud/cloud_server.py', 'r') as f:
    content = f.read()

# 先找到并移除 admin_chat 内部错误插入的 _format_family_context 函数定义
# 以及被挤到函数定义后面的 full_messages 和 return 代码

marker_start = '    # 注入家庭档案上下文（师父可查所有家庭，AI 不许瞎猜）'
marker_end = '    full_messages = [{"role": "system", "content": base_prompt + family_context}] + messages'

# 检查当前错误结构
if 'def _format_family_context(fam, compact=False):' in content and 'def admin_chat():' in content:
    # 找到 admin_chat 函数体内的 _format_family_context 定义
    admin_chat_start = content.find('def admin_chat():')
    next_def = content.find('\ndef ', admin_chat_start + 1)
    
    # 提取 admin_chat 函数体
    admin_chat_body = content[admin_chat_start:next_def]
    
    # 在 admin_chat 体内找到 _format_family_context 定义
    inner_def_start = admin_chat_body.find('def _format_family_context(fam, compact=False):')
    if inner_def_start != -1:
        # 把 _format_family_context 提取出来，放到 admin_chat 外面
        inner_func = admin_chat_body[inner_def_start:]
        
        # 找到 inner_func 中 return ctx 之后的位置（函数结束）
        return_ctx_pos = inner_func.find('    return ctx\n\n')
        if return_ctx_pos != -1:
            func_end = return_ctx_pos + len('    return ctx\n\n')
            extracted_func = inner_func[:func_end]
            remaining = inner_func[func_end:]
            
            # remaining 应该包含 full_messages 和 return
            # 构建正确的 admin_chat 函数体
            clean_body = admin_chat_body[:inner_def_start] + remaining
            
            # 替换原来的 admin_chat 函数体
            content = content[:admin_chat_start] + clean_body + content[next_def:]
            
            # 在 admin_chat 函数定义之前插入提取出来的 _format_family_context
            insert_pos = content.find('def admin_chat():')
            content = content[:insert_pos] + extracted_func.replace('    def ', 'def ').replace('\n    ', '\n') + '\n' + content[insert_pos:]
            
            with open('/opt/bookboy-cloud/cloud_server.py', 'w') as f:
                f.write(content)
            print("✅ 代码结构已修复")
        else:
            print("❌ 找不到 return ctx")
            sys.exit(1)
    else:
        print("❌ 找不到内部函数定义")
        sys.exit(1)
else:
    print("⚠️ 代码结构可能已正确")
