"""大模型翻译（任意 OpenAI 兼容接口：OpenAI / DeepSeek / 智谱 / 通义 / Kimi / 本地 Ollama 等）。

按整页合并成一次请求，并且用**流式接收**：边生成边解析，收齐条目就提前结束。
这样即使模型生成得慢也不会被"读取超时"掐断，还能把进度显示出来。
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Callable

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

_LINE_RE = re.compile(r"^\s*[（(]?\s*(\d+)\s*[.、．,，:：)）\]]\s*(.*)$")

#: 这些状态码是"重试也没用"的（密钥、余额、参数问题）
_PERMANENT_STATUS = (400, 401, 403, 404, 422)
#: 逐句兜底最多处理这么多条
_FALLBACK_LIMIT = 6


class _PermanentError(RuntimeError):
    """重试也不会成功的错误。"""


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
        retries: int = 1,
    ) -> None:
        import requests

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.read_timeout = timeout           # 单次"没收到数据"的等待上限
        self.total_timeout = max(45.0, timeout * 3)   # 整段生成的兜底上限
        self.workers = max(1, int(workers))
        self.retries = max(0, int(retries))
        self.last_error = ""
        self.on_progress: Callable[[str], None] | None = None
        self.session = requests.Session()
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}

    # ------------------------------------------------------------------ 请求
    def _target_name(self, dst: str) -> str:
        return "繁体中文" if dst == "zh-Hant" else "简体中文"

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _post_stream(self, system: str, user: str, feed) -> None:
        """流式请求；每收到一段内容就交给 feed，feed 返回 True 表示可以提前结束。"""

        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": 0.2,
            "max_tokens": 2000,
            "stream": True,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            response = self.session.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
                stream=True,
                timeout=(min(8.0, self.read_timeout), self.read_timeout),
            )
        except Exception as exc:
            raise RuntimeError(f"连接失败：{type(exc).__name__}") from exc

        try:
            if response.status_code != 200:
                body = response.text[:200].replace("\n", " ")
                message = f"接口返回 {response.status_code}：{body}"
                if response.status_code in _PERMANENT_STATUS:
                    raise _PermanentError(message)
                raise RuntimeError(message)

            content_type = (response.headers.get("Content-Type") or "").lower()
            if "event-stream" not in content_type:
                # 少数兼容接口不支持流式，按普通 JSON 处理
                text = (response.json()["choices"][0]["message"]["content"] or "").strip()
                feed(text)
                return

            deadline = time.monotonic() + self.total_timeout
            for raw in response.iter_lines(decode_unicode=False):
                if time.monotonic() > deadline:
                    raise RuntimeError("大模型响应超过总时限")
                if not raw:
                    continue
                line = raw.decode("utf-8", "ignore").strip()
                if not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    obj = json.loads(chunk)
                except ValueError:
                    continue
                choices = obj.get("choices") or []
                if not choices:
                    continue
                piece = (choices[0].get("delta") or {}).get("content") or ""
                if piece and feed(piece):
                    break
        except _PermanentError:
            raise
        except Exception as exc:
            raise RuntimeError(f"读取响应失败：{type(exc).__name__}") from exc
        finally:
            response.close()

    # ------------------------------------------------------------------ 翻译
    @staticmethod
    def _collect(line: str, found: dict) -> None:
        match = _LINE_RE.match(line.strip())
        if match:
            found[int(match.group(1))] = match.group(2).strip()

    def _translate_batch(self, texts: list[str], src: str, dst: str) -> list[str] | None:
        expected = len(texts)
        found: dict[int, str] = {}
        buffer = ""
        started = time.monotonic()

        def feed(piece: str) -> bool:
            nonlocal buffer
            buffer += piece
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                self._collect(line, found)
                if self.on_progress and len(found) != expected:
                    self.on_progress(
                        f"翻译 {len(found)}/{expected}（{time.monotonic() - started:.0f}s）"
                    )
            return len(found) >= expected

        system = _SYSTEM_BATCH.format(target=self._target_name(dst))
        numbered = "\n".join(
            f"{index + 1}. " + texts[index].replace(chr(10), " ")
            for index in range(expected)
        )
        self._post_stream(system, numbered, feed)
        if buffer.strip():
            self._collect(buffer, found)
        if len(found) != expected:
            return None
        return [found.get(index + 1, "") for index in range(expected)]

    def _per_item(self, texts: list[str], src: str, dst: str, indexes=None) -> dict:
        import concurrent.futures

        targets = list(range(len(texts))) if indexes is None else list(indexes)
        if not targets:
            return {}
        system = _SYSTEM_SINGLE.format(target=self._target_name(dst))

        def one(index: int):
            collected: list[str] = []
            try:
                self._post_stream(system, texts[index], lambda piece: collected.append(piece) or False)
            except Exception as exc:
                if not self.last_error:
                    self.last_error = str(exc)[:200]
                return index, ""
            return index, "".join(collected).strip()

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
        batch: list[str] | None = None
        for attempt in range(self.retries + 1):
            try:
                batch = self._translate_batch(texts, src, dst)
                self.last_error = ""
                break
            except _PermanentError as exc:
                self.last_error = str(exc)[:200]
                return ["" for _ in texts]
            except Exception as exc:
                self.last_error = str(exc)[:200]
                if attempt < self.retries:
                    time.sleep(0.8)  # 稍等一下自动重试一次
        if batch is None:
            if self.last_error:
                return ["" for _ in texts]
            if len(texts) > _FALLBACK_LIMIT:
                self.last_error = "模型没有按序号返回，请按 F7 重试"
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
