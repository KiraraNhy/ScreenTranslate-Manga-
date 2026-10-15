"""选区提示描边：常驻显示选区，颜色表示运行状态。"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from .blend import over

#: 翻译中（绿）
RUNNING = (46, 204, 113)
#: 已暂停（红）
PAUSED = (231, 76, 60)
DEFAULT_THICKNESS = 3
DEFAULT_ALPHA = 170


def color_for(enabled: bool) -> tuple[int, int, int]:
    """按运行状态取描边颜色。"""

    return RUNNING if enabled else PAUSED


def make_border(
    width: int,
    height: int,
    color: tuple[int, int, int] = RUNNING,
    thickness: int = DEFAULT_THICKNESS,
    alpha: int = DEFAULT_ALPHA,
) -> np.ndarray:
    """生成一张"只有一圈边框、中间透明"的 RGBA 图。"""

    width, height = max(1, int(width)), max(1, int(height))
    frame = np.zeros((height, width, 4), np.uint8)
    t = max(1, min(int(thickness), width // 4 or 1, height // 4 or 1))
    r, g, b = color
    frame[:t, :, :] = (r, g, b, alpha)
    frame[height - t :, :, :] = (r, g, b, alpha)
    frame[:, :t, :] = (r, g, b, alpha)
    frame[:, width - t :, :] = (r, g, b, alpha)
    return frame


@lru_cache(maxsize=8)
def cached_border(
    width: int, height: int, color: tuple[int, int, int] = RUNNING
) -> np.ndarray:
    return make_border(width, height, color)


def apply_border(overlay: np.ndarray, border: np.ndarray) -> np.ndarray:
    """把描边叠到覆盖层最上层（覆盖层与描边尺寸一致）。"""

    if border is None or overlay.shape[:2] != border.shape[:2]:
        return overlay
    alpha = border[:, :, 3].astype(np.float32) / 255.0
    if not alpha.any():
        return overlay
    return over(overlay, border[:, :, :3], alpha)
