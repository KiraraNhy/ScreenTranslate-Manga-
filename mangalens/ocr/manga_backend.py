"""manga-ocr 后端：日漫文字识别质量最好，用 PaddleOCR 的检测框做定位。"""

from __future__ import annotations

from typing import Any

import numpy as np

from .base import OcrBackend, TextLine, rect_quad


class MangaOcrBackend(OcrBackend):
    name = "manga-ocr"
    label = "manga-ocr 日漫专用"

    def __init__(self, lang: str = "ja", det_backend=None, **options: Any) -> None:
        self.lang = lang
        self.options = options
        self._model = None
        self._det = det_backend

    # ------------------------------------------------------------------ 模型
    def _detector(self):
        if self._det is None:
            # 优先用 RapidOCR 的检测器（轻量、无需 Paddle 运行时）
            import importlib.util

            if importlib.util.find_spec("rapidocr") is not None:
                from .rapidocr_backend import RapidOcrBackend

                self._det = RapidOcrBackend(lang="ja")
            else:
                from .paddle_backend import PaddleBackend

                self._det = PaddleBackend(lang="ja", det_only=True)
        return self._det

    def _ensure(self):
        if self._model is None:
            import os

            import torch

            # manga-ocr 的模型在 HuggingFace 上，国内默认走镜像
            os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
            from manga_ocr import MangaOcr

            device = "cpu"
            try:
                if torch.cuda.is_available():
                    device = "cuda"
            except Exception:
                device = "cpu"
            try:
                self._model = MangaOcr(device=device)
            except Exception as exc:
                raise RuntimeError(
                    f"manga-ocr 模型加载失败（首次需要下载约 400MB）：{exc}"
                ) from exc
        return self._model

    def warmup(self, lang: str = "auto") -> None:
        self._ensure()
        self._detector().warmup("ja")

    def close(self) -> None:
        self._model = None
        if self._det is not None:
            self._det.close()
            self._det = None

    # ---------------------------------------------------------------- 识别
    def read(self, image: np.ndarray, lang: str = "auto") -> list[TextLine]:
        from PIL import Image

        model = self._ensure()
        quads = self._detector().detect(image)
        h, w = image.shape[:2]
        pil = Image.fromarray(image)
        lines: list[TextLine] = []
        for quad in quads:
            xs = [p[0] for p in quad]
            ys = [p[1] for p in quad]
            x0 = max(0, int(min(xs)) - 2)
            y0 = max(0, int(min(ys)) - 2)
            x1 = min(w, int(max(xs)) + 2)
            y1 = min(h, int(max(ys)) + 2)
            if x1 - x0 < 4 or y1 - y0 < 4:
                continue
            crop = pil.crop((x0, y0, x1, y1))
            try:
                text = model(crop)
            except Exception:
                continue
            if text:
                lines.append(TextLine(text=text, quad=quad, conf=1.0))
        return self.clean(lines, min_height=0)
