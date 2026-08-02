# 贡献指南 / Contributing Guide

中文 | [English](#english)

感谢你愿意为 **SnapLingo** 贡献力量！无论是提 Bug、给建议、写文档还是提代码，都欢迎 ❤️

## 提 Issue（Bug / 建议）

- 先搜索 [Issues](../../issues) 看是否已有人提过
- 说明：**操作步骤、期望结果、实际结果**、Windows 版本
- 如果是报错，请附上日志：`%APPDATA%\ScreenLingo\logs\screenlingo.log`
- 报错截图也可以直接贴

## 提 PR（代码贡献）

1. **Fork** 本仓库并 clone 到本地
2. 创建功能分支：`git checkout -b feat/my-feature`
3. 本地开发运行：
   ```bash
   pip install -r requirements.txt
   python main.py
   ```
4. 确保语法与测试通过：
   ```bash
   python -m py_compile main.py config.py ocr.py snipper.py translator.py
   python -m unittest discover tests
   ```
5. 提交（写清楚改动内容，中文或英文均可）
6. Push 后从你的 fork 发起 Pull Request

## 代码规范

- Python 3.10+，标准库优先，少加依赖
- 所有 Tk 界面操作必须在**主线程**；网络请求放后台线程
- 新增配置项请同步更新 `config.py` 的 `DEFAULTS` 和 `config.json.example`
- 功能改动请同步更新 `README.md`（中英双语）
- 界面文案保持中英双语（如 `原文 / Original`）

## 发版流程（维护者）

1. 合并 PR 到 `main`
2. 打标签并推送（CI 会自动打包并发布 Release）：
   ```bash
   git tag vX.Y && git push origin vX.Y
   ```
3. 检查 [Releases](../../releases) 是否生成 `ScreenLingo.exe` + `SHA256.txt`

---

# English

Thanks for contributing to **SnapLingo**! Bug reports, feature ideas, docs and code are all welcome ❤️

## Issues

- Search [Issues](../../issues) first
- Include: **steps to reproduce, expected vs actual result**, Windows version
- For crashes, attach the log: `%APPDATA%\ScreenLingo\logs\screenlingo.log`
- Screenshots welcome

## Pull Requests

1. **Fork** and clone the repo
2. Branch: `git checkout -b feat/my-feature`
3. Run locally:
   ```bash
   pip install -r requirements.txt
   python main.py
   ```
4. Verify:
   ```bash
   python -m py_compile main.py config.py ocr.py snipper.py translator.py
   python -m unittest discover tests
   ```
5. Commit with a clear message, push, and open a PR from your fork

## Coding conventions

- Python 3.10+, prefer the standard library, keep dependencies minimal
- All Tk UI operations must happen on the **main thread**; network calls go to background threads
- New config keys must be added to `DEFAULTS` in `config.py` and to `config.json.example`
- Feature changes should update `README.md` (bilingual)
- UI strings stay bilingual (e.g. `原文 / Original`)

## Releasing (maintainers)

1. Merge PRs into `main`
2. Tag and push — CI builds and publishes the Release automatically:
   ```bash
   git tag vX.Y && git push origin vX.Y
   ```
3. Check [Releases](../../releases) for `ScreenLingo.exe` + `SHA256.txt`
