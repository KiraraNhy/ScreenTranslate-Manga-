"""翻译后端注册表。"""

from __future__ import annotations

from typing import Callable

from .base import Translator
from .cache import CachedTranslator, TranslationCache


def _google(cfg) -> Translator:
    from .google_backend import GoogleTranslator

    return GoogleTranslator(proxy=cfg.proxy)


def _mymemory(cfg) -> Translator:
    from .mymemory_backend import MyMemoryTranslator

    return MyMemoryTranslator(email=getattr(cfg, "memory_email", ""), proxy=cfg.proxy)


def _llm(cfg) -> Translator:
    from .llm_backend import LlmTranslator

    return LlmTranslator(
        base_url=cfg.llm_base_url,
        api_key=cfg.llm_api_key,
        model=cfg.llm_model,
        proxy=cfg.proxy,
    )


def _deepl(cfg) -> Translator:
    from .deepl_backend import DeeplTranslator

    return DeeplTranslator(api_key=cfg.deepl_api_key, proxy=cfg.proxy)


def _offline(cfg) -> Translator:
    from .offline_backend import OfflineTranslator

    return OfflineTranslator()


def _echo(cfg) -> Translator:
    class Echo(Translator):
        name = "echo"
        label = "调试占位"
        needs_network = False

        def translate(self, texts, src="auto", dst="zh"):
            return [self.normalize(f"【译】{t}", dst) for t in texts]

    return Echo()


FACTORIES: dict[str, tuple[str, Callable]] = {
    "mymemory": ("MyMemory 免费免密钥", _mymemory),
    "llm": ("大模型（OpenAI 兼容）", _llm),
    "offline": ("本地离线模型", _offline),
    "google": ("谷歌翻译（免密钥）", _google),
    "deepl": ("DeepL（需密钥）", _deepl),
    "echo": ("调试占位", _echo),
}

UI_ORDER = ["mymemory", "llm", "offline", "google", "deepl", "echo"]

#: 大模型服务商预设：名称 -> (展示名, base_url, 模型)
LLM_PRESETS: dict[str, tuple[str, str, str]] = {
    "deepseek": ("DeepSeek（推荐）", "https://api.deepseek.com/v1", "deepseek-chat"),
    "zhipu": ("智谱 GLM", "https://open.bigmodel.cn/api/paas/v4", "glm-4-flash"),
    "dashscope": (
        "通义千问",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "qwen-plus",
    ),
    "moonshot": ("Kimi", "https://api.moonshot.cn/v1", "moonshot-v1-8k"),
    "siliconflow": (
        "硅基流动",
        "https://api.siliconflow.cn/v1",
        "Qwen/Qwen2.5-7B-Instruct",
    ),
    "openai": ("OpenAI", "https://api.openai.com/v1", "gpt-4o-mini"),
    "ollama": ("本地 Ollama", "http://127.0.0.1:11434/v1", "qwen2.5:7b"),
}


def names() -> list[str]:
    return list(UI_ORDER)


def label_of(name: str) -> str:
    entry = FACTORIES.get(name)
    return entry[0] if entry else name


def create(name: str, cfg) -> Translator:
    entry = FACTORIES.get(name)
    if entry is None:
        raise ValueError(f"未知的翻译引擎：{name}")
    return entry[1](cfg)


__all__ = [
    "Translator",
    "TranslationCache",
    "CachedTranslator",
    "LLM_PRESETS",
    "create",
    "names",
    "label_of",
]
