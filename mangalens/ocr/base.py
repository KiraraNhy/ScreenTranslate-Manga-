"""OCR 通用数据结构与接口。"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class TextLine:
    """一段被识别出来的文字（一行/一列）。"""

    text: str
    quad: list[tuple[float, float]]
    conf: float = 1.0
    vertical: bool = False

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        xs = [p[0] for p in self.quad]
        ys = [p[1] for p in self.quad]
        return min(xs), min(ys), max(xs), max(ys)

    @property
    def width(self) -> float:
        x0, _, x1, _ = self.bbox
        return x1 - x0

    @property
    def height(self) -> float:
        _, y0, _, y1 = self.bbox
        return y1 - y0

    @property
    def center(self) -> tuple[float, float]:
        x0, y0, x1, y1 = self.bbox
        return (x0 + x1) / 2, (y0 + y1) / 2


def rect_quad(x0: float, y0: float, x1: float, y1: float) -> list[tuple[float, float]]:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


class OcrBackend:
    """OCR 后端接口。lang 可以是具体语言码，也可以是 'auto'。"""

    name = "base"
    label = "基础"

    def read(self, image: np.ndarray, lang: str = "auto") -> list[TextLine]:
        raise NotImplementedError

    def warmup(self, lang: str = "auto") -> None:
        """提前加载模型，避免第一次识别卡顿。"""

    def close(self) -> None:
        pass

    # ------------------------------------------------------------------ 工具
    @staticmethod
    def clean(lines: list[TextLine], min_height: float = 0.0) -> list[TextLine]:
        out: list[TextLine] = []
        for line in lines:
            text = (line.text or "").strip()
            if not text:
                continue
            if line.height < min_height or line.width < 2:
                continue
            line.text = text
            line.vertical = line.vertical or line.height > line.width * 1.4
            out.append(line)
        return out
