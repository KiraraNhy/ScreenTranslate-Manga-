"""大模型翻译（任意 OpenAI 兼容接口：OpenAI / DeepSeek / 智谱 / 通义 / Kimi / 本地 Ollama 等）。

按整页合并成一次请求（每句前面加序号），避免一屏十几句话发十几次请求导致长时间没反应。
"""

from __future__ import annotations

import re
from typing import Any

from .base import Translator

_SYSTEM_SINGLE = (
    "你是专业的漫画翻译。把用户给的原文翻译成{target}，要求：\n"
    "1. 口语化、符合中文习惯，保留人物语气；\n"
    "2. 简洁，长度尽量接近原文，方便放进对话框；\n"
    "3. 人名、专有名词保留原样或音译；\n"
    "4. 只输出译文本身，不要解释、不要加引号、不要注音。"
)

_SYSTEM_BATCH = (
    "你是专业的漫画翻译。下面每行是一条漫画台词，行首有序号。"
    "请把每一条都翻译成{target}，要求：\n"
    "1. 口语化、符合中文习惯，保留人物语气；\n"
    "2. 简洁，长度尽量接近原文，方便放进对话框；\n"
    "3. 人名、专有名词保留原样或音译；\n"
    "4. 输出格式必须是「序号. 译文」，一条一行，序号和条目数量都不能变；\n"
    "5. 不要输出任何解释、标题或多余空行。"
)

_LINE_RE = re.compile(r"^\s*(\d+)\s*[.、．,:：)）]\s*(.*)$")

#: 逐句兜底最多处理这么多条，避免接口异常时长时间卡住
_FALLBACK_LIMIT = 6


class LlmTranslator(Translator):
    name = "llm"
    label = "大模型（OpenAI 兼容）"

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        model: str = "gpt-4o-mini",
        proxy: str = "",
        timeout: float = 20.0,
        workers: int = 4,
    ) -> None:
        import requests

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.workers = max(1, int(workers))
        self.last_error = ""
        self.session = requests.Session()
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}

    # ------------------------------------------------------------------ 请求
    def _target_name(self, dst: str) -> str:
        return "繁体中文" if dst == "zh-Hant" else "简体中文"

    def _chat(self, system: str, user: str) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": 0.2,
            "max_tokens": 1500,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
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
        if resp.status_code != 200:
            detail = resp.text[:160].replace("\n", " ")
            raise RuntimeError(f"接口返回 {resp.status_code}：{detail}")
        data = resp.json()
        return (data["choices"][0]["message"]["content"] or "").strip()

    # ------------------------------------------------------------------ 翻译
    def _translate_batch(self, texts: list[str], src: str, dst: str) -> list[str] | None:
        """一次请求翻完整页；序号对不上就返回 None。"""

        numbered = "\n".join(
            f"{index + 1}. " + texts[index].replace(chr(10), " ")
            for index in range(len(texts))
        )
        answer = self._chat(_SYSTEM_BATCH.format(target=self._target_name(dst)), numbered)
        found: dict[int, str] = {}
        for line in answer.splitlines():
            match = _LINE_RE.match(line)
            if match:
                found[int(match.group(1))] = match.group(2).strip()
        if len(found) != len(texts):
            return None
        return [found.get(index + 1, "") for index in range(len(texts))]

    def _per_item(self, texts: list[str], src: str, dst: str, indexes=None) -> dict:
        import concurrent.futures

        targets = list(range(len(texts))) if indexes is None else list(indexes)
        if not targets:
            return {}
        system = _SYSTEM_SINGLE.format(target=self._target_name(dst))

        def one(index: int):
            try:
                return index, self._chat(system, texts[index])
            except Exception as exc:
                if not self.last_error:
                    self.last_error = str(exc)[:200]
                return index, ""

        out = {}
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(self.workers, len(targets))
        ) as pool:
            for index, value in pool.map(one, targets):
                out[index] = value
        return out

    def translate(self, texts: list[str], src: str = "auto", dst: str = "zh") -> list[str]:
        if not texts:
            return []
        self.last_error = ""
        try:
            batch = self._translate_batch(texts, src, dst)
        except Exception as exc:
            self.last_error = str(exc)[:200]
            return ["" for _ in texts]

        if batch is None:
            if len(texts) > _FALLBACK_LIMIT:
                self.last_error = "模型没有按序号返回，请重试（可按 F7）"
                return ["" for _ in texts]
            self.last_error = "模型没有按序号返回，已改为逐句翻译"
            values = self._per_item(texts, src, dst)
            return [self.normalize(values.get(i, ""), dst) for i in range(len(texts))]

        missing = [i for i, value in enumerate(batch) if not value.strip()]
        if missing and len(missing) <= 4:
            values = self._per_item(texts, src, dst, indexes=missing)
            for index, value in values.items():
                batch[index] = value
        if any(not value.strip() for value in batch):
            self.last_error = self.last_error or "有句子没翻出来，可按 F7 重试"
        return [self.normalize(value, dst) if value else "" for value in batch]
