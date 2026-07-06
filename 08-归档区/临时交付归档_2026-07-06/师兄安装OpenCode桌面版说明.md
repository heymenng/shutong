# 师兄安装 OpenCode 桌面版说明

> 写给：灵觉 / Prome 师兄
> 目的：让师兄的 Mac 上也显示出 OpenCode 的 `$|` 图标
> 适用系统：macOS

---

## 一、这是什么？

OpenCode 有两个形态：

1. **命令行版**：通过终端运行 `opencode` 命令，没有图标。
2. **桌面版（OpenCode Desktop）**：有独立的 App 图标（一个深色圆角方块，里面有绿色的 `$` 和 `|`），可以放在 Dock 里，像普通软件一样打开。

师兄如果只有命令行版，就不会有那个图标。需要安装桌面版。

---

## 二、安装步骤（Mac）

### 步骤 1：下载 OpenCode Desktop

打开浏览器，访问 OpenCode 官网下载页面：

```
https://opencode.ai/download
```

或者直接在浏览器搜索 **"OpenCode Desktop download"**。

下载 **macOS ARM64** 版本（如果是 Intel Mac，选择 x86_64 版本）。

下载完成后，会得到一个 `.dmg` 文件，例如：

```
OpenCode Desktop.dmg
```

---

### 步骤 2：打开 DMG 文件

双击下载好的 `.dmg` 文件，系统会挂载一个磁盘，名字类似：

```
OpenCode 1.17.13-arm64
```

打开后，里面会有一个 **OpenCode.app** 文件，图标就是 `$|`。

---

### 步骤 3：安装到应用程序

把 **OpenCode.app** 拖到 **应用程序（Applications）** 文件夹里。

操作：
1. 打开 Finder
2. 左侧找到已挂载的 `OpenCode ...` 磁盘
3. 用鼠标按住 `OpenCode.app`
4. 拖到左侧的 `应用程序` 文件夹上，松手

安装完成。

---

### 步骤 4：让图标显示在 Dock 里（可选）

1. 打开 **启动台（Launchpad）**
2. 找到 OpenCode 图标（`$|`）
3. 右键点击图标 → **选项** → **保留在 Dock 中**

或者：
1. 打开 Finder → 应用程序
2. 找到 OpenCode.app
3. 拖到 Dock 栏上

---

### 步骤 5：首次打开

第一次打开时，Mac 可能会提示：

> "OpenCode.app 无法打开，因为无法验证开发者。"

解决方法：
1. 打开 **系统设置** → **隐私与安全性**
2. 在下方找到 "已阻止打开 OpenCode"
3. 点击 **仍要打开**

---

## 三、安装后效果

- 启动台里有 OpenCode 图标
- Dock 里可以常驻 OpenCode 图标
- 用 Spotlight 搜索 "OpenCode" 可以快速打开
- 打开后就是一个 `$|` 图标的 App

---

## 四、常见问题

**Q1：我已经有 `opencode` 命令了，还需要装桌面版吗？**

A：命令行版和桌面版是两套东西。想要 `$|` 图标，就必须安装桌面版。

**Q2：安装后图标不显示怎么办？**

A：
- 确认是否拖到了 `/Applications` 文件夹，而不是留在 DMG 里
- 重启一下 Finder：在 Finder 菜单栏点击 **前往** → **前往文件夹**，输入 `/Applications`，看有没有 OpenCode.app
- 如果还没有，重新拖一次

**Q3：打开时提示损坏怎么办？**

A：在终端执行：

```bash
xattr -dr com.apple.quarantine /Applications/OpenCode.app
```

然后再打开。

---

## 五、一句话总结

> 下载 OpenCode Desktop 的 `.dmg`，双击挂载后，把里面的 `OpenCode.app` 拖到 `应用程序` 文件夹，图标就会常驻。

---

*说明由书童整理*
*日期：2026-07-04*
