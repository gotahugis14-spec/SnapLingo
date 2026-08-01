"""ScreenLingo 入口：托盘常驻 + 全局热键截图 OCR + 中英双向翻译

使用流程：
  按热键（默认 Ctrl+Alt+O）→ 弹出操作选择（翻译 / 复制文字 / 翻译+复制）
  → 鼠标框选屏幕区域 → 按所选操作执行，结果窗口弹出，文字自动进剪贴板。

线程模型：
- 主线程：隐藏 Tk root，负责菜单/结果窗/设置窗/剪贴板，poll_queue 轮询
- pystray：托盘图标线程
- keyboard：全局热键回调线程，只向队列投递事件，不碰 UI
- 工作线程：截图 -> OCR -> (翻译)，结果入队
"""
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

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
             padx=16, pady=8, width=None):
    """统一样式的按钮"""
    return tk.Button(
        parent, text=text, command=command,
        font=(THEME["font"], size, "bold" if bold else "normal"),
        bg=bg or THEME["card"], fg=fg or THEME["text"],
        activebackground="#e6f7ec" if bg is None else bg,
        activeforeground=THEME["text"],
        relief="flat", bd=0, padx=padx, pady=pady,
        cursor="hand2", highlightthickness=1,
        highlightbackground=THEME["border"], width=width)


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
            except Exception as e:
                # 翻译失败不丢原文：结果窗口仍显示，附失败原因
                err_note = f"\n\n[翻译失败 / Translate failed] {e}"
        task_queue.put(("result", mode, text, translated, err_note))
    except Exception as e:
        task_queue.put(("error", str(e)))


def begin_capture(mode: str):
    """在主线程调用：弹遮罩截图，拿到图片后起后台线程处理。
    遮罩必须用主线程的主 Tk 实例（Toplevel），否则会出现
    'image pyimage does not exist' 错误。"""
    last_mode["mode"] = mode
    img = snipper.capture_selection(main_root)
    if img is None:
        return
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


# ---------- 结果窗口 ----------

def show_result_window(mode: str, text: str, translated: str, err_note: str = ""):
    win = tk.Toplevel(main_root)
    win.title("ScreenLingo - 识别结果 / Result")
    win.configure(bg=THEME["bg"])
    win.attributes("-topmost", True)
    win.geometry("920x660")

    if translated:
        body = f"【原文 / Original】\n{text}\n\n【译文 / Translation】\n{translated}"
    else:
        body = text
    if err_note:
        body += err_note

    txt = tk.Text(win, wrap="word", font=(THEME["font"], 12),
                  bg=THEME["card"], fg=THEME["text"],
                  relief="flat", bd=0, padx=14, pady=12)
    txt.insert("1.0", body)
    txt.configure(state="disabled")
    txt.pack(fill="both", expand=True, padx=14, pady=(14, 8))

    bar = tk.Frame(win, bg=THEME["bg"])
    bar.pack(fill="x", padx=14, pady=(0, 14))

    def copy_and(label, s):
        main_root.clipboard_clear()
        main_root.clipboard_append(s)
        status.config(text=f"已复制：{label} ✓", fg=THEME["accent_dark"])

    make_btn(bar, "复制原文 / Copy Original",
             lambda: copy_and("原文 / Original", text)).pack(side="left")
    if translated:
        make_btn(bar, "复制译文 / Copy Translation",
                 lambda: copy_and("译文 / Translation", translated)).pack(side="left", padx=8)
    make_btn(bar, "复制全部 / Copy All",
             lambda: copy_and("全部 / All", body)).pack(side="left", padx=8)
    make_btn(bar, "↻ 再来一次 / Again",
             lambda: (win.destroy(), task_queue.put(("action", last_mode["mode"])))).pack(side="left", padx=8)
    make_btn(bar, "关闭 / Close", win.destroy).pack(side="left", padx=8)

    status = tk.Label(bar, text="", font=(THEME["font"], 10),
                      fg=THEME["accent_dark"], bg=THEME["bg"])
    status.pack(side="left", padx=12)

    # 自动复制：翻译相关模式复制译文，否则复制原文
    if translated:
        copy_and("译文 / Translation", translated)
    else:
        copy_and("原文 / Original", text)


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

    # OCR 后端
    backend_var = tk.StringVar(value=cfg.get("ocr_backend", "auto"))
    combo = ttk.Combobox(body, textvariable=backend_var,
                         values=["auto", "tesseract", "api"], state="readonly")
    add_row(0, "OCR 后端", combo)

    # 全局快捷键
    hotkey_var = tk.StringVar(value=cfg.get("hotkey_menu", "ctrl+alt+o"))
    add_row(1, "全局快捷键", make_entry(hotkey_var))

    # API Key + 小眼睛（点击切换明文/密文）
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
    add_row(2, "API Key", key_frame)

    # API Key 获取指引链接
    def open_ak_page():
        import webbrowser
        webbrowser.open("https://cloud.siliconflow.cn/account/ak")

    link = tk.Label(body, text="🔑 不知道 API Key 是什么 / 在哪获取？点这里看步骤",
                    font=(THEME["font"], 10), fg="#2563eb", bg=THEME["bg"],
                    cursor="hand2")
    link.grid(row=3, column=1, sticky="w", pady=(0, 4))
    link.bind("<Button-1>", lambda _: open_ak_page())

    # 分隔线
    tk.Frame(body, bg=THEME["border"], height=1).grid(
        row=4, column=0, columnspan=2, sticky="ew", pady=12)

    # 进阶选项
    vision_var = tk.StringVar(value=cfg.get("vision_model", ""))
    add_row(5, "视觉模型", make_entry(vision_var))
    trans_var = tk.StringVar(value=cfg.get("translate_model", ""))
    add_row(6, "翻译模型", make_entry(trans_var))
    autostart_var = tk.BooleanVar(value=is_autostart_enabled())
    add_row(7, "开机自启", tk.Checkbutton(body, variable=autostart_var,
                                          bg=THEME["bg"], activebackground=THEME["bg"]))

    tk.Label(body,
             text="快捷键格式示例：ctrl+alt+o / alt+shift+k / f8\n"
                  "API Key 留空则使用环境变量 SILICONFLOW_API_KEY。\n"
                  "点「确定」后设置立即生效，无需重启。",
             font=(THEME["font"], 9), fg=THEME["muted"], bg=THEME["bg"],
             justify="left").grid(row=8, column=0, columnspan=2, sticky="w",
                                  pady=(6, 4))

    # 右下角确定按钮：点按才保存并生效
    footer = tk.Frame(win, bg=THEME["bg"])
    footer.pack(fill="x", padx=28, pady=(0, 22))

    def save():
        new_hotkey = hotkey_var.get().strip()
        if new_hotkey:
            cfg["hotkey_menu"] = new_hotkey
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
    # keyboard 回调线程：只投递事件，UI 由主线程处理
    task_queue.put(("menu",))


def rebind_hotkeys(cfg: dict):
    """先解绑旧热键，再注册新热键。保存设置后立即生效。"""
    global hotkey_handles
    for h in hotkey_handles:
        try:
            keyboard.remove_hotkey(h)
        except Exception:
            pass
    hotkey_handles = []
    hotkey = cfg.get("hotkey_menu", "ctrl+alt+o")
    try:
        hotkey_handles.append(keyboard.add_hotkey(hotkey, on_menu_hotkey))
    except Exception as e:
        messagebox.showerror(
            "ScreenLingo",
            f"注册全局热键失败（格式错误或需要管理员权限）：\n{e}",
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
        elif kind == "result":
            mode, text, translated, err_note = payload
            show_result_window(mode, text, translated, err_note)
        elif kind == "error":
            messagebox.showerror("ScreenLingo", str(payload[0]), parent=main_root)
    if not exit_flag["quit"]:
        main_root.after(150, poll_queue)


def main():
    global main_root, icon
    main_root = tk.Tk()
    main_root.withdraw()

    cfg = config.load()
    rebind_hotkeys(cfg)

    icon = setup_icon()
    icon.run_detached()

    main_root.after(150, poll_queue)
    main_root.mainloop()


if __name__ == "__main__":
    main()
