"""ScreenLingo 入口：托盘常驻 + 全局热键截图 OCR + 英文翻译

线程模型：
- 主线程：隐藏的 Tk root，负责弹结果窗 / 设置窗 / 剪贴板，poll_queue 轮询结果
- pystray：托盘图标线程
- keyboard：全局热键回调线程，回调里再起线程跑 截图->OCR->翻译
"""
import queue
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


# ---------- 管道：截图 -> OCR -> (翻译) ----------

def run_pipeline(translate: bool):
    try:
        img = snipper.capture_selection()
        if img is None:
            return
        cfg = config.load()
        text = ocr.ocr_image(img, cfg)
        translated = ""
        err_note = ""
        if translate:
            try:
                translated = translator.translate_to_english(text, cfg)
            except Exception as e:
                # 翻译失败不丢原文：结果窗口仍显示，附失败原因
                err_note = f"\n\n[翻译失败] {e}"
        task_queue.put(("result", text, translated, err_note))
    except Exception as e:
        task_queue.put(("error", str(e)))


def start_pipeline(translate: bool):
    threading.Thread(target=run_pipeline, args=(translate,), daemon=True).start()


# ---------- 结果窗口 ----------

def show_result_window(text: str, translated: str, err_note: str = ""):
    win = tk.Toplevel(main_root)
    win.title("ScreenLingo - 识别结果")
    win.attributes("-topmost", True)
    win.geometry("680x460")

    if translated:
        body = f"【原文】\n{text}\n\n【英文翻译】\n{translated}"
    elif err_note:
        body = f"{text}{err_note}"
    else:
        body = text

    txt = tk.Text(win, wrap="word", font=("Microsoft YaHei UI", 11))
    txt.insert("1.0", body)
    txt.configure(state="disabled")
    txt.pack(fill="both", expand=True, padx=8, pady=8)

    bar = tk.Frame(win)
    bar.pack(fill="x", padx=8, pady=(0, 8))

    def copy_all():
        main_root.clipboard_clear()
        main_root.clipboard_append(body)
        status.config(text="已复制到剪贴板 ✓", fg="#00a652")

    tk.Button(bar, text="复制全部", command=copy_all).pack(side="left")
    tk.Button(bar, text="关闭", command=win.destroy).pack(side="left", padx=6)
    status = tk.Label(bar, text="", fg="#00a652")
    status.pack(side="left", padx=10)


# ---------- 设置窗口 ----------

def show_settings():
    win = tk.Toplevel(main_root)
    win.title("ScreenLingo - 设置")
    win.attributes("-topmost", True)
    win.geometry("440x320")
    cfg = config.load()

    rows = tk.Frame(win)
    rows.pack(fill="both", expand=True, padx=12, pady=12)

    def add_row(label, widget):
        f = tk.Frame(rows)
        f.pack(fill="x", pady=4)
        tk.Label(f, text=label, width=12, anchor="w").pack(side="left")
        widget.pack(side="left", fill="x", expand=True)

    backend_var = tk.StringVar(value=cfg.get("ocr_backend", "auto"))
    add_row("OCR 后端", ttk.Combobox(rows, textvariable=backend_var,
                                     values=["auto", "tesseract", "api"],
                                     state="readonly"))

    key_var = tk.StringVar(value=config.get_api_key(cfg))
    add_row("API Key", tk.Entry(rows, textvariable=key_var, show="*"))

    vision_var = tk.StringVar(value=cfg.get("vision_model", ""))
    add_row("视觉模型", tk.Entry(rows, textvariable=vision_var))

    trans_var = tk.StringVar(value=cfg.get("translate_model", ""))
    add_row("翻译模型", tk.Entry(rows, textvariable=trans_var))

    tk.Label(
        rows,
        text="提示：Key 留空则使用环境变量 SILICONFLOW_API_KEY。\n"
             "OCR 后端 auto = 有 Tesseract 用本地，否则用 API。",
        fg="#888", justify="left").pack(anchor="w", pady=8)

    def save():
        cfg["ocr_backend"] = backend_var.get()
        cfg["api_key"] = key_var.get().strip()
        cfg["vision_model"] = vision_var.get().strip()
        cfg["translate_model"] = trans_var.get().strip()
        config.save(cfg)
        win.destroy()
        messagebox.showinfo("ScreenLingo", "设置已保存。", parent=main_root)

    tk.Button(rows, text="保存", command=save, width=10).pack(anchor="e")


# ---------- 托盘 ----------

def make_icon_image() -> Image.Image:
    img = Image.new("RGB", (64, 64), "#121826")
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((10, 20, 54, 50), radius=8, fill="#00c853")
    d.ellipse((24, 26, 40, 42), fill="#121826")
    d.line((40, 36, 50, 44), fill="#00c853", width=4)
    return img


def on_ocr(_icon, _item):
    start_pipeline(False)


def on_translate(_icon, _item):
    start_pipeline(True)


def on_settings(_icon, _item):
    main_root.after(0, show_settings)


def on_quit(_icon, _item):
    exit_flag["quit"] = True
    keyboard.unhook_all()
    icon.stop()
    main_root.after(0, main_root.destroy)


def setup_icon() -> pystray.Icon:
    menu = pystray.Menu(
        pystray.MenuItem("截图识别并复制  (Ctrl+Alt+O)", on_ocr),
        pystray.MenuItem("截图识别并翻译成英文  (Ctrl+Alt+T)", on_translate),
        pystray.MenuItem("设置…", on_settings),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", on_quit),
    )
    return pystray.Icon("ScreenLingo", make_icon_image(),
                        "ScreenLingo - 截图OCR + 英文翻译", menu)


# ---------- 主循环 ----------

def poll_queue():
    while True:
        try:
            kind, *payload = task_queue.get_nowait()
        except queue.Empty:
            break
        if kind == "result":
            text, translated, err_note = payload
            main_root.clipboard_clear()
            main_root.clipboard_append(translated if translated else text)
            show_result_window(text, translated, err_note)
        elif kind == "error":
            messagebox.showerror("ScreenLingo", str(payload[0]), parent=main_root)
    if not exit_flag["quit"]:
        main_root.after(150, poll_queue)


def main():
    global main_root, icon
    main_root = tk.Tk()
    main_root.withdraw()

    cfg = config.load()
    try:
        keyboard.add_hotkey(cfg.get("hotkey_ocr", "ctrl+alt+o"),
                            lambda: start_pipeline(False))
        keyboard.add_hotkey(cfg.get("hotkey_translate", "ctrl+alt+t"),
                            lambda: start_pipeline(True))
    except Exception as e:
        messagebox.showerror(
            "ScreenLingo",
            f"注册全局热键失败（可能需要管理员权限运行）：\n{e}",
            parent=main_root)

    icon = setup_icon()
    icon.run_detached()

    main_root.after(150, poll_queue)
    main_root.mainloop()


if __name__ == "__main__":
    main()
