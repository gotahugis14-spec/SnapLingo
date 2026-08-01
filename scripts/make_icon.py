"""生成 ScreenLingo 应用图标 icon.ico（与托盘图标同风格：深底 + 绿色相机）"""
from PIL import Image, ImageDraw


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 64.0
    # 深色圆角底
    d.rounded_rectangle((4 * s, 4 * s, 60 * s, 60 * s),
                        radius=14 * s, fill=(18, 24, 38, 255))
    # 绿色镜头
    d.rounded_rectangle((12 * s, 22 * s, 52 * s, 50 * s),
                        radius=9 * s, fill=(0, 200, 83, 255))
    # 镜头孔
    d.ellipse((26 * s, 28 * s, 38 * s, 40 * s), fill=(18, 24, 38, 255))
    # 快门线
    d.line((40 * s, 38 * s, 48 * s, 44 * s), fill=(0, 200, 83, 255),
           width=max(1, round(4 * s)))
    return img


if __name__ == "__main__":
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [draw_icon(s) for s in sizes]
    imgs[0].save("icon.ico", format="ICO",
                 sizes=[(s, s) for s in sizes], append_images=imgs[1:])
    print("icon.ico generated:", sizes)
