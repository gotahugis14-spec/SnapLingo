# 🎯 ScreenLingo — 截图即得：OCR 文字提取 + 一键英文翻译

> **按下热键，框选屏幕任意区域，文字自动进剪贴板；再按另一个键，直接拿到英文翻译。**
> 看英文文献、截图文档、提取网页/视频里的文字——从此不用再手敲一个字。

![platform](https://img.shields.io/badge/platform-Windows-0078d6) ![python](https://img.shields.io/badge/python-3.10%2B-3776ab) ![license](https://img.shields.io/badge/license-MIT-green) ![size](https://img.shields.io/badge/size-%3E10KB-blue)

---

## ✨ 它解决什么问题

| 场景 | 以前 | 用 ScreenLingo |
|---|---|---|
| 网页/PDF 文字不能复制 | 截图 → 打开 OCR 网站 → 下载图片 → 上传 → 复制 | 热键框选 → 文字已在剪贴板，**2 秒** |
| 英文文章/论文看不懂 | 逐句复制 → 贴进翻译网站 | 热键框选 → 原文+英文翻译同时到手 |
| 视频/图片里的字幕 | 一帧一帧截图手打 | 框选即得 |

## 🚀 快速开始

### 方式一：直接下载 exe（推荐，无需 Python）
去 [Releases](../../releases) 下载 `ScreenLingo.exe`，双击运行，托盘出现图标即可用。

### 方式二：源码运行
```bash
pip install -r requirements.txt
python main.py
```

## 🕹️ 使用

| 操作 | 快捷键 |
|---|---|
| 截图识别并复制文字 | `Ctrl + Alt + O` |
| 截图识别 + 翻译成英文 | `Ctrl + Alt + T` |
| 取消框选 | `Esc` |

1. 按下快捷键，屏幕出现遮罩
2. 鼠标拖拽框选目标区域，松开
3. 结果窗口弹出，文字已自动复制到剪贴板 ✅

## ⚙️ 配置 OCR 后端

支持三种后端，`config.json` 或托盘"设置"里切换（配置文件在 `%APPDATA%\ScreenLingo\`）：

| 后端 | 说明 | 需要什么 |
|---|---|---|
| `auto`（默认） | 检测到 Tesseract 用本地，否则走 API | 无 |
| `tesseract` | 本地离线识别，免费 | 安装 [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) + 中文语言包 `chi_sim` |
| `api` | OpenAI 兼容视觉模型，中文/复杂版面准确率最高 | 任意 OpenAI 兼容 API 的 key |

**配置 API key（二选一）：**
```bash
# 方式一：环境变量（推荐，安全）
set SILICONFLOW_API_KEY=sk-xxx

# 方式二：编辑 %APPDATA%\ScreenLingo\config.json
{"api_key": "sk-xxx"}
```

默认使用 [SiliconFlow](https://siliconflow.cn) 的 OpenAI 兼容接口（视觉模型 `Qwen/Qwen3-VL-8B-Instruct`，翻译模型 `deepseek-ai/DeepSeek-V3.2`），换成任意兼容服务只需改 `api_base_url` 和模型名。

## 🏗️ 项目结构

```
ScreenLingo/
├── main.py          # 入口：托盘 + 全局热键 + 结果窗口
├── snipper.py       # 全屏遮罩 + 鼠标框选截图
├── ocr.py           # OCR 后端：tesseract / api
├── translator.py    # 英文翻译（OpenAI 兼容）
├── config.py        # 配置读写（%APPDATA%/ScreenLingo/config.json）
├── build.bat        # 一键打包 exe
└── requirements.txt
```

## 🧱 打包成 exe（给别人用）

```bash
build.bat
# 产物在 dist\ScreenLingo.exe，拷到任何 Windows 电脑都能跑
```

## ❓ 常见问题

- **热键没反应？** 右键托盘图标，或尝试以管理员身份运行（部分软件会拦截全局热键）。
- **提示未配置 API key？** 按上面"配置 API key"两步操作，然后重新框选。
- **Tesseract 识别中文乱码？** 确认安装了 `chi_sim.traineddata` 语言包，并重启程序。
- **exe 被杀毒软件误报？** 本项目完全开源，代码可自查；这是 PyInstaller 打包的常见误报。

## 📄 License

[MIT](LICENSE) — 随便用，注明出处即可。

## ⭐ 支持

如果它帮你省了时间，点个 Star 就是最大的支持 ❤️
