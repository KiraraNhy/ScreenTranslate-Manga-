"""屏幕采集。"""

from __future__ import annotations

import threading

import numpy as np

try:
    import mss
except ImportError:  # pragma: no cover - mss 缺失时退回 Pillow
    mss = None


def _grab_pillow(left: int, top: int, width: int, height: int) -> np.ndarray:
    from PIL import ImageGrab

    img = ImageGrab.grab(bbox=(left, top, left + width, top + height), all_screens=True)
    return np.asarray(img.convert("RGB"))


class Capturer:
    """按线程封装 mss（mss 实例不可跨线程共享）。"""

    def __init__(self) -> None:
        self._local = threading.local()
        self._use_mss = mss is not None

    def _sct(self):
        sct = getattr(self._local, "sct", None)
        if sct is None:
            sct = mss.mss()
            self._local.sct = sct
        return sct

    def grab(self, rect: tuple[int, int, int, int]) -> np.ndarray:
        """rect = (left, top, width, height) -> RGB uint8 数组。"""

        left, top, width, height = (int(v) for v in rect)
        if width <= 0 or height <= 0:
            raise ValueError("采集区域为空")
        if self._use_mss:
            try:
                shot = self._sct().grab(
                    {"left": left, "top": top, "width": width, "height": height}
                )
                return (
                    np.frombuffer(shot.rgb, dtype=np.uint8)
                    .reshape(height, width, 3)
                    .copy()
                )
            except Exception:
                self._use_mss = False
        return _grab_pillow(left, top, width, height)


def downscale_gray(frame: np.ndarray, width: int = 160) -> np.ndarray:
    """用于变化检测的缩略灰度图。"""

    import cv2

    h, w = frame.shape[:2]
    scale = width / float(w)
    small = cv2.resize(
        frame, (max(8, width), max(8, int(h * scale))), interpolation=cv2.INTER_AREA
    )
    return cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
