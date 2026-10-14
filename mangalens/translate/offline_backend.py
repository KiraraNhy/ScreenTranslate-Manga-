"""本地离线翻译（transformers 的 opus-mt 模型）。

opus-mt 没有直接的日->中模型，这里用英文做中转（日->英->中）。
首次使用会自动下载模型（从 hf-mirror 镜像，约几百 MB），之后完全离线。
"""

from __future__ import annotations

import os

from .base import Translator

#: 单跳模型
_DIRECT = {
    ("en", "zh"): "Helsinki-NLP/opus-mt-en-zh",
    ("en", "zh-Hant"): "Helsinki-NLP/opus-mt-en-zh",
}

#: 经由英语中转的模型（源语言 -> 英）
_TO_EN = {
    "ja": "Helsinki-NLP/opus-mt-ja-en",
    "ko": "Helsinki-NLP/opus-mt-ko-en",
    "fr": "Helsinki-NLP/opus-mt-fr-en",
    "de": "Helsinki-NLP/opus-mt-de-en",
    "es": "Helsinki-NLP/opus-mt-es-en",
    "it": "Helsinki-NLP/opus-mt-it-en",
    "pt": "Helsinki-NLP/opus-mt-ROMANCE-en",
    "ru": "Helsinki-NLP/opus-mt-ru-en",
    "vi": "Helsinki-NLP/opus-mt-vi-en",
    "th": "Helsinki-NLP/opus-mt-th-en",
    "ar": "Helsinki-NLP/opus-mt-ar-en",
}


def chain_for(src: str, dst: str) -> list[str]:
    """返回需要依次调用的模型列表。"""

    if src == dst:
        return []
    if (src, dst) in _DIRECT:
        return [_DIRECT[(src, dst)]]
    if src not in ("en", "zh", "zh-Hant"):
        to_en = _TO_EN.get(src)
        if to_en:
            return [to_en, _DIRECT[("en", "zh")]]
    raise RuntimeError(f"离线模型暂不支持 {src} -> {dst}，请改用在线翻译")


class OfflineTranslator(Translator):
    name = "offline"
    label = "离线模型（需下载）"
    needs_network = False

    def __init__(self, **options) -> None:
        self._models: dict[str, object] = {}
        self.options = options

    def _model(self, model_name: str):
        """加载 opus-mt 模型（transformers 5 已经没有 translation pipeline，这里直接推理）。"""

        if model_name not in self._models:
            # 国内默认走 HuggingFace 镜像，模型只需要下载一次
            os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
            self._models[model_name] = _Marian(model_name)
        return self._models[model_name]

    def translate(self, texts: list[str], src: str = "auto", dst: str = "zh") -> list[str]:
        if not texts:
            return []
        if src == "auto":
            src = "ja"
        models = chain_for(src, dst)
        if not models:
            return [self.normalize(t, dst) for t in texts]
        current = [t for t in texts]
        for model_name in models:
            model = self._model(model_name)
            current = model.translate(current)  # type: ignore[attr-defined]
        return [self.normalize(t, dst) for t in current]


class _Marian:
    """opus-mt（Marian）模型的简单封装。"""

    def __init__(self, name: str, max_new_tokens: int = 320) -> None:
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        self.name = name
        self.max_new_tokens = max_new_tokens
        self.tokenizer = AutoTokenizer.from_pretrained(name)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(name)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model.to(self.device)
        self.model.eval()

    def translate(self, texts: list[str]) -> list[str]:
        import torch

        out: list[str] = []
        batch_size = 8
        for start in range(0, len(texts), batch_size):
            chunk = [t if t.strip() else " " for t in texts[start : start + batch_size]]
            with torch.no_grad():
                batch = self.tokenizer(
                    chunk,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                ).to(self.device)
                generated = self.model.generate(
                    **batch, max_new_tokens=self.max_new_tokens, num_beams=1
                )
            out.extend(self.tokenizer.batch_decode(generated, skip_special_tokens=True))
        return out
