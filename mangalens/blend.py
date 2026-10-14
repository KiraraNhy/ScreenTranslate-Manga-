"""直通（straight）alpha 合成。

覆盖层的像素要按"颜色 + alpha"两个通道正确合成，不能直接用 a*c + (1-a)*c'，
否则半透明区域（描边、贴图羽化边）会因为重复预乘而发暗，在画面里留下一圈暗边。
"""

from __future__ import annotations

import numpy as np


def over(dst: np.ndarray, src_rgb: np.ndarray, src_alpha: np.ndarray) -> np.ndarray:
    """把 src 叠到 dst 上，返回新数组。

    dst:       (h, w, 4) uint8，直通 RGBA
    src_rgb:   (h, w, 3) uint8
    src_alpha: (h, w) 或 (h, w, 1)，0..1 的浮点
    """

    alpha = src_alpha.astype(np.float32)
    if alpha.ndim == 2:
        alpha = alpha[:, :, None]
    dst_alpha = dst[:, :, 3:4].astype(np.float32) / 255.0
    out_alpha = alpha + dst_alpha * (1.0 - alpha)
    safe = np.maximum(out_alpha, 1e-6)
    rgb = (
        src_rgb.astype(np.float32) * alpha
        + dst[:, :, :3].astype(np.float32) * dst_alpha * (1.0 - alpha)
    ) / safe
    out = np.empty_like(dst)
    out[:, :, :3] = np.clip(rgb, 0.0, 255.0).astype(np.uint8)
    out[:, :, 3:4] = np.clip(out_alpha * 255.0, 0.0, 255.0).astype(np.uint8)
    return out
