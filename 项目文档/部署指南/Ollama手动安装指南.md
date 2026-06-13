# 伴读书童AI·Ollama手动安装指南

> **用途**：安装本地AI模型，让书童真正"智能"起来  
> **适用系统**：macOS（Intel/Apple Silicon）  
> **预计时间**：安装2分钟 + 下载模型10-30分钟  
> **所需空间**：约5GB（Ollama程序200MB + 模型4GB）  
> **编写者**：灵觉/Prome  
> **日期**：2026年5月29日  

---

## 📋 安装前检查

### 检查1：系统版本
```bash
sw_vers
```
**要求**：macOS 11 (Big Sur) 或更高版本

### 检查2：磁盘空间
```bash
df -h /
```
**要求**：剩余空间 ≥ 10GB

### 检查3：网络连接
```bash
ping -c 3 ollama.com
```
**要求**：能连通 ollama.com

---

## 🚀 安装步骤（3步走）

### 第一步：下载Ollama安装包

**方法一：浏览器下载（推荐）**
1. 打开浏览器，访问：https://ollama.com/download
2. 点击 **"Download for macOS"** 按钮
3. 等待下载完成（约200MB，文件名类似 `Ollama-darwin.zip`）

**方法二：命令行下载**
```bash
# 如果网络好，可以直接下载
curl -L -o ~/Downloads/Ollama-darwin.zip "https://ollama.com/download/Ollama-darwin.zip"
```

---

### 第二步：安装Ollama

**图形界面安装：**
1. 双击下载的 `Ollama-darwin.zip` 解压
2. 双击解压后的 `Ollama.app`
3. 按照提示完成安装
4. 首次打开可能会提示"来自不明开发者"，去 **系统设置 → 隐私与安全** 点击"仍要打开"

**命令行安装（高级）：**
```bash
# 解压
unzip ~/Downloads/Ollama-darwin.zip -d /Applications/

# 添加到命令行路径（重要！）
echo 'export PATH="/Applications/Ollama.app/Contents/Resources:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

---

### 第三步：验证安装

打开终端，运行：
```bash
ollama --version
```

**预期输出：**
```
ollama version 0.1.x
```

如果显示版本号，说明安装成功 ✅

---

## 📥 第四步：下载中文模型（关键！）

### 下载模型

在终端运行：
```bash
# 下载Qwen2.5-7B模型（约4GB，需要10-30分钟）
ollama pull qwen2.5:7b
```

**下载过程：**
```
downloading qwen2.5:7b...
[====================> ]  3.8GB/4.0GB  95%  2MB/s   剩余2分钟
```

### 验证模型

```bash
# 测试模型是否能正常对话
ollama run qwen2.5:7b
```

输入测试：
```
>>> 你好
```

如果模型回复中文，说明一切正常 ✅

退出测试：
```
/bye
```

---

## 🔌 第五步：启动Ollama服务

### 方式1：图形界面启动（推荐）
1. 打开 **启动台** → 找到 **Ollama**
2. 点击图标启动
3. 菜单栏会出现Ollama图标（像一只羊驼 🦙）

### 方式2：命令行启动
```bash
# 后台启动服务
ollama serve &
```

### 验证服务是否运行
```bash
# 检查服务状态
curl http://localhost:11434/api/tags
```

**预期输出（JSON格式）：**
```json
{"models":[{"name":"qwen2.5:7b","model":"qwen2.5:7b","size":4683075271}]}
```

---

## 🎮 第六步：运行书童AI

### 切换后端配置

打开书童配置文件：
```bash
# 找到这一行，从 "simulation" 改成 "ollama"
# 在 bookboy_main.py 第19行左右
```

或者直接在终端运行：
```bash
cd /Users/liuqingyuan/Documents/shutong/伴读书童AI训练素材库

# 运行书童（自动检测Ollama）
python3 bookboy_main.py
```

### 如果自动检测失败，手动指定后端

```bash
# 在运行前设置环境变量
export BOOKBOY_BACKEND="ollama"
python3 bookboy_main.py
```

---

## ✅ 安装成功验证清单

| 检查项 | 命令 | 预期结果 |
|--------|------|---------|
| Ollama安装 | `ollama --version` | 显示版本号 |
| 模型下载 | `ollama list` | 显示 `qwen2.5:7b` |
| 服务运行 | `curl http://localhost:11434/api/tags` | 返回JSON |
| 书童运行 | `python3 bookboy_main.py` | 显示"使用Ollama本地模型" |

**全部通过 = 安装成功 🎉**

---

## ❌ 常见问题解决

### 问题1：ollama命令找不到

**现象**：
```bash
$ ollama --version
zsh: command not found: ollama
```

**解决**：
```bash
# 找到Ollama安装位置
ls /Applications/Ollama.app/Contents/Resources/ollama

# 添加到PATH
echo 'export PATH="/Applications/Ollama.app/Contents/Resources:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

---

### 问题2：模型下载太慢/失败

**现象**：
```
Error: pull model manifest: Get "https://registry.ollama.ai/...": timeout
```

**解决**：
```bash
# 使用代理下载（如果有代理）
export HTTPS_PROXY=http://127.0.0.1:7890
ollama pull qwen2.5:7b

# 或换用其他镜像源
ollama pull registry.cn-hangzhou.aliyuncs.com/ollama-library/qwen2.5:7b
```

---

### 问题3：内存不足

**现象**：模型运行时卡顿、电脑变慢

**解决**：
```bash
# 检查内存
sysctl hw.memsize

# 如果内存 < 8GB，建议换用更小模型
ollama pull qwen2.5:3b  # 3B模型，约2GB
```

然后修改书童配置中的模型名称：
```python
"ollama_model": "qwen2.5:3b"
```

---

### 问题4：Apple Silicon芯片兼容性

**现象**：M1/M2/M3 Mac安装后无法运行

**解决**：
Ollama原生支持Apple Silicon，无需额外操作。如果遇到问题：
```bash
# 确保下载的是ARM64版本
file /Applications/Ollama.app/Contents/MacOS/Ollama

# 预期输出包含 "arm64"
```

---

## 🔄 装好后如何更新

```bash
# 更新Ollama程序
brew upgrade ollama
# 或去官网重新下载

# 更新模型
ollama pull qwen2.5:7b
```

---

## 🆘 如果还是装不上

**方案B：用Docker安装**
```bash
# 如果有Docker
docker run -d -v ollama:/root/.ollama -p 11434:11434 --name ollama ollama/ollama

# 在容器内下载模型
docker exec -it ollama ollama pull qwen2.5:7b
```

**方案C：用OpenAI API替代**
```bash
# 无需安装任何模型
export OPENAI_API_KEY="sk-您的Key"
python3 bookboy_main.py
```

---

## 📞 安装完成后联系我

装好后，在终端运行：
```bash
ollama --version && ollama list
```

截图发给我，或者告诉我输出内容，我帮您验证书童是否能正常运行。

---

**安装有问题随时问我。**
**装好了立刻告诉我，我远程切换书童到真实AI模式。**

---

**文件位置**：`伴读书童AI训练素材库/00-核心配置/Ollama手动安装指南.md`  
**版本**：V1.0
