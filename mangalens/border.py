"""选区提示描边：让用户随时看得见当前正在翻译的范围。"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from .blend import over

OUTLINE = (76, 201, 240)  # 亮蓝
CORNER = (255, 255, 255)
DEFAULT_THICKNESS = 3
DEFAULT_ALPHA = 165


def make_border(
    width: int,
    height: int,
    thickness: int = DEFAULT_THICKNESS,
    alpha: int = DEFAULT_ALPHA,
) -> np.ndarray:
    """生成一张"只有边框、中间透明"的 RGBA 图。"""

    width, height = max(1, int(width)), max(1, int(height))
    frame = np.zeros((height, width, 4), np.uint8)
    t = max(1, min(thickness, width // 4 or 1, height // 4 or 1))
    r, g, b = OUTLINE
    frame[:t, :, :] = (r, g, b, alpha)
    frame[height - t :, :, :] = (r, g, b, alpha)
    frame[:, :t, :] = (r, g, b, alpha)
    frame[:, width - t :, :] = (r, g, b, alpha)

    # 四个角加亮，画面花的时候也能看清边界
    cr, cg, cb = CORNER
    size = max(10, min(28, min(width, height) // 8))
    for ys, ye in ((0, size), (height - size, height)):
        for xs, xe in ((0, size), (width - size, width)):
            frame[ys:ye, xs:xs + t, :] = (cr, cg, cb, 235)
            frame[ys:ys + t, xs:xe, :] = (cr, cg, cb, 235)
    return frame


@lru_cache(maxsize=4)
def cached_border(width: int, height: int) -> np.ndarray:
    return make_border(width, height)


def apply_border(overlay: np.ndarray, border: np.ndarray) -> np.ndarray:
    """把描边叠到覆盖层最上层（覆盖层与描边尺寸一致）。"""

    if border is None or overlay.shape[:2] != border.shape[:2]:
        return overlay
    alpha = border[:, :, 3].astype(np.float32) / 255.0
    if not alpha.any():
        return overlay
    return over(overlay, border[:, :, :3], alpha)
