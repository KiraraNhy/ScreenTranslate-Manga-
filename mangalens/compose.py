"""把译文画回原文位置：先抹掉原文，再按框的大小排版中文。"""

from __future__ import annotations

import re
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .blend import over
from .fonts import load_font, resolve_font
from .layout import Block

_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")


@dataclass
class Style:
    font_path: str = ""
    font_scale: float = 1.0
    erase_original: bool = True
    outline: bool = True
    #: 中文一律横排（从左到右、从上到下），不跟随日文竖排
    force_horizontal: bool = True
    pad_ratio: float = 0.05
    min_font: int = 7
    max_font: int = 96
    feather: int = 3


def _ring_color(frame: np.ndarray, box: tuple[float, float, float, float], margin: int = 3):
    """取文本框外侧一圈像素的中位色，用来判断周围是不是对话框的底色。"""

    height, width = frame.shape[:2]
    x0, y0, x1, y1 = (int(v) for v in box)
    strips = []
    for ya, yb, xa, xb in (
        (y0 - margin, y0, x0, x1),
        (y1, y1 + margin, x0, x1),
        (y0, y1, x0 - margin, x0),
        (y0, y1, x1, x1 + margin),
    ):
        ya, yb = max(0, ya), min(height, yb)
        xa, xb = max(0, xa), min(width, xb)
        if yb > ya and xb > xa:
            strips.append(frame[ya:yb, xa:xb].reshape(-1, 3))
    if not strips:
        return None
    pixels = np.concatenate(strips).astype(np.float32)
    return tuple(float(v) for v in np.median(pixels, axis=0))


def _expand_box_horizontal(
    frame: np.ndarray,
    box: tuple[int, int, int, int],
    bg: tuple[float, float, float],
    max_ratio: float = 0.4,
    step: int = 6,
    tolerance: float = 46.0,
    min_similar: float = 0.88,
) -> tuple[int, int, int, int]:
    """竖排文件框改成横排时，向左右借用对话框里的空白，避免字被挤小。"""

    height, width = frame.shape[:2]
    x0, y0, x1, y1 = box
    reference = np.array(bg, np.int16)
    limit = int(round((x1 - x0) * max_ratio))

    def usable(xa: int, xb: int) -> bool:
        if xb <= xa or xa < 0 or xb > width or y1 <= y0:
            return False
        strip = frame[y0:y1, xa:xb].reshape(-1, 3).astype(np.int16)
        if strip.size == 0:
            return False
        diff = np.abs(strip - reference).mean(axis=1)
        return float((diff <= tolerance).mean()) >= min_similar

    for side in ("left", "right"):
        grown = 0
        while grown < limit:
            take = min(step, limit - grown)
            if side == "left":
                if not usable(x0 - take, x0):
                    break
                x0 -= take
            else:
                if not usable(x1, x1 + take):
                    break
                x1 += take
            grown += take
    return x0, y0, x1, y1


# --------------------------------------------------------------------- 工具
def _is_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text))


def _flatten(text: str) -> str:
    """去掉换行：中文直接连起来，英文用空格。"""

    joiner = "" if _is_cjk(text) else " "
    return re.sub(r"\s*\n\s*", joiner, text.strip())


def _text_metrics(font: ImageFont.FreeTypeFont) -> tuple[float, float]:
    ascent, descent = font.getmetrics()
    return float(ascent), float(descent)


def _wrap_horizontal(
    text: str, font: ImageFont.FreeTypeFont, box_w: float, box_h: float
) -> list[str] | None:
    ascent, descent = _text_metrics(font)
    line_h = ascent + descent
    spacing = max(1.0, line_h * 0.08)
    max_lines = int((box_h + spacing) // (line_h + spacing))
    if max_lines < 1:
        return None
    lines: list[str] = []
    current = ""
    for ch in text:
        candidate = current + ch
        if current and font.getlength(candidate) > box_w:
            break_at = -1
            if not _is_cjk(ch):
                break_at = current.rfind(" ")
            if break_at > 0:
                lines.append(current[:break_at])
                current = current[break_at + 1 :] + ch
            else:
                lines.append(current)
                current = ch
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        return None
    for line in lines:
        if font.getlength(line) > box_w * 1.02:
            return None
    return lines


def _wrap_vertical(
    text: str, font: ImageFont.FreeTypeFont, box_w: float, box_h: float
) -> list[str] | None:
    ascent, descent = _text_metrics(font)
    char_h = ascent + descent
    probe = "国" if _is_cjk(text) else "M"
    char_w = max(1.0, font.getlength(probe))
    rows = int(box_h // char_h)
    cols = int(box_w // char_w)
    if rows < 1 or cols < 1:
        return None
    if len(text) > rows * cols:
        return None
    columns = [text[i * rows : (i + 1) * rows] for i in range(cols)]
    return [col for col in columns if col]


def _fit_text(
    text: str,
    box_w: float,
    box_h: float,
    style: Style,
    vertical: bool,
    max_size: int,
) -> tuple[ImageFont.FreeTypeFont, list[str], bool] | None:
    path, index = resolve_font(style.font_path)
    limit = max(style.min_font, min(int(max_size), style.max_font))
    for size in range(limit, style.min_font - 1, -1):
        font = load_font(size, path, index)
        layout = (
            _wrap_vertical(text, font, box_w, box_h)
            if vertical
            else _wrap_horizontal(text, font, box_w, box_h)
        )
        if layout:
            return font, layout, vertical
    # 实在放不下就用最小字号，允许轻微溢出
    font = load_font(style.min_font, path, index)
    layout = (
        _wrap_vertical(text, font, box_w * 1.5, box_h * 1.2)
        if vertical
        else _wrap_horizontal(text, font, box_w * 1.2, box_h * 1.5)
    )
    if not layout:
        layout = [text]
    return font, layout, vertical


def _draw_lines(
    image: Image.Image,
    font: ImageFont.FreeTypeFont,
    layout: list[str],
    vertical: bool,
    fg: tuple[int, int, int],
    bg: tuple[int, int, int],
    outline: bool,
) -> None:
    draw = ImageDraw.Draw(image)
    w, h = image.size
    ascent, descent = _text_metrics(font)
    char_h = ascent + descent
    stroke = 1 if outline else 0
    if vertical:
        probe = "国" if _is_cjk("".join(layout)) else "M"
        char_w = max(1.0, font.getlength(probe))
        total_w = char_w * len(layout)
        start_x = (w - total_w) / 2 + char_w / 2
        for col_index, column in enumerate(layout):
            cx = start_x + col_index * char_w
            total_h = char_h * len(column)
            start_y = (h - total_h) / 2 + char_h / 2
            for row_index, ch in enumerate(column):
                cy = start_y + row_index * char_h
                draw.text(
                    (cx, cy),
                    ch,
                    font=font,
                    fill=fg,
                    anchor="mm",
                    stroke_width=stroke,
                    stroke_fill=bg,
                )
    else:
        spacing = max(1.0, char_h * 0.08)
        total_h = char_h * len(layout) + spacing * (len(layout) - 1)
        y = (h - total_h) / 2
        for line in layout:
            draw.text(
                (w / 2, y + char_h / 2),
                line,
                font=font,
                fill=fg,
                anchor="mm",
                stroke_width=stroke,
                stroke_fill=bg,
            )
            y += char_h + spacing


# --------------------------------------------------------------------- 主体
def _mask_of_block(
    block: Block,
    offset: tuple[int, int],
    size: tuple[int, int],
    dilate: int,
) -> np.ndarray:
    width, height = size
    mask = np.zeros((height, width), np.uint8)
    ox, oy = offset
    for quad in block.quads():
        points = np.array(
            [[int(round(x - ox)), int(round(y - oy))] for x, y in quad], np.int32
        )
        cv2.fillPoly(mask, [points], 255)
    if dilate > 1:
        kernel = np.ones((dilate, dilate), np.uint8)
        mask = cv2.dilate(mask, kernel, iterations=1)
    return mask


def _colors(crop_bgr: np.ndarray, mask: np.ndarray) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """估计原文颜色（前景）和对话框底色（背景）。"""

    inside = mask > 0
    if not inside.any():
        return (0, 0, 0), (255, 255, 255)
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    values = gray[inside]
    threshold, _ = cv2.threshold(
        values.reshape(-1, 1), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    dark = inside & (gray <= threshold)
    light = inside & (gray > threshold)
    if dark.sum() <= light.sum():
        fg_mask, fg_pixels = dark, crop_bgr[dark]
    else:
        fg_mask, fg_pixels = light, crop_bgr[light]
    outside = ~inside
    bg_pixels = crop_bgr[outside] if outside.any() else crop_bgr.reshape(-1, 3)

    def median_rgb(pixels: np.ndarray) -> tuple[int, int, int]:
        if pixels.size == 0:
            return (255, 255, 255)
        b, g, r = np.median(pixels.reshape(-1, 3), axis=0)
        return (int(r), int(g), int(b))

    bg = median_rgb(bg_pixels)
    fg = median_rgb(fg_pixels) if fg_pixels.size else (0, 0, 0)
    if sum(abs(a - b) for a, b in zip(fg, bg)) < 60:
        # 对比度太低，退回黑字
        fg = (0, 0, 0) if sum(bg) > 384 else (255, 255, 255)
    return fg, bg


def _feather_alpha(width: int, height: int, feather: int) -> np.ndarray:
    alpha = np.ones((height, width), np.float32)
    feather = int(max(0, min(feather, width // 3, height // 3)))
    if feather > 0:
        ramp = np.linspace(0.0, 1.0, feather + 1, dtype=np.float32)[1:]
        alpha[:feather, :] *= ramp[:, None]
        alpha[-feather:, :] *= ramp[::-1][:, None]
        alpha[:, :feather] *= ramp[None, :]
        alpha[:, -feather:] *= ramp[::-1][None, :]
    return (alpha * 255.0).astype(np.uint8)


@dataclass
class LayoutPlan:
    """一段译文的排版结果：画在哪、横排还是竖排、用多大字号、怎么断行。"""

    box: tuple[int, int, int, int]
    vertical: bool
    font: ImageFont.FreeTypeFont
    lines: list[str]


def plan_layout(frame_rgb: np.ndarray, block: Block, style: Style) -> LayoutPlan | None:
    """决定译文的位置与排版（不含颜色与绘制）。"""

    text = block.text_dst.strip()
    if not text:
        return None
    height, width = frame_rgb.shape[:2]
    x0, y0, x1, y1 = block.bbox
    pad = max(3, int(style.pad_ratio * max(x1 - x0, y1 - y0)))
    x0 = max(0, int(x0) - pad)
    y0 = max(0, int(y0) - pad)
    x1 = min(width, int(np.ceil(x1)) + pad)
    y1 = min(height, int(np.ceil(y1)) + pad)
    if x1 - x0 < 6 or y1 - y0 < 6:
        return None

    # 竖排日文改成横排中文时，先向左右借用对话框内部的空白
    if style.force_horizontal and block.vertical:
        ring = _ring_color(frame_rgb, block.bbox)
        if ring is not None:
            x0, y0, x1, y1 = _expand_box_horizontal(frame_rgb, (x0, y0, x1, y1), ring)

    box_w = (x1 - x0) * 0.92
    box_h = (y1 - y0) * 0.92
    vertical = (
        not style.force_horizontal
        and block.vertical
        and (y1 - y0) >= (x1 - x0) * 0.6
    )
    # 原文的字号：横排看行高，竖排看列宽
    char_size = float(
        np.median(
            [max(1.0, ln.width) for ln in block.lines]
            if block.vertical
            else [max(1.0, ln.height) for ln in block.lines]
        )
    )
    max_size = int(
        min(
            char_size * 1.4 * style.font_scale,
            box_h,
            box_w * (1.0 if vertical else 1.1),
        )
    )
    fitted = _fit_text(_flatten(text), box_w, box_h, style, vertical, max_size)
    if fitted is None:
        return None
    font, layout, vertical = fitted
    return LayoutPlan((x0, y0, x1, y1), vertical, font, layout)


def render_block(
    frame_rgb: np.ndarray,
    block: Block,
    style: Style,
) -> tuple[np.ndarray, tuple[int, int]] | None:
    """生成单个文本块的贴图（RGBA）及其在整帧中的左上角坐标。"""

    plan = plan_layout(frame_rgb, block, style)
    if plan is None:
        return None
    x0, y0, x1, y1 = plan.box
    crop = frame_rgb[y0:y1, x0:x1]
    crop_bgr = cv2.cvtColor(crop, cv2.COLOR_RGB2BGR)
    line_h = float(np.median([max(1.0, ln.height) for ln in block.lines]))
    dilate = int(max(3, min(15, round(line_h * 0.45)))) | 1
    mask = _mask_of_block(block, (x0, y0), (x1 - x0, y1 - y0), dilate)
    fg, bg = _colors(crop_bgr, mask)

    if style.erase_original:
        patch_bgr = cv2.inpaint(crop_bgr, mask, max(2, dilate // 2), cv2.INPAINT_TELEA)
    else:
        patch_bgr = crop_bgr.copy()
        patch_bgr[mask > 0] = (bg[2], bg[1], bg[0])

    patch = Image.fromarray(cv2.cvtColor(patch_bgr, cv2.COLOR_BGR2RGB))
    _draw_lines(patch, plan.font, plan.lines, plan.vertical, fg, bg, style.outline)

    rgba = np.dstack(
        [
            np.asarray(patch),
            _feather_alpha(x1 - x0, y1 - y0, style.feather),
        ]
    )
    return rgba, (x0, y0)


def compose(
    frame_rgb: np.ndarray,
    blocks: list[Block],
    style: Style | None = None,
    skip_rects: list[tuple[int, int, int, int]] | None = None,
) -> np.ndarray:
    """返回整帧大小的 RGBA 覆盖层。"""

    style = style or Style()
    height, width = frame_rgb.shape[:2]
    overlay = np.zeros((height, width, 4), np.uint8)
    for block in blocks:
        if not block.text_dst:
            continue
        if skip_rects and _overlaps(block.bbox, skip_rects):
            continue
        rendered = render_block(frame_rgb, block, style)
        if rendered is None:
            continue
        patch, (px, py) = rendered
        ph, pw = patch.shape[:2]
        overlay[py : py + ph, px : px + pw] = over(
            overlay[py : py + ph, px : px + pw],
            patch[:, :, :3],
            patch[:, :, 3].astype(np.float32) / 255.0,
        )
    return overlay


def _overlaps(
    box: tuple[float, float, float, float],
    rects: list[tuple[int, int, int, int]],
    margin: int = 0,
) -> bool:
    for x0, y0, w, h in rects:
        if box[0] < x0 + w + margin and box[2] > x0 - margin and box[1] < y0 + h + margin and box[3] > y0 - margin:
            return True
    return False
