#!/bin/bash
# 设置书童头像
# 使用方法：双击这个文件，选择宝宝照片，书童头像就换好了

cd "$(dirname "$0")"

echo "============================================================"
echo "  设置书童头像"
echo "============================================================"
echo ""
echo "请在选择窗口中点击宝宝照片，然后按"打开"。"
echo ""

# 弹出 Mac 文件选择对话框
FILE=$(osascript -e 'POSIX path of (choose file with prompt "请选择宝宝照片作为书童头像" of type {"public.image"})')

if [ -z "$FILE" ]; then
    echo "您没有选照片，书童头像不变。"
    read -n 1 -s -r -p "按任意键关闭..."
    exit 1
fi

echo "您选择的文件: $FILE"

# 复制到书童头像位置
cp "$FILE" "本地书童头像.jpg"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ 书童头像已设置成功！"
    echo ""
    echo "现在请刷新浏览器里的书童界面："
    echo "  http://127.0.0.1:3876"
    echo ""
else
    echo ""
    echo "❌ 设置失败，请重试。"
fi

read -n 1 -s -r -p "按任意键关闭..."
