"""大模型翻译（任意 OpenAI 兼容接口：OpenAI / DeepSeek / 硅基流动 / 本地 Ollama 等）。"""

from __future__ import annotations

import concurrent.futures
from typing import Any

from .base import Translator

_SYSTEM = (
    "你是专业的漫画翻译。把用户给的原文翻译成{target}，要求：\n"
    "1. 口语化、符合中文习惯，保留人物语气；\n"
    "2. 简洁，长度尽量接近原文，方便放进对话框；\n"
    "3. 人名、专有名词保留原样或音译；\n"
    "4. 只输出译文本身，不要解释、不要加引号、不要注音。"
)


class LlmTranslator(Translator):
    name = "llm"
    label = "大模型（OpenAI 兼容）"

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        model: str = "gpt-4o-mini",
        proxy: str = "",
        timeout: float = 40.0,
        workers: int = 4,
    ) -> None:
        import requests

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.workers = workers
        self.session = requests.Session()
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}

    def _target_name(self, dst: str) -> str:
        return "繁体中文" if dst == "zh-Hant" else "简体中文"

    def _translate_one(self, text: str, src: str, dst: str) -> str:
        if not text.strip():
            return ""
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": _SYSTEM.format(target=self._target_name(dst)),
                },
                {"role": "user", "content": text},
            ],
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        resp = self.session.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

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
