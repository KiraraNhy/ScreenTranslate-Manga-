"""Windows 自带 OCR（Windows.Media.Ocr）：免下载，识别已安装语言包的语种。"""

from __future__ import annotations

import asyncio
import io
from typing import Any

import numpy as np

from .base import OcrBackend, TextLine, rect_quad

_LANG_TAGS = {
    "ja": "ja",
    "en": "en",
    "ko": "ko",
    "zh": "zh-Hans",
    "zh-Hant": "zh-Hant",
    "fr": "fr",
    "de": "de",
    "es": "es",
    "it": "it",
    "pt": "pt",
    "ru": "ru",
    "ar": "ar",
    "th": "th",
    "vi": "vi",
}


class WindowsOcrBackend(OcrBackend):
    name = "windows"
    label = "Windows OCR 免下载"

    def __init__(self, lang: str = "auto", **options: Any) -> None:
        self.lang = lang
        self.options = options
        self._engine = None
        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------ 引擎
    @staticmethod
    def installed_languages() -> list[str]:
        try:
            from winsdk.windows.media.ocr import OcrEngine

            return [lang.language_tag for lang in OcrEngine.available_recognizer_languages]
        except Exception:
            return []

    def _ensure(self):
        if self._engine is not None:
            return self._engine
        from winsdk.windows.globalization import Language
        from winsdk.windows.media.ocr import OcrEngine

        engine = None
        if self.lang in ("auto", ""):
            engine = OcrEngine.try_create_from_user_profile_languages()
        else:
            tag = _LANG_TAGS.get(self.lang, self.lang)
            engine = OcrEngine.try_create_from_language(Language(tag))
            if engine is None:
                raise RuntimeError(
                    f"系统没有安装 {tag} 的 OCR 语言包。"
                    "请在 设置 > 时间和语言 > 语言和区域 里添加该语言后重试。"
                )
        if engine is None:
            raise RuntimeError("Windows OCR 无法创建识别引擎，请改用 PaddleOCR。")
        self._engine = engine
        return engine

    def warmup(self, lang: str = "auto") -> None:
        try:
            self._ensure()
        except Exception:
            pass

    def close(self) -> None:
        self._engine = None

    # ---------------------------------------------------------------- 识别
    def read(self, image: np.ndarray, lang: str = "auto") -> list[TextLine]:
        if self.lang in ("auto", "") and lang not in ("auto", ""):
            self.lang = lang
        loop = self._loop
        if loop is None or loop.is_closed():
            loop = asyncio.new_event_loop()
            self._loop = loop
        return loop.run_until_complete(self._read_async(image))

    async def _read_async(self, image: np.ndarray) -> list[TextLine]:
        from PIL import Image
        from winsdk.windows.graphics.imaging import BitmapDecoder
        from winsdk.windows.media.ocr import OcrEngine
        from winsdk.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

        engine = self._ensure()
        max_dim = OcrEngine.max_image_dimension
        pil = Image.fromarray(image)
        if max(pil.size) > max_dim:
            ratio = max_dim / float(max(pil.size))
            pil = pil.resize((int(pil.width * ratio), int(pil.height * ratio)))
        buffer = io.BytesIO()
        pil.save(buffer, format="PNG")

        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream)
        writer.write_bytes(buffer.getvalue())
        await writer.store_async()
        await writer.flush_async()
        stream.seek(0)

        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()
        result = await engine.recognize_async(bitmap)

        scale = image.shape[1] / float(pil.width)
        lines: list[TextLine] = []
        for line in result.lines:
            text = line.text
            if not text or not text.strip():
                continue
            xs: list[float] = []
            ys: list[float] = []
            for word in line.words:
                rect = word.bounding_rect
                xs += [rect.x * scale, (rect.x + rect.width) * scale]
                ys += [rect.y * scale, (rect.y + rect.height) * scale]
            if not xs:
                continue
            lines.append(
                TextLine(
                    text=text,
                    quad=rect_quad(min(xs), min(ys), max(xs), max(ys)),
                    conf=1.0,
                )
            )
        return self.clean(lines, min_height=0)
