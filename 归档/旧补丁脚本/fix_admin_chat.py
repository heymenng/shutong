with open('/opt/bookboy-cloud/cloud_server.py', 'r') as f:
    content = f.read()

# 找到错误的代码块并替换
old_part = '''    except Exception as e:
        print("[admin_chat] 加载家庭档案失败: " + str(e))

def _format_family_context(fam, compact=False):'''

new_part = '''    except Exception as e:
        print("[admin_chat] 加载家庭档案失败: " + str(e))

    full_messages = [{"role": "system", "content": base_prompt + family_context}] + messages

    start_time = time.time()
    try:
        reply = chat_completion(full_messages, backend=backend)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": f"模型调用失败: {str(e)}"}), 500

    cost_ms = int((time.time() - start_time) * 1000)
    log_admin("admin_chat", f"mode={mode}, messages={len(messages)}")

    return jsonify({
        "success": True,
        "reply": reply,
        "mode": mode,
        "soul_version": soul_cache.get("version"),
        "cost_ms": cost_ms,
    })


def _format_family_context(fam, compact=False):'''

if old_part in content:
    # 先截断：把 old_part 之后的所有内容（直到 admin_chat 结束）删掉，换上正确的结尾
    idx = content.find(old_part)
    # 找到 admin_chat 之后下一个顶层函数
    next_def = content.find('\n@app.route("/admin/soul"', idx)
    if next_def == -1:
        next_def = content.find('\ndef admin_get_soul', idx)
    
    # 构造正确内容
    fixed_content = content[:idx] + new_part + content[next_def:]
    
    with open('/opt/bookboy-cloud/cloud_server.py', 'w') as f:
        f.write(fixed_content)
    print("✅ admin_chat 已修复")
else:
    print("❌ 找不到目标代码")
