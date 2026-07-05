#!/bin/bash
# 伴读书童AI · 核心文件解锁脚本
# 用途：临时解除核心 soul 文件的只读保护，便于师父修改
# 修改完成后，请运行 "锁定核心文件.command" 重新加锁

cd "$(dirname "$0")/.."

CORE_FILES=(
    "00-灵魂区/AGENTS.md"
    "00-灵魂区/WORKFLOW.md"
    "03-引擎区/书童程序/数据/提示词/系统提示词整合版_可运行.md"
    "03-引擎区/书童程序/数据/提示词/师父模式系统提示词.md"
)

echo "==================================="
echo "  伴读书童AI · 核心文件解锁"
echo "==================================="
echo ""
echo "请输入解锁密码："
read -s PASSWORD
echo ""

# 密码校验（请师父妥善保管此密码）
EXPECTED="s$Jikj$RsJTDax*r"
if [ "$PASSWORD" != "$EXPECTED" ]; then
    echo "❌ 密码错误，核心文件保持只读"
    exit 1
fi

echo "✅ 密码正确，正在解锁核心文件..."
for f in "${CORE_FILES[@]}"; do
    if [ -f "$f" ]; then
        chmod 666 "$f"
        echo "  已解锁: $f"
    else
        echo "  ⚠️  未找到: $f"
    fi
done

echo ""
echo "核心文件已解锁，现在可以修改。"
echo "修改完成后，请双击运行：锁定核心文件.command"
