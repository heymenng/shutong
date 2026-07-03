#!/bin/bash
# 语音通知小助手：用 Edge-TTS 播放简短通知，避免使用 say
# 用法: ./语音通知.sh "要播放的文字" [方言]
# 方言可选: 东北话|台湾话|粤语|陕西话|普通话，默认东北话

TEXT="$1"
DIALECT="${2:-东北话}"

if [ -z "$TEXT" ]; then
    echo "用法: ./语音通知.sh \"要播放的文字\" [方言]"
    exit 1
fi

case "$DIALECT" in
    东北话) VOICE="zh-CN-liaoning-XiaobeiNeural" ;;
    台湾话) VOICE="zh-TW-HsiaoChenNeural" ;;
    粤语) VOICE="zh-HK-HiuMaanNeural" ;;
    陕西话) VOICE="zh-CN-shaanxi-XiaoniNeural" ;;
    普通话|*) VOICE="zh-CN-XiaoxiaoNeural" ;;
esac

.venv/bin/python 工具脚本/语音播报.py --voice "$VOICE" "$TEXT"
