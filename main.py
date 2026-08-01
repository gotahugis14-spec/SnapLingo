"""ScreenLingo 入口：托盘常驻 + 全局热键截图 OCR + 中英双向翻译

使用流程：
  按热键（默认 Ctrl+Alt+O）→ 弹出操作选择（翻译 / 复制文字 / 翻译+复制）
  → 鼠标框选屏幕区域 → 立即弹出结果窗口（显示加载中）→ 识别/翻译完成后原地更新
  → 结果窗口支持历史浏览（上一个/下一个）、删除、编辑。

线程模型：
- 主线程：隐藏 Tk root，负责菜单/截图遮罩/结果窗/设置窗/剪贴板，poll_queue 轮询
- pystray：托盘图标线程
- keyboard：全局热键回调线程，只向队列投递事件，不碰 UI
- 工作线程：OCR/翻译（耗时网络请求），完成后结果入队
"""
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk
import logging
from logging.handlers import RotatingFileHandler

import keyboard
import pystray
from PIL import Image, ImageDraw

import config
import ocr
import snipper
import translator

task_queue = queue.Queue()
exit_flag = {"quit": False}
last_mode = {"mode": "copy"}
hotkey_handles = []

# 历史记录：单结果窗口 + 上一条/下一条浏览
history = []  # 每项 {"mode", "text", "translated", "err_note"}
hist_idx = {"i": -1}
result_win = {"win": None}

AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_NAME = "ScreenLingo"

# ---------- UI 主题 ----------
THEME = {
    "bg": "#f4f6f8",
    "card": "#ffffff",
    "accent": "#00c853",
    "accent_dark": "#00a544",
    "text": "#1f2937",
    "muted": "#6b7280",
    "border": "#e5e7eb",
    "font": "Microsoft YaHei UI",
}


def make_btn(parent, text, command, *, size=11, bg=None, fg=None, bold=False,
             padx=16, pady=8, width=None, state="normal"):
    """统一样式的按钮"""
    return tk.Button(
        parent, text=text, command=command,
        font=(THEME["font"], size, "bold" if bold else "normal"),
        bg=bg or THEME["card"], fg=fg or THEME["text"],
        activebackground="#e6f7ec" if bg is None else bg,
        activeforeground=THEME["text"],
        relief="flat", bd=0, padx=padx, pady=pady,
        cursor="hand2", highlightthickness=1,
        highlightbackground=THEME["border"], width=width, state=state)


# ---------- 日志 ----------

def setup_logging():
    log_dir = os.path.join(config.config_dir(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    handler = RotatingFileHandler(
        os.path.join(log_dir, "screenlingo.log"),
        maxBytes=1024 * 1024, backupCount=3, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler],
                        format="%(asctime)s %(levelname)s %(message)s")


# ---------- 管道：主线程截图，后台 OCR/翻译 ----------

def do_ocr_translate(img, mode: str):
    """后台线程执行 OCR/翻译（耗时网络请求不阻塞 UI）。mode: copy/translate/both"""
    try:
        cfg = config.load()
        text = ocr.ocr_image(img, cfg)
        translated = ""
        err_note = ""
        if mode in ("translate", "both"):
            try:
                translated = translator.translate(text, cfg)
                logging.info("translate done: %d chars -> %d chars", len(text), len(translated))
            except Exception as e:
                err_note = f"[翻译失败 / Translate failed] {e}"
                logging.exception("translate failed")
        logging.info("ocr done: mode=%s, %d chars", mode, len(text))
        task_queue.put(("update", mode, text, translated, err_note))
    except Exception as e:
        logging.exception("ocr pipeline failed")
        task_queue.put(("error", str(e)))


def begin_capture(mode: str):
    """在主线程调用：弹遮罩截图 → 立即弹结果窗口（加载中）→ 后台处理。
    遮罩必须用主线程的主 Tk 实例（Toplevel），否则会出现
    'image pyimage does not exist' 错误。"""
    last_mode["mode"] = mode
    img = snipper.capture_selection(main_root)
    if img is None:
        return
    show_result_window(mode)  # 立即弹出，显示加载中
    threading.Thread(target=do_ocr_translate, args=(img, mode), daemon=True).start()


# ---------- 操作选择菜单 ----------

def show_mode_menu() -> str | None:
    """弹出三选项菜单，返回 copy/translate/both；取消返回 None。阻塞式。"""
    result = {"mode": None}
    win = tk.Toplevel(main_root)
    win.title("ScreenLingo - 选择操作 / Choose Action")
    win.configure(bg=THEME["bg"])
    win.attributes("-topmost", True)
    win.resizable(False, False)

    tk.Label(win, text="截图后要做什么？", font=(THEME["font"], 16, "bold"),
             bg=THEME["bg"], fg=THEME["text"]).pack(pady=(26, 2))
    tk.Label(win, text="What do you want to do?", font=(THEME["font"], 10),
             bg=THEME["bg"], fg=THEME["muted"]).pack(pady=(0, 18))

    def pick(mode):
        result["mode"] = mode
        win.destroy()

    btns = [
        ("🌐  翻译 / Translate", "自动互译中英文", "translate"),
        ("📋  复制文字 / Copy Text", "只提取文字并复制", "copy"),
        ("✨  翻译 + 复制 / Both", "翻译并复制译文", "both"),
    ]
    for main_txt, sub_txt, mode in btns:
        tk.Button(
            win, text=f"{main_txt}\n{sub_txt}",
            font=(THEME["font"], 13),
            bg=THEME["card"], fg=THEME["text"],
            activebackground="#e6f7ec",
            relief="flat", bd=0, width=38, pady=12,
            cursor="hand2", highlightthickness=1,
            highlightbackground=THEME["border"],
            command=lambda m=mode: pick(m)).pack(pady=6)

    tk.Button(win, text="取消 / Cancel  (Esc)", command=win.destroy,
              font=(THEME["font"], 10), bg=THEME["bg"], fg=THEME["muted"],
              relief="flat", bd=0, cursor="hand2").pack(pady=(12, 18))
    win.bind("<Escape>", lambda _: win.destroy())

    win.update_idletasks()
    w, h = win.winfo_width(), win.winfo_height()
    x = (win.winfo_screenwidth() - w) // 2
    y = (win.winfo_screenheight() - h) // 2
    win.geometry(f"+{x}+{y}")
    main_root.wait_window(win)
    return result["mode"]


# ---------- 结果窗口（单实例 + 历史浏览 + 编辑） ----------

def set_text(txt: tk.Text, s: str):
    txt.config(state="normal")
    txt.delete("1.0", "end")
    txt.insert("1.0", s)
    txt.config(state="disabled")


def _copy_clipboard(s: str, status=None, label=""):
    main_root.clipboard_clear()
    main_root.clipboard_append(s)
    if status is not None:
        status.config(text=f"已复制：{label} ✓", fg=THEME["accent_dark"])


def _make_status(bar) -> tk.Label:
    status = tk.Label(bar, text="", font=(THEME["font"], 10),
                      fg=THEME["accent_dark"], bg=THEME["bg"])
    return status


def show_result_window(mode: str):
    """确保结果窗口存在并置前，显示加载中。完成后由 update_result 填充。"""
    win = result_win["win"]
    if win is None or not win.winfo_exists():
        win = _build_result_window()
        result_win["win"] = win
    win._mode = mode
    win._editing = False
    win.deiconify()
    win.lift()
    win.focus_force()

    if mode in ("translate", "both"):
        set_text(win._trans_txt, "⏳ 正在翻译…")
    else:
        set_text(win._trans_txt, "—（此模式不翻译）")
    set_text(win._orig_txt, "⏳ 正在识别截图中的文字…")
    win._pos_label.config(text="—")
    for b in (win._prev_btn, win._next_btn, win._del_btn,
              win._edit_btn, win._copy_orig, win._copy_trans, win._copy_all):
        b.config(state="disabled")
    win._edit_btn.config(text="✏️ 编辑")


def _build_result_window() -> tk.Toplevel:
    win = tk.Toplevel(main_root)
    win.title("ScreenLingo - 识别结果 / Result")
    win.configure(bg=THEME["bg"])
    win.attributes("-topmost", True)
    win.geometry("920x680")

    # 顶部：历史位置 + 标题
    head = tk.Frame(win, bg=THEME["bg"])
    head.pack(fill="x", padx=16, pady=(12, 0))
    tk.Label(head, text="识别结果 / Result", font=(THEME["font"], 14, "bold"),
             bg=THEME["bg"], fg=THEME["text"]).pack(side="left")
    pos_label = tk.Label(head, text="—", font=(THEME["font"], 11),
                         fg=THEME["muted"], bg=THEME["bg"])
    pos_label.pack(side="right")

    # 原文区
    tk.Label(win, text="📄 原文 / Original", font=(THEME["font"], 11, "bold"),
             bg=THEME["bg"], fg=THEME["text"]).pack(anchor="w", padx=16, pady=(10, 2))
    orig_txt = tk.Text(win, wrap="word", font=(THEME["font"], 12),
                       bg=THEME["card"], fg=THEME["text"],
                       relief="flat", bd=0, padx=12, pady=10, height=9)
    orig_txt.pack(fill="x", padx=16)
    orig_txt.configure(state="disabled")

    # 译文区
    tk.Label(win, text="🌐 译文 / Translation", font=(THEME["font"], 11, "bold"),
             bg=THEME["bg"], fg=THEME["text"]).pack(anchor="w", padx=16, pady=(10, 2))
    trans_txt = tk.Text(win, wrap="word", font=(THEME["font"], 12),
                        bg=THEME["card"], fg=THEME["text"],
                        relief="flat", bd=0, padx=12, pady=10, height=9)
    trans_txt.pack(fill="both", expand=True, padx=16, pady=(0, 8))
    trans_txt.configure(state="disabled")

    # 按钮栏
    bar = tk.Frame(win, bg=THEME["bg"])
    bar.pack(fill="x", padx=16, pady=(0, 12))
    status = _make_status(bar)
    status.pack(side="left")

    def current():
        i = hist_idx["i"]
        return history[i] if 0 <= i < len(history) else None

    def refresh():
        """把当前历史项填进窗口。"""
        item = current()
        if item is None:
            return
        set_text(orig_txt, item["text"])
        if item["translated"]:
            set_text(trans_txt, item["translated"] + (f"\n\n{item['err_note']}" if item.get("err_note") else ""))
        elif item.get("err_note"):
            set_text(trans_txt, f"—\n\n{item['err_note']}")
        else:
            set_text(trans_txt, "—（此模式不翻译）")
        pos_label.config(text=f"{hist_idx['i'] + 1} / {len(history)}")
        for b in (prev_btn, next_btn, del_btn, edit_btn,
                  copy_orig, copy_trans, copy_all):
            b.config(state="normal")
        prev_btn.config(state="normal" if hist_idx["i"] > 0 else "disabled")
        next_btn.config(state="normal" if hist_idx["i"] < len(history) - 1 else "disabled")
        edit_btn.config(text="✏️ 编辑")

    def go_prev():
        if hist_idx["i"] > 0:
            hist_idx["i"] -= 1
            refresh()

    def go_next():
        if hist_idx["i"] < len(history) - 1:
            hist_idx["i"] += 1
            refresh()

    def delete_current():
        if current() is None:
            return
        i = hist_idx["i"]
        history.pop(i)
        if not history:
            hist_idx["i"] = -1
            result_win["win"] = None
            win.destroy()
            return
        hist_idx["i"] = min(i, len(history) - 1)
        refresh()

    def toggle_edit():
        item = current()
        if item is None:
            return
        editing = not win._editing
        win._editing = editing
        for t in (orig_txt, trans_txt):
            t.config(state="normal" if editing else "disabled")
        edit_btn.config(text="✅ 保存" if editing else "✏️ 编辑")
        if not editing:  # 保存编辑内容
            item["text"] = orig_txt.get("1.0", "end-1c")
            item["translated"] = trans_txt.get("1.0", "end-1c")
            status.config(text="已保存修改 ✓", fg=THEME["accent_dark"])

    prev_btn = make_btn(bar, "◀ 上一个", go_prev)
    prev_btn.pack(side="right", padx=4)
    next_btn = make_btn(bar, "下一个 ▶", go_next)
    next_btn.pack(side="right", padx=4)
    del_btn = make_btn(bar, "🗑 删除", delete_current)
    del_btn.pack(side="right", padx=4)
    edit_btn = make_btn(bar, "✏️ 编辑", toggle_edit)
    edit_btn.pack(side="right", padx=4)
    def close_win():
        result_win["win"] = None
        win.destroy()

    def again():
        result_win["win"] = None
        win.destroy()
        task_queue.put(("action", last_mode["mode"]))

    make_btn(bar, "↻ 再来一次", again).pack(side="right", padx=4)
    make_btn(bar, "关闭", close_win).pack(side="right", padx=4)
    copy_orig = make_btn(bar, "复制原文",
                         lambda: _copy_cur(orig_txt, trans_txt, status, "原文"))
    copy_orig.pack(side="right", padx=4)
    copy_trans = make_btn(bar, "复制译文",
                          lambda: _copy_cur(orig_txt, trans_txt, status, "译文"))
    copy_trans.pack(side="right", padx=4)
    copy_all = make_btn(bar, "复制全部",
                        lambda: _copy_cur(orig_txt, trans_txt, status, "全部"))
    copy_all.pack(side="right", padx=4)

    win._orig_txt = orig_txt
    win._trans_txt = trans_txt
    win._pos_label = pos_label
    win._prev_btn = prev_btn
    win._next_btn = next_btn
    win._del_btn = del_btn
    win._edit_btn = edit_btn
    win._copy_orig = copy_orig
    win._copy_trans = copy_trans
    win._copy_all = copy_all
    win._status = status
    return win


def _copy_cur(orig_txt, trans_txt, status, label):
    """复制当前窗口显示的内容（按标签）"""
    i = hist_idx["i"]
    if not (0 <= i < len(history)):
        return
    item = history[i]
    if label == "原文":
        _copy_clipboard(item["text"], status, "原文")
    elif label == "译文" and item["translated"]:
        _copy_clipboard(item["translated"], status, "译文")
    elif label == "全部":
        body = item["text"]
        if item["translated"]:
            body += f"\n\n{item['translated']}"
        _copy_clipboard(body, status, "全部")


def update_result(mode: str, text: str, translated: str, err_note: str):
    """后台结果就绪：追加历史、自动复制、刷新窗口。"""
    history.append({"mode": mode, "text": text,
                    "translated": translated, "err_note": err_note})
    hist_idx["i"] = len(history) - 1
    # 自动复制最新结果
    if translated:
        main_root.clipboard_clear()
        main_root.clipboard_append(translated)
    else:
        main_root.clipboard_clear()
        main_root.clipboard_append(text)
    win = result_win["win"]
    if win is not None and win.winfo_exists():
        # 重新构建当前项到窗口
        i = hist_idx["i"]
        item = history[i]
        set_text(win._orig_txt, item["text"])
        if item["translated"]:
            set_text(win._trans_txt, item["translated"] + (f"\n\n{item['err_note']}" if item.get("err_note") else ""))
        elif item.get("err_note"):
            set_text(win._trans_txt, f"—\n\n{item['err_note']}")
        else:
            set_text(win._trans_txt, "—（此模式不翻译）")
        win._pos_label.config(text=f"{i + 1} / {len(history)}")
        for b in (win._prev_btn, win._next_btn, win._del_btn,
                  win._edit_btn, win._copy_orig, win._copy_trans, win._copy_all):
            b.config(state="normal")
        win._prev_btn.config(state="normal" if i > 0 else "disabled")
        win._next_btn.config(state="normal" if i < len(history) - 1 else "disabled")
        win._edit_btn.config(text="✏️ 编辑")
        win._status.config(text="已复制最新结果 ✓", fg=THEME["accent_dark"])


# ---------- 设置窗口 ----------

def show_settings():
    win = tk.Toplevel(main_root)
    win.title("ScreenLingo - 设置 / Settings")
    win.configure(bg=THEME["bg"])
    win.attributes("-topmost", True)
    win.geometry("600x560")
    win.resizable(False, False)
    cfg = config.load()

    tk.Label(win, text="设置 / Settings", font=(THEME["font"], 16, "bold"),
             bg=THEME["bg"], fg=THEME["text"]).pack(pady=(22, 6), padx=28, anchor="w")

    body = tk.Frame(win, bg=THEME["bg"])
    body.pack(fill="both", expand=True, padx=28)
    body.grid_columnconfigure(1, weight=1)

    def add_row(row, label, widget):
        tk.Label(body, text=label, font=(THEME["font"], 11), bg=THEME["bg"],
                 fg=THEME["text"], anchor="w").grid(
            row=row, column=0, sticky="w", padx=(0, 16), pady=9)
        widget.grid(row=row, column=1, sticky="ew", pady=9)

    def make_entry(var):
        return tk.Entry(body, textvariable=var, font=(THEME["font"], 11),
                        relief="solid", bd=1, highlightthickness=1,
                        highlightbackground=THEME["border"])

    backend_var = tk.StringVar(value=cfg.get("ocr_backend", "auto"))
    combo = ttk.Combobox(body, textvariable=backend_var,
                         values=["auto", "tesseract", "api"], state="readonly")
    add_row(0, "OCR 后端", combo)

    hotkey_var = tk.StringVar(value=cfg.get("hotkey_menu", "ctrl+alt+o"))
    add_row(1, "菜单快捷键", make_entry(hotkey_var))

    trans_hotkey_var = tk.StringVar(value=cfg.get("hotkey_translate", "ctrl+alt+t"))
    add_row(2, "直通翻译快捷键", make_entry(trans_hotkey_var))

    copy_hotkey_var = tk.StringVar(value=cfg.get("hotkey_copy", "ctrl+alt+c"))
    add_row(3, "直通复制快捷键", make_entry(copy_hotkey_var))

    key_var = tk.StringVar(value=config.get_api_key(cfg))
    key_frame = tk.Frame(body, bg=THEME["bg"])
    key_entry = tk.Entry(key_frame, textvariable=key_var, show="*",
                         font=(THEME["font"], 11), relief="solid", bd=1,
                         highlightthickness=1, highlightbackground=THEME["border"])
    key_entry.pack(side="left", fill="x", expand=True)
    key_state = {"shown": False}

    def toggle_eye():
        key_state["shown"] = not key_state["shown"]
        key_entry.config(show="" if key_state["shown"] else "*")
        eye_btn.config(text="🙈" if key_state["shown"] else "👁")

    eye_btn = tk.Button(key_frame, text="👁", command=toggle_eye,
                        font=(THEME["font"], 13), relief="flat", bd=0,
                        bg=THEME["bg"], cursor="hand2",
                        activebackground=THEME["bg"])
    eye_btn.pack(side="left", padx=(8, 0))
    add_row(4, "API Key", key_frame)

    def open_ak_page():
        import webbrowser
        webbrowser.open("https://cloud.siliconflow.cn/account/ak")

    link = tk.Label(body, text="🔑 不知道 API Key 是什么 / 在哪获取？点这里看步骤",
                    font=(THEME["font"], 10), fg="#2563eb", bg=THEME["bg"],
                    cursor="hand2")
    link.grid(row=5, column=1, sticky="w", pady=(0, 4))
    link.bind("<Button-1>", lambda _: open_ak_page())

    tk.Frame(body, bg=THEME["border"], height=1).grid(
        row=6, column=0, columnspan=2, sticky="ew", pady=12)

    vision_var = tk.StringVar(value=cfg.get("vision_model", ""))
    add_row(7, "视觉模型", make_entry(vision_var))
    trans_var = tk.StringVar(value=cfg.get("translate_model", ""))
    add_row(8, "翻译模型", make_entry(trans_var))
    autostart_var = tk.BooleanVar(value=is_autostart_enabled())
    add_row(9, "开机自启", tk.Checkbutton(body, variable=autostart_var,
                                          bg=THEME["bg"], activebackground=THEME["bg"]))

    tk.Label(body,
             text="快捷键格式示例：ctrl+alt+o / alt+shift+k / f8\n"
                  "API Key 留空则使用环境变量 SILICONFLOW_API_KEY。\n"
                  "点「确定」后设置立即生效，无需重启。",
             font=(THEME["font"], 9), fg=THEME["muted"], bg=THEME["bg"],
             justify="left").grid(row=10, column=0, columnspan=2, sticky="w",
                                  pady=(6, 4))

    footer = tk.Frame(win, bg=THEME["bg"])
    footer.pack(fill="x", padx=28, pady=(0, 22))

    def save():
        new_hotkey = hotkey_var.get().strip()
        if new_hotkey:
            cfg["hotkey_menu"] = new_hotkey
        if trans_hotkey_var.get().strip():
            cfg["hotkey_translate"] = trans_hotkey_var.get().strip()
        if copy_hotkey_var.get().strip():
            cfg["hotkey_copy"] = copy_hotkey_var.get().strip()
        cfg["ocr_backend"] = backend_var.get()
        cfg["api_key"] = key_var.get().strip()
        cfg["vision_model"] = vision_var.get().strip()
        cfg["translate_model"] = trans_var.get().strip()
        config.save(cfg)
        set_autostart(autostart_var.get())
        rebind_hotkeys(cfg)
        win.destroy()
        messagebox.showinfo("ScreenLingo",
                            "设置已保存，快捷键已生效。\nSettings saved.",
                            parent=main_root)

    make_btn(footer, "确定  OK", save, size=13, bold=True,
             bg=THEME["accent"], fg="#ffffff", padx=36, pady=10).pack(side="right")


# ---------- 首次运行引导 ----------

def show_welcome():
    """首次运行（无 API key 且无本地 Tesseract）时弹出引导。"""
    win = tk.Toplevel(main_root)
    win.title("ScreenLingo - 欢迎 / Welcome")
    win.configure(bg=THEME["bg"])
    win.attributes("-topmost", True)
    win.geometry("560x380")
    win.resizable(False, False)

    tk.Label(win, text="👋 欢迎使用 ScreenLingo！", font=(THEME["font"], 16, "bold"),
             bg=THEME["bg"], fg=THEME["text"]).pack(pady=(26, 12))
    tk.Label(win, text=(
        "截图识别与翻译需要调用云端 AI 服务，\n"
        "首次使用需要配置一个 API Key（云端密钥）。\n\n"
        "获取步骤（约 2 分钟，免费注册）：\n"
        "1. 打开 siliconflow.cn 注册并登录\n"
        "2. 左侧菜单「API 密钥」→ 新建 API 密钥\n"
        "3. 复制 sk- 开头的字符串（关闭后不再显示）\n"
        "4. 点下方「打开设置」粘贴进去，点确定\n\n"
        "不想用云端？也可以安装本地 Tesseract 后\n"
        "在设置里把 OCR 后端切到 tesseract。"),
        font=(THEME["font"], 11), bg=THEME["bg"], fg=THEME["text"],
        justify="left").pack(padx=36, anchor="w")

    bar = tk.Frame(win, bg=THEME["bg"])
    bar.pack(pady=(18, 22))

    def open_ak_page():
        import webbrowser
        webbrowser.open("https://cloud.siliconflow.cn/account/ak")
        win.destroy()

    def open_settings():
        win.destroy()
        show_settings()

    make_btn(bar, "🔑 打开密钥页", open_ak_page, size=11, bold=True,
             bg=THEME["accent"], fg="#ffffff", padx=20, pady=8).pack(side="left", padx=6)
    make_btn(bar, "⚙️ 打开设置", open_settings).pack(side="left", padx=6)
    make_btn(bar, "稍后再说", win.destroy).pack(side="left", padx=6)

    win.update_idletasks()
    x = (win.winfo_screenwidth() - 560) // 2
    y = (win.winfo_screenheight() - 380) // 2
    win.geometry(f"+{x}+{y}")


# ---------- 单实例锁 ----------

def ensure_single_instance() -> bool:
    """防止多开：第二个实例直接退出。返回 False 表示已有实例在运行。"""
    try:
        import ctypes
        ctypes.windll.kernel32.CreateMutexW(None, False, "ScreenLingo_SingleInstance")
        return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS
    except Exception:
        return True


# ---------- 开机自启（注册表） ----------

def autostart_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return f'"{sys.executable}" "{os.path.abspath(__file__)}"'


def set_autostart(enabled: bool):
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY,
                             0, winreg.KEY_SET_VALUE)
        if enabled:
            winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ,
                              autostart_command())
        else:
            try:
                winreg.DeleteValue(key, AUTOSTART_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        messagebox.showerror("ScreenLingo", f"设置开机自启失败：\n{e}",
                             parent=main_root)


def is_autostart_enabled() -> bool:
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY,
                             0, winreg.KEY_READ)
        winreg.QueryValueEx(key, AUTOSTART_NAME)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


# ---------- 托盘 ----------

def make_icon_image() -> Image.Image:
    img = Image.new("RGB", (64, 64), "#121826")
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((10, 20, 54, 50), radius=8, fill="#00c853")
    d.ellipse((24, 26, 40, 42), fill="#121826")
    d.line((40, 36, 50, 44), fill="#00c853", width=4)
    return img


def on_translate(_icon, _item):
    task_queue.put(("action", "translate"))


def on_copy(_icon, _item):
    task_queue.put(("action", "copy"))


def on_both(_icon, _item):
    task_queue.put(("action", "both"))


def on_settings(_icon, _item):
    main_root.after(0, show_settings)


def on_quit(_icon, _item):
    exit_flag["quit"] = True
    for h in hotkey_handles:
        try:
            keyboard.remove_hotkey(h)
        except Exception:
            pass
    icon.stop()
    main_root.after(0, main_root.destroy)


def setup_icon() -> pystray.Icon:
    menu = pystray.Menu(
        pystray.MenuItem("🌐 翻译 / Translate", on_translate),
        pystray.MenuItem("📋 复制文字 / Copy Text", on_copy),
        pystray.MenuItem("✨ 翻译+复制 / Both", on_both),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("设置… / Settings", on_settings),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出 / Quit", on_quit),
    )
    return pystray.Icon("ScreenLingo", make_icon_image(),
                        "ScreenLingo - 截图OCR + 中英互译", menu)


# ---------- 全局热键 ----------

def on_menu_hotkey():
    task_queue.put(("menu",))


def rebind_hotkeys(cfg: dict):
    """先解绑旧热键，再注册全部热键（菜单 + 直通翻译 + 直通复制）。保存设置后立即生效。"""
    global hotkey_handles
    for h in hotkey_handles:
        try:
            keyboard.remove_hotkey(h)
        except Exception:
            pass
    hotkey_handles = []
    binds = [
        (cfg.get("hotkey_menu", "ctrl+alt+o"), on_menu_hotkey),
        (cfg.get("hotkey_translate", "ctrl+alt+t"),
         lambda: task_queue.put(("action", "translate"))),
        (cfg.get("hotkey_copy", "ctrl+alt+c"),
         lambda: task_queue.put(("action", "copy"))),
    ]
    errors = []
    for hotkey, fn in binds:
        try:
            hotkey_handles.append(keyboard.add_hotkey(hotkey, fn))
        except Exception as e:
            logging.error("hotkey %s register failed: %s", hotkey, e)
            errors.append(f"{hotkey}: {e}")
    if errors:
        messagebox.showerror(
            "ScreenLingo",
            "部分全局热键注册失败（格式错误或需要管理员权限）：\n"
            + "\n".join(errors),
            parent=main_root)


# ---------- 主循环 ----------

def poll_queue():
    while True:
        try:
            kind, *payload = task_queue.get_nowait()
        except queue.Empty:
            break
        if kind == "menu":
            mode = show_mode_menu()
            if mode:
                begin_capture(mode)
        elif kind == "action":
            begin_capture(payload[0])
        elif kind == "update":
            update_result(payload[0], payload[1], payload[2], payload[3])
        elif kind == "error":
            messagebox.showerror("ScreenLingo", str(payload[0]), parent=main_root)
    if not exit_flag["quit"]:
        main_root.after(150, poll_queue)


def main():
    global main_root, icon
    setup_logging()
    logging.info("ScreenLingo started")
    main_root = tk.Tk()
    main_root.withdraw()

    if not ensure_single_instance():
        logging.warning("another instance already running, exit")
        messagebox.showwarning(
            "ScreenLingo",
            "ScreenLingo 已经在运行中。\nScreenLingo is already running.",
            parent=main_root)
        main_root.destroy()
        return

    cfg = config.load()
    rebind_hotkeys(cfg)

    # 首次运行引导：无 API key 且无本地 Tesseract
    if not config.get_api_key(cfg) and not ocr.tesseract_available():
        main_root.after(900, show_welcome)

    icon = setup_icon()
    icon.run_detached()

    main_root.after(150, poll_queue)
    main_root.mainloop()


if __name__ == "__main__":
    main()
