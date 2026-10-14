"""生成一张模拟漫画页面，用于本地测试（不联网）。"""

from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT_JP = r"C:\Windows\Fonts\NotoSansJP-VF.ttf"
FONT_CN = r"C:\Windows\Fonts\msyh.ttc"


def _font(path: str, size: int, index: int = 0):
    return ImageFont.truetype(path, size=size, index=index)


def _draw_horizontal_bubble(img: Image.Image, box, text: str, size: int = 30) -> None:
    draw = ImageDraw.Draw(img)
    draw.ellipse(box, fill=(255, 255, 255), outline=(40, 40, 40), width=3)
    font = _font(FONT_JP, size)
    x0, y0, x1, y1 = box
    lines = text.split("\n")
    line_h = size * 1.5
    y = y0 + (y1 - y0 - line_h * len(lines)) / 2
    for line in lines:
        width = draw.textlength(line, font=font)
        draw.text(((x0 + x1 - width) / 2, y), line, font=font, fill=(0, 0, 0))
        y += line_h


def _draw_vertical_bubble(img: Image.Image, box, text: str, size: int = 34) -> None:
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(box, radius=26, fill=(255, 255, 255), outline=(40, 40, 40), width=3)
    font = _font(FONT_JP, size)
    x0, y0, x1, y1 = box
    per_column = 6
    columns = [text[i : i + per_column] for i in range(0, len(text), per_column)]
    col_w = size * 1.35
    total_w = col_w * len(columns)
    start_x = x0 + (x1 - x0 - total_w) / 2
    for index, column in enumerate(columns):
        # 竖排日文从右往左读，第一列画在最右边
        x = start_x + (len(columns) - 1 - index) * col_w
        total_h = size * 1.4 * len(column)
        y = y0 + (y1 - y0 - total_h) / 2
        for ch in column:
            width = draw.textlength(ch, font=font)
            draw.text((x + (col_w - width) / 2, y), ch, font=font, fill=(0, 0, 0))
            y += size * 1.4


def build(path: Path) -> Path:
    random.seed(7)
    img = Image.new("RGB", (900, 1200), (232, 232, 228))
    draw = ImageDraw.Draw(img)

    # 背景图案，模拟漫画线条
    for _ in range(220):
        x = random.randint(0, 900)
        y = random.randint(0, 1200)
        length = random.randint(20, 160)
        angle_up = random.random() < 0.5
        draw.line(
            (x, y, x + length, y - length * 0.35 if angle_up else y + length * 0.35),
            fill=(205, 205, 200),
            width=random.choice([1, 2]),
        )
    for _ in range(14):
        x = random.randint(0, 860)
        y = random.randint(0, 1160)
        draw.ellipse((x, y, x + random.randint(40, 160), y + random.randint(30, 120)),
                     outline=(120, 120, 115), width=3)

    _draw_horizontal_bubble(
        img,
        (60, 70, 420, 250),
        "おはよう、今日はいい天気だね。",
    )
    _draw_vertical_bubble(img, (560, 120, 840, 620), "俺は海賊王になる男だ")
    _draw_horizontal_bubble(img, (90, 420, 470, 640), "なんだって！？\nそんなはずはない！", 32)

    # 旁白框（白底黑字，横排）
    draw.rectangle((70, 720, 830, 830), fill=(255, 255, 255), outline=(40, 40, 40), width=3)
    font = _font(FONT_JP, 30)
    draw.text((110, 765), "その日、世界は大きく変わった。", font=font, fill=(0, 0, 0))

    # 黑底白字的英文标题
    draw.rectangle((0, 1080, 900, 1200), fill=(24, 24, 28))
    font_en = _font(FONT_CN, 40)
    draw.text((60, 1120), "TO BE CONTINUED", font=font_en, fill=(240, 240, 240))

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


if __name__ == "__main__":
    out = build(ROOT / "tests" / "sample_ja.png")
    print(out)
