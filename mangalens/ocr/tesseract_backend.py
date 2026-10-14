"""Tesseract 后端（需要单独安装 tesseract 程序）。"""

from __future__ import annotations

from typing import Any

import numpy as np

from .base import OcrBackend, TextLine

_LANG_MAP = {
    "ja": "jpn+jpn_vert",
    "en": "eng",
    "ko": "kor",
    "zh": "chi_sim",
    "zh-Hant": "chi_tra",
    "fr": "fra",
    "de": "deu",
    "es": "spa",
    "it": "ita",
    "pt": "por",
    "ru": "rus",
    "ar": "ara",
    "th": "tha",
    "vi": "vie",
}


class TesseractBackend(OcrBackend):
    name = "tesseract"
    label = "Tesseract"

    def __init__(self, lang: str = "auto", **options: Any) -> None:
        self.lang = lang
        self.options = options

    def read(self, image: np.ndarray, lang: str = "auto") -> list[TextLine]:
        import pytesseract
        from PIL import Image

        tess_lang = _LANG_MAP.get(lang if lang != "auto" else self.lang, "jpn")
        data = pytesseract.image_to_data(
            Image.fromarray(image),
            lang=tess_lang,
            output_type=pytesseract.Output.DICT,
            config="--psm 3",
        )
        groups: dict[tuple[int, int, int], list[int]] = {}
        for i, word in enumerate(data["text"]):
            if not word or not word.strip():
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            groups.setdefault(key, []).append(i)

        lines: list[TextLine] = []
        for indexes in groups.values():
            xs0 = min(data["left"][i] for i in indexes)
            ys0 = min(data["top"][i] for i in indexes)
            xs1 = max(data["left"][i] + data["width"][i] for i in indexes)
            ys1 = max(data["top"][i] + data["height"][i] for i in indexes)
            text = " ".join(data["text"][i].strip() for i in indexes)
            if tess_lang.startswith(("jpn", "chi", "kor")):
                text = text.replace(" ", "")
            lines.append(
                TextLine(
                    text=text,
                    quad=[
                        (xs0, ys0),
                        (xs1, ys0),
                        (xs1, ys1),
                        (xs0, ys1),
                    ],
                    conf=1.0,
                )
            )
        return self.clean(lines, min_height=0)
