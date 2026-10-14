"""谷歌翻译（免费网页接口，无需密钥）。"""

from __future__ import annotations

import concurrent.futures
import re
from typing import Any

from .base import Translator

_ENDPOINTS = (
    "https://translate.googleapis.com/translate_a/single",
    "https://translate.google.com/translate_a/single",
)

# 内部语言码 -> 谷歌语言码
_CODE = {
    "zh": "zh-CN",
    "zh-Hant": "zh-TW",
    "auto": "auto",
}


def _code(lang: str) -> str:
    return _CODE.get(lang, lang)


class GoogleTranslator(Translator):
    name = "google"
    label = "谷歌翻译（免密钥）"

    def __init__(self, proxy: str = "", timeout: float = 12.0, workers: int = 6) -> None:
        import requests

        self.timeout = timeout
        self.workers = workers
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                )
            }
        )
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}

    # ------------------------------------------------------------------ 单条
    def _translate_one(self, text: str, src: str, dst: str) -> str:
        if not text.strip():
            return ""
        params = {
            "client": "gtx",
            "sl": _code(src),
            "tl": _code(dst),
            "dt": "t",
            "ie": "UTF-8",
            "oe": "UTF-8",
            "q": text,
        }
        last_error: Exception | None = None
        for endpoint in _ENDPOINTS:
            for _attempt in range(2):
                try:
                    resp = self.session.get(
                        endpoint, params=params, timeout=self.timeout
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    return "".join(
                        chunk[0] for chunk in data[0] if chunk and chunk[0]
                    )
                except Exception as exc:  # 网络抖动/被限流时换端点重试
                    last_error = exc
        raise RuntimeError(f"谷歌翻译请求失败：{last_error}")

    # ------------------------------------------------------------------ 批量
    def translate(self, texts: list[str], src: str = "auto", dst: str = "zh") -> list[str]:
        if not texts:
            return []
        results: list[str] = [""] * len(texts)
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(self.workers, len(texts))
        ) as pool:
            futures = {
                pool.submit(self._translate_one, text, src, dst): index
                for index, text in enumerate(texts)
            }
            for future in concurrent.futures.as_completed(futures):
                index = futures[future]
                try:
                    results[index] = self.normalize(future.result(), dst)
                except Exception:
                    results[index] = ""
        return results
