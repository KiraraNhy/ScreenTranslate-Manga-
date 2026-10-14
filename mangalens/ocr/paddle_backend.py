"""PaddleOCR 后端：多语言、支持竖排 CJK。"""

from __future__ import annotations

import os
from typing import Any

import numpy as np

from .base import OcrBackend, TextLine, rect_quad

# 内部语言码 -> PaddleOCR lang
_LANG_MAP = {
    "ja": "japan",
    "en": "en",
    "ko": "korean",
    "zh": "ch",
    "zh-Hant": "chinese_cht",
    "fr": "latin",
    "de": "latin",
    "es": "latin",
    "it": "latin",
    "pt": "latin",
    "vi": "latin",
    "ru": "cyrillic",
    "ar": "arabic",
    "th": "th",
}


class PaddleBackend(OcrBackend):
    name = "paddleocr"
    label = "PaddleOCR（实验）"

    def __init__(self, lang: str = "auto", det_only: bool = False, **options: Any) -> None:
        self.lang = lang
        # 自动检测时默认按日语处理（漫画场景最常见）
        self.paddle_lang = _LANG_MAP.get(lang, "japan" if lang == "auto" else "en")
        self.det_only = det_only
        self.options = options
        self.ocr_version = options.get("ocr_version") or os.environ.get(
            "MANGALENS_PADDLE_VERSION", "PP-OCRv5"
        )
        self._engine = None
        self._device = self._pick_device()

    @staticmethod
    def _pick_device() -> str:
        """PaddlePaddle 若有 GPU 就用 GPU，否则 CPU。"""

        if os.environ.get("MANGALENS_PADDLE_DEVICE"):
            return os.environ["MANGALENS_PADDLE_DEVICE"]
        try:
            import paddle

            if paddle.device.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0:
                return "gpu"
        except Exception:
            pass
        return "cpu"

    # ------------------------------------------------------------------ 引擎
    def _ensure(self):
        if self._engine is not None:
            return self._engine

        # 模型下载源：国内默认走 ModelScope
        os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "modelscope")

        from paddleocr import PaddleOCR

        kwargs: dict[str, Any] = dict(
            lang=self.paddle_lang,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=True,
            device=self._device,
        )
        if self.ocr_version:
            kwargs["ocr_version"] = self.ocr_version
        try:
            self._engine = PaddleOCR(**kwargs)
        except TypeError:
            kwargs.pop("device", None)
            kwargs.pop("use_doc_unwarping", None)
            self._engine = PaddleOCR(**kwargs)
        return self._engine

    def warmup(self, lang: str = "auto") -> None:
        self._ensure()

    def close(self) -> None:
        self._engine = None

    # ---------------------------------------------------------------- 识别
    def read(self, image: np.ndarray, lang: str = "auto") -> list[TextLine]:
        import cv2

        engine = self._ensure()
        bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        raw = engine.predict(bgr)
        return self.clean(self._parse(raw), min_height=0)

    def detect(self, image: np.ndarray) -> list[list[tuple[float, float]]]:
        """只做文本框检测，返回四边形列表。"""

        import cv2

        engine = self._ensure()
        bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        raw = engine.predict(bgr)
        out: list[list[tuple[float, float]]] = []
        for data in self._iter_payloads(raw):
            for poly in data.get("dt_polys") or data.get("rec_polys") or []:
                arr = np.asarray(poly, dtype=float)
                if arr.ndim == 2 and arr.shape[0] >= 3:
                    out.append([(float(x), float(y)) for x, y in arr[:, :2]])
        return out

    # ---------------------------------------------------------------- 解析
    @staticmethod
    def _iter_payloads(raw: Any):
        """兼容 PaddleOCR 2.x/3.x 的返回结构。"""

        def to_dict(item: Any) -> dict | None:
            if isinstance(item, dict):
                inner = item.get("res")
                return inner if isinstance(inner, dict) else item
            for attr in ("json", "res"):
                value = getattr(item, attr, None)
                if isinstance(value, dict):
                    inner = value.get("res")
                    return inner if isinstance(inner, dict) else value
            return None

        if raw is None:
            return
        if isinstance(raw, list) and raw and isinstance(raw[0], list) and raw[0]:
            # 2.x: [[ [box, (text, score)], ... ]]
            payload = {
                "dt_polys": [item[0] for item in raw[0]],
                "rec_texts": [item[1][0] for item in raw[0]],
                "rec_scores": [item[1][1] for item in raw[0]],
            }
            yield payload
            return
        items = raw if isinstance(raw, list) else [raw]
        for item in items:
            data = to_dict(item)
            if data:
                yield data

    def _parse(self, raw: Any) -> list[TextLine]:
        lines: list[TextLine] = []
        for data in self._iter_payloads(raw):
            polys = data.get("dt_polys")
            if polys is None:
                polys = data.get("rec_polys") or []
            texts = list(data.get("rec_texts") or [])
            scores = list(data.get("rec_scores") or [])
            for index, poly in enumerate(polys):
                arr = np.asarray(poly, dtype=float)
                if arr.ndim != 2 or arr.shape[0] < 3:
                    continue
                quad = [(float(x), float(y)) for x, y in arr[:, :2]]
                text = texts[index] if index < len(texts) else ""
                conf = float(scores[index]) if index < len(scores) else 1.0
                lines.append(TextLine(text=str(text), quad=quad, conf=conf))
        return lines
