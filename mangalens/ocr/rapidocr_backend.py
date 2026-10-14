"""RapidOCR 后端（ONNX Runtime，模型小、CPU 上快、多语言，不需要 Paddle 运行时）。"""

from __future__ import annotations

from typing import Any

import numpy as np

from .base import OcrBackend, TextLine

#: 内部语言码 -> (RapidOCR 识别语言, 识别模型版本)
#: 日文/繁体目前只有 PP-OCRv4 系列的识别模型
_SPECS: dict[str, tuple[str, str]] = {
    "auto": ("ch", "PP-OCRv5"),
    "ja": ("japan", "PP-OCRv4"),
    "en": ("en", "PP-OCRv5"),
    "ko": ("korean", "PP-OCRv5"),
    "zh": ("ch", "PP-OCRv5"),
    "zh-Hant": ("chinese_cht", "PP-OCRv4"),
    "fr": ("latin", "PP-OCRv5"),
    "de": ("latin", "PP-OCRv5"),
    "es": ("latin", "PP-OCRv5"),
    "it": ("latin", "PP-OCRv5"),
    "pt": ("latin", "PP-OCRv5"),
    "vi": ("latin", "PP-OCRv5"),
    "ru": ("cyrillic", "PP-OCRv5"),
    "ar": ("arabic", "PP-OCRv5"),
    "th": ("th", "PP-OCRv5"),
}

class RapidOcrBackend(OcrBackend):
    name = "rapidocr"
    label = "RapidOCR 多语言"

    def __init__(self, lang: str = "auto", **options: Any) -> None:
        self.lang = lang
        self.options = options
        self._engine = None
        self._det_engine = None

    # ------------------------------------------------------------------ 引擎
    def _params(self, det_only: bool = False) -> dict[str, Any]:
        from rapidocr import LangRec, ModelType, OCRVersion

        rec_lang, rec_version = _SPECS.get(self.lang, _SPECS["auto"])
        params: dict[str, Any] = {
            "Global.use_det": True,
            # 竖排日文用方向分类反而容易被转错，这里关掉，也更快
            "Global.use_cls": False,
            "Global.text_score": 0.4,
            "Global.log_level": "error",
            "Det.ocr_version": OCRVersion("PP-OCRv5"),
            "Det.model_type": ModelType("mobile"),
        }
        if det_only:
            params["Global.use_rec"] = False
        else:
            params.update(
                {
                    "Global.use_rec": True,
                    "Rec.lang_type": LangRec(rec_lang),
                    "Rec.ocr_version": OCRVersion(rec_version),
                    "Rec.model_type": ModelType("mobile"),
                }
            )
        params.update(
            {k: v for k, v in self.options.items() if isinstance(k, str) and "." in k}
        )
        return params

    def _ensure(self):
        if self._engine is None:
            from rapidocr import RapidOCR

            self._engine = RapidOCR(params=self._params())
        return self._engine

    def _detector(self):
        if self._det_engine is None:
            from rapidocr import RapidOCR

            self._det_engine = RapidOCR(params=self._params(det_only=True))
        return self._det_engine

    def warmup(self, lang: str = "auto") -> None:
        self._ensure()

    def close(self) -> None:
        self._engine = None
        self._det_engine = None

    # ---------------------------------------------------------------- 识别
    def read(self, image: np.ndarray, lang: str = "auto") -> list[TextLine]:
        import cv2

        result = self._ensure()(cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return []
        texts = getattr(result, "txts", None) or []
        scores = getattr(result, "scores", None) or []
        lines: list[TextLine] = []
        for index, box in enumerate(boxes):
            arr = np.asarray(box, dtype=float).reshape(-1, 2)
            if arr.shape[0] < 4:
                continue
            quad = [(float(x), float(y)) for x, y in arr]
            text = str(texts[index]) if index < len(texts) else ""
            conf = float(scores[index]) if index < len(scores) else 1.0
            lines.append(TextLine(text=text, quad=quad, conf=conf))
        return self.clean(lines)

    def detect(self, image: np.ndarray) -> list[list[tuple[float, float]]]:
        """只做检测，返回四边形（给 manga-ocr 之类的识别器用）。"""

        import cv2

        result = self._detector()(cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return []
        out: list[list[tuple[float, float]]] = []
        for box in boxes:
            arr = np.asarray(box, dtype=float).reshape(-1, 2)
            if arr.shape[0] >= 4:
                out.append([(float(x), float(y)) for x, y in arr])
        return out
