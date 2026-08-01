"""全屏遮罩 + 鼠标框选截图（主显示器）"""
import mss
import tkinter as tk
from PIL import Image, ImageTk


def _grab_screen() -> Image.Image:
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # 主显示器
        raw = sct.grab(monitor)
        return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")


def capture_selection() -> Image.Image | None:
    """显示全屏遮罩，鼠标框选区域，返回裁剪后的图片；Esc 或点选过小返回 None"""
    bg = _grab_screen()
    result = {"img": None}

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.92)
    w, h = bg.size
    root.geometry(f"{w}x{h}+0+0")

    photo = ImageTk.PhotoImage(bg)
    canvas = tk.Canvas(root, width=w, height=h, highlightthickness=0)
    canvas.pack()
    canvas.create_image(0, 0, anchor="nw", image=photo)

    state = {"x0": 0, "y0": 0, "rect": None}

    def on_press(e):
        state["x0"], state["y0"] = e.x, e.y
        if state["rect"]:
            canvas.delete(state["rect"])
        state["rect"] = canvas.create_rectangle(
            e.x, e.y, e.x, e.y, outline="#00c853", width=2)

    def on_drag(e):
        if state["rect"]:
            canvas.coords(state["rect"], state["x0"], state["y0"], e.x, e.y)

    def on_release(e):
        x1, x2 = sorted((state["x0"], e.x))
        y1, y2 = sorted((state["y0"], e.y))
        if x2 - x1 < 3 or y2 - y1 < 3:  # 过小视为取消
            root.destroy()
            return
        result["img"] = bg.crop((x1, y1, x2, y2))
        root.destroy()

    def on_escape(_):
        root.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind("<Escape>", on_escape)

    root.mainloop()
    return result["img"]
