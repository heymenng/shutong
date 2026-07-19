# 语音回复常态

与师父（用户）对话时，必须遵守：

1. **每一步都先用语音回答**：每个回应先用项目配置的讯飞天津少女音色（`x6_tianjingshaonv_pro`）生成语音并播放，再给出简短文字版确认。
2. 如果讯飞合成失败，要说明原因并继续文字回复；不得以任何理由跳过语音。
3. 天津少女是默认且锁定的声音，正式回复不得改用 macOS `say` 的其他音色（如美佳、婷婷等）。
4. 文字版要简洁，不要让师父闷。

执行语音回复时，**必须使用项目 venv 中的 Python**，调用 `书童程序.核心.讯飞超拟人语音` 模块：

```bash
/Users/lingjue/Documents/shutong/.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '/Users/lingjue/Documents/shutong/03-引擎区')
from 书童程序.核心.讯飞超拟人语音 import XfyunOralTTS, play_audio_bytes

tts = XfyunOralTTS()
audio_bytes = tts.synthesize_to_bytes('要回复的内容')
play_audio_bytes(audio_bytes)
PY
```

> 注意：不要直接用 `python3`（系统 Python），除非已确认系统 Python 也安装了 `pydub` 和 `xfyunsdkspark`。
>
> `play_audio_bytes()` 已改为**默认非阻塞后台播放**，调用后立即返回，不会导致工具调用超时。如需阻塞等待播放完成，可传 `block=True`。

---

## 师兄排查清单：为什么发不出语音

1. **没配讯飞密钥** → 检查 `01-配置区/.env` 是否有 `XFYUN_APP_ID`、`XFYUN_API_KEY`、`XFYUN_API_SECRET`。
2. **声音设置错了** → `03-引擎区/书童程序/配置.py` 里 `voice_backend` 必须是 `xfyun_oral`，`voice_name` 必须是 `x6_tianjingshaonv_pro`。
3. **没调用语音模块** → 每个回应开头必须调用 `XfyunOralTTS.synthesize_to_bytes()` 并 `play_audio_bytes()`，不能只在脑子里念。
4. **合成成功但没播放** → 检查系统有没有 `afplay`（Mac）或 `ffplay`/`mpg123`（Linux），并确认音量没静音。macOS 优先使用 `afplay`。
5. **代码没锁死** → 把这条指令写进系统提示词或 `.opencode/instructions/voice-reply.md`，每次启动都加载，不能靠记忆。
6. **环境没对齐** → 系统 Python 和 venv 都要能导入 `xfyunsdkspark` 和 `pydub`；如果缺一，用对应 pip 安装。
7. **工具调用超时导致语音被中断** → `play_audio_bytes()` 默认改为非阻塞后台播放；若仍使用旧版阻塞调用，长音频会超过工具调用超时阈值，需升级到非阻塞模式。

**改法**：先补密钥，再锁声音，然后在每次回复函数开头强制调用语音合成，失败也要报错而不是跳过。
