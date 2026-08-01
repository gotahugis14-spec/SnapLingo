"""全屏遮罩 + 鼠标框选截图（主显示器）

样式参考主流截图工具（Snipaste/QQ 截图）：暗色遮罩 + 蓝色选区框 + 尺寸提示。

重要：必须把 parent（主 Tk 实例）传进来，用 Toplevel 显示遮罩，
不要自建 Tk —— 多个 Tk 实例会互相干扰，导致
"image 'pyimageN' doesn't exist" 之类的错误。
"""
import mss
import tkinter as tk
from PIL import Image, ImageEnhance, ImageTk

FRAME_COLOR = "#ff8c00"  # 选区框：橙红虚线（参考 Windows 自带截图工具 Snip & Sketch 风格）

FONT = "Microsoft YaHei UI"


def _grab_screen() -> Image.Image:
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # 主显示器
        raw = sct.grab(monitor)
        return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")


def capture_selection(parent=None) -> Image.Image | None:
    """显示全屏遮罩，鼠标框选区域，返回裁剪后的图片；Esc 或点选过小返回 None。

    parent：主 Tk 实例（推荐必传）。传入时用 Toplevel 显示，wait_window
    嵌套事件循环，全程只有主线程一个 Tk 实例，杜绝 pyimage 错误。
    """
    bg = _grab_screen()
    # 遮罩背景：原图压暗，模拟专业截图工具的暗色遮罩
    dim = ImageEnhance.Brightness(bg).enhance(0.45)
    result = {"img": None}

    if parent is not None:
        win = tk.Toplevel(parent)
    else:
        win = tk.Tk()
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    w, h = bg.size
    win.geometry(f"{w}x{h}+0+0")

    photo = ImageTk.PhotoImage(dim)
    win._screenlingo_photo = photo  # 持有引用，防止被垃圾回收
    canvas = tk.Canvas(win, width=w, height=h, highlightthickness=0)
    canvas.pack()
    canvas.create_image(0, 0, anchor="nw", image=photo)

    state = {"x0": 0, "y0": 0, "lines": None, "size_text": None}

    def draw_rect(x1, y1, x2, y2):
        # 用四条 create_line 画虚线边框（create_rectangle 不支持 dash）
        if state["lines"]:
            for ln in state["lines"]:
                canvas.delete(ln)
        if state["size_text"]:
            canvas.delete(state["size_text"])
        state["lines"] = [
            canvas.create_line(x1, y1, x2, y1, fill=FRAME_COLOR, width=2, dash=(6, 4)),
            canvas.create_line(x2, y1, x2, y2, fill=FRAME_COLOR, width=2, dash=(6, 4)),
            canvas.create_line(x2, y2, x1, y2, fill=FRAME_COLOR, width=2, dash=(6, 4)),
            canvas.create_line(x1, y2, x1, y1, fill=FRAME_COLOR, width=2, dash=(6, 4)),
        ]
        sw, sh = abs(x2 - x1), abs(y2 - y1)
        tx = min(x1, x2) + 6
        ty = min(y1, y2) + sw + 10 if sw > 0 else min(y1, y2) + 10
        state["size_text"] = canvas.create_text(
            tx, ty, anchor="nw", text=f"{sw} × {sh}",
            fill=FRAME_COLOR, font=(FONT, 12, "bold"))

    def on_press(e):
        state["x0"], state["y0"] = e.x, e.y
        draw_rect(e.x, e.y, e.x, e.y)

    def on_drag(e):
        draw_rect(state["x0"], state["y0"], e.x, e.y)

    def on_release(e):
        x1, x2 = sorted((state["x0"], e.x))
        y1, y2 = sorted((state["y0"], e.y))
        if x2 - x1 < 3 or y2 - y1 < 3:  # 过小视为取消
            win.destroy()
            return
        result["img"] = bg.crop((x1, y1, x2, y2))
        win.destroy()

    def on_escape(_):
        win.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    win.bind("<Escape>", on_escape)

    if parent is not None:
        win.wait_window()  # 嵌套事件循环，主线程继续处理其他 Tk 事件
    else:
        win.mainloop()
    return result["img"]
