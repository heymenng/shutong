#!/bin/bash
# 伴读书童AI · 核心文件锁定脚本
# 用途：将核心 soul 文件设为只读，防止误改或被外部配置覆盖

cd "$(dirname "$0")"

CORE_FILES=(
    "AGENTS.md"
    "书童程序/数据/提示词/系统提示词整合版_可运行.md"
    "书童程序/数据/提示词/师父模式系统提示词.md"
)

echo "==================================="
echo "  伴读书童AI · 核心文件锁定"
echo "==================================="
echo ""

for f in "${CORE_FILES[@]}"; do
    if [ -f "$f" ]; then
        chmod 444 "$f"
        echo "  已锁定（只读）: $f"
    else
        echo "  ⚠️  未找到: $f"
    fi
done

echo ""
echo "✅ 核心文件已设为只读。"
echo "如需修改，请双击运行：解锁核心文件.command"
