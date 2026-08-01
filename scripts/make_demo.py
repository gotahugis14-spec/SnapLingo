"""生成 README 演示图 docs/screenshot-mask.png（示意虚线截图遮罩效果）"""
import os

from PIL import Image, ImageDraw, ImageFont

FONT = "C:/Windows/Fonts/msyh.ttc"

W, H = 720, 420
img = Image.new("RGB", (W, H), (48, 54, 66))  # 压暗的屏幕
d = ImageDraw.Draw(img)

font_small = ImageFont.truetype(FONT, 20)
font_large = ImageFont.truetype(FONT, 22)
font_size = ImageFont.truetype(FONT, 15)

# 压暗区域的"屏幕内容"
d.text((36, 40), "Here is some text on the screen (dimmed).", fill=(110, 116, 128), font=font_small)
d.text((36, 78), "屏幕上的其他内容（被遮罩压暗）", fill=(110, 116, 128), font=font_small)
d.text((36, 116), "Press Ctrl+Alt+O to start...", fill=(110, 116, 128), font=font_small)

# 选区：框内为正常亮度（模拟）
x1, y1, x2, y2 = 80, 150, 620, 300
d.text((100, 172), "Selected region — text stays bright", fill=(242, 244, 248), font=font_large)
d.text((100, 210), "选中区域：文字保持正常亮度，方便核对", fill=(242, 244, 248), font=font_large)
d.text((100, 250), "ScreenLingo 会识别这里的文字", fill=(242, 244, 248), font=font_large)

# 橙色虚线框（dash 模拟）
ORANGE = (255, 140, 0)
step, seg = 14, 8
for px in range(x1, x2, step):
    d.line((px, y1, min(px + seg, x2), y1), fill=ORANGE, width=3)
    d.line((px, y2, min(px + seg, x2), y2), fill=ORANGE, width=3)
for py in range(y1, y2, step):
    d.line((x1, py, x1, min(py + seg, y2)), fill=ORANGE, width=3)
    d.line((x2, py, x2, min(py + seg, y2)), fill=ORANGE, width=3)

# 尺寸提示
d.text((x1 + 8, y1 + 6), "540 × 150", fill=ORANGE, font=font_size)

os.makedirs("docs", exist_ok=True)
img.save("docs/screenshot-mask.png")
print("docs/screenshot-mask.png generated")
