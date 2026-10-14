"""MyMemory 免费翻译接口（免密钥，国内可直连）。

限制：每次请求原文不超过 500 字节；匿名每天约 5000 字符，
填了邮箱（设置里的 email 字段）约 50000 字符。
"""

from __future__ import annotations

import concurrent.futures
import re
import threading
import time

from .base import Translator

_ENDPOINT = "https://api.mymemory.translated.net/get"

#: 内部语言码 -> MyMemory 语言码
_CODE = {
    "zh": "zh-CN",
    "zh-Hant": "zh-TW",
    "auto": "ja",
    "ja": "ja",
    "en": "en",
    "ko": "ko",
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

_QUOTA_HINT = ("MYMEMORY WARNING", "YOU USED ALL AVAILABLE", "QUERY LENGTH LIMIT")
_SPLIT_RE = re.compile(r"(?<=[。．！？!?…])")
_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")

#: 单次请求的原文上限（接口限制 500 字节），留点余量
_BUDGET = 450


def _one_line(text: str) -> str:
    """把一段话压成一行：接口会按行原样返回，这样才能一条请求翻多段。"""

    joiner = "" if _CJK_RE.search(text) else " "
    return re.sub(r"\s*\n\s*", joiner, text.strip())


def _group(texts: list[str]) -> list[list[int]]:
    """按字节预算分组，尽量用最少的请求数翻完整页。"""

    groups: list[list[int]] = []
    current: list[int] = []
    size = 0
    for index, text in enumerate(texts):
        length = len(_one_line(text).encode("utf-8")) + 1
        if current and size + length > _BUDGET:
            groups.append(current)
            current, size = [], 0
        current.append(index)
        size += length
    if current:
        groups.append(current)
    return groups


def _chunks(text: str, limit: int = 480) -> list[str]:
    """按句子切分，保证每段不超过 limit 字节。"""

    if len(text.encode("utf-8")) <= limit:
        return [text]
    parts: list[str] = []
    current = ""
    for piece in _SPLIT_RE.split(text):
        if not piece:
            continue
        candidate = current + piece
        if len(candidate.encode("utf-8")) > limit and current:
            parts.append(current)
            current = piece
        else:
            current = candidate
    if current:
        parts.append(current)
    out: list[str] = []
    for part in parts:
        while len(part.encode("utf-8")) > limit:
            cut = limit // 3
            out.append(part[:cut])
            part = part[cut:]
        if part:
            out.append(part)
    return out


class MyMemoryTranslator(Translator):
    name = "mymemory"
    label = "MyMemory（免费免密钥）"

    def __init__(
        self,
        email: str = "",
        proxy: str = "",
        timeout: float = 12.0,
        workers: int = 5,
    ) -> None:
        import requests

        self.timeout = timeout
        self.workers = max(1, int(workers))
        self.email = email
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "MangaLens/0.1 (screen translation)"})
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}
        self._lock = threading.Lock()
        self._next_call = 0.0
        self.quota_exhausted = False

    def _throttle(self, interval: float = 0.12) -> None:
        with self._lock:
            now = time.monotonic()
            wait = self._next_call - now
            self._next_call = max(now, self._next_call) + interval
        if wait > 0:
            time.sleep(wait)

    def _request(self, text: str, src: str, dst: str) -> str:
        params = {
            "q": text,
            "langpair": f"{_CODE.get(src, src)}|{_CODE.get(dst, dst)}",
        }
        if self.email:
            params["de"] = self.email
        self._throttle()
        resp = self.session.get(_ENDPOINT, params=params, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        status = int(data.get("responseStatus", 200))
        translated = (data.get("responseData") or {}).get("translatedText") or ""
        upper = translated.upper()
        if any(hint in upper for hint in _QUOTA_HINT):
            self.quota_exhausted = True
            raise RuntimeError(
                "MyMemory 免费额度用完了（每天约 5000 字符）。"
                "可以在设置里填一个邮箱提高到 5 万字符，"
                "或改用大模型 / 本地离线模型。"
            )
        if status != 200 or not translated:
            raise RuntimeError(f"MyMemory 返回异常（{status}）")
        return translated

    def translate(self, texts: list[str], src: str = "auto", dst: str = "zh") -> list[str]:
        results: list[str] = [""] * len(texts)
        if not texts or self.quota_exhausted:
            return results

        def translate_group(indexes: list[int]) -> None:
            lines = [_one_line(texts[i]) for i in indexes]
            if len(indexes) == 1:
                text = lines[0]
                if not text:
                    return
                results[indexes[0]] = self.normalize(
                    "".join(self._request(c, src, dst) for c in _chunks(text)), dst
                )
                return
            try:
                raw = self._request("\n".join(lines), src, dst)
            except Exception:
                raw = ""
            parts = [p for p in (raw or "").split("\n") if p.strip()]
            if len(parts) == len(indexes):
                for index, part in zip(indexes, parts):
                    results[index] = self.normalize(part.strip(), dst)
                return
            # 行数对不上（翻译引擎改动了换行），退回逐条请求，保证不错位
            for index, line in zip(indexes, lines):
                if not line:
                    continue
                try:
                    results[index] = self.normalize(self._request(line, src, dst), dst)
                except Exception:
                    results[index] = ""

        groups = _group(texts)
        if self.workers == 1 or len(groups) == 1:
            for group in groups:
                translate_group(group)
            return results
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(self.workers, len(groups))
        ) as pool:
            list(pool.map(translate_group, groups))
        return results
