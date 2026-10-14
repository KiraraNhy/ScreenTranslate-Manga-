"""OCR 后端注册表。"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Callable

from .base import OcrBackend, TextLine, rect_quad


@dataclass
class _Entry:
    name: str
    label: str
    factory: Callable[..., OcrBackend]
    probe: Callable[[], bool]
    note: str = ""


_ENTRIES: dict[str, _Entry] = {}


def register(
    name: str,
    label: str,
    factory: Callable[..., OcrBackend],
    probe: Callable[[], bool],
    note: str = "",
) -> None:
    _ENTRIES[name] = _Entry(name, label, factory, probe, note)


def _has(*modules: str) -> Callable[[], bool]:
    def check() -> bool:
        return all(importlib.util.find_spec(m) is not None for m in modules)

    return check


def _manga_available() -> bool:
    if importlib.util.find_spec("manga_ocr") is None:
        return False
    # manga-ocr 只负责识别，需要搭配 PaddleOCR 的检测器
    return importlib.util.find_spec("paddleocr") is not None


def _tesseract_available() -> bool:
    import shutil

    return (
        importlib.util.find_spec("pytesseract") is not None
        and shutil.which("tesseract") is not None
    )


def _windows_available() -> bool:
    return importlib.util.find_spec("winsdk") is not None


def _make_paddle(**kw: object) -> OcrBackend:
    from .paddle_backend import PaddleBackend

    return PaddleBackend(**kw)  # type: ignore[arg-type]


def _make_rapid(**kw: object) -> OcrBackend:
    from .rapidocr_backend import RapidOcrBackend

    return RapidOcrBackend(**kw)  # type: ignore[arg-type]


def _make_manga(**kw: object) -> OcrBackend:
    from .manga_backend import MangaOcrBackend

    return MangaOcrBackend(**kw)  # type: ignore[arg-type]


def _make_windows(**kw: object) -> OcrBackend:
    from .windows_backend import WindowsOcrBackend

    return WindowsOcrBackend(**kw)  # type: ignore[arg-type]


def _make_tesseract(**kw: object) -> OcrBackend:
    from .tesseract_backend import TesseractBackend

    return TesseractBackend(**kw)  # type: ignore[arg-type]


register("manga-ocr", "manga-ocr 日漫专用", _make_manga, _manga_available)
register(
    "rapidocr",
    "RapidOCR 多语言",
    _make_rapid,
    _has("rapidocr", "onnxruntime"),
)
register("paddleocr", "PaddleOCR（实验）", _make_paddle, _has("paddleocr"))
register("windows", "Windows OCR 免下载", _make_windows, _windows_available)
register("tesseract", "Tesseract", _make_tesseract, _tesseract_available)

#: 选择顺序（按语言）
_PREFERENCE: dict[str, list[str]] = {
    "auto": ["windows", "rapidocr", "manga-ocr", "paddleocr", "tesseract"],
    "ja": ["rapidocr", "manga-ocr", "windows", "paddleocr", "tesseract"],
}
_DEFAULT_PREFERENCE = ["rapidocr", "windows", "paddleocr", "tesseract"]


def available_names() -> list[str]:
    return [name for name, entry in _ENTRIES.items() if entry.probe()]


def all_names() -> list[str]:
    return list(_ENTRIES)


def label_of(name: str) -> str:
    entry = _ENTRIES.get(name)
    return entry.label if entry else name


def choosable() -> list[str]:
    """界面上可选的引擎（含 auto）。"""

    return ["auto"] + all_names()


def auto_name(lang: str) -> str:
    order = _PREFERENCE.get(lang, _DEFAULT_PREFERENCE)
    for name in order:
        entry = _ENTRIES.get(name)
        if entry and entry.probe():
            return name
    usable = available_names()
    if usable:
        return usable[0]
    raise RuntimeError(
        "没有找到可用的识别引擎。请先运行 install.bat 安装依赖（PaddleOCR 或 Windows OCR）。"
    )


_CACHE: dict[tuple[str, str], OcrBackend] = {}


def create(name: str = "auto", lang: str = "auto", **kwargs: object) -> OcrBackend:
    """按名字取后端；name == 'auto' 时自动挑选。实例按 (引擎, 语言) 缓存。"""

    if name in ("auto", "", None):
        name = auto_name(lang)
    entry = _ENTRIES.get(name)
    if entry is None:
        raise ValueError(f"未知的识别引擎：{name}")
    key = (entry.name, lang)
    backend = _CACHE.get(key)
    if backend is None:
        backend = entry.factory(lang=lang, **kwargs)
        _CACHE[key] = backend
    return backend


__all__ = [
    "OcrBackend",
    "TextLine",
    "rect_quad",
    "available_names",
    "all_names",
    "choosable",
    "auto_name",
    "label_of",
    "create",
]
