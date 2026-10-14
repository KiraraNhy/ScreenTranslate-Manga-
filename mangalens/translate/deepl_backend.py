"""DeepL 翻译（需要 API Key）。"""

from __future__ import annotations

from .base import Translator

_CODE = {"zh": "ZH", "zh-Hant": "ZH", "ja": "JA", "en": "EN"}


class DeeplTranslator(Translator):
    name = "deepl"
    label = "DeepL（需密钥）"

    def __init__(self, api_key: str = "", proxy: str = "", timeout: float = 20.0) -> None:
        import requests

        if not api_key:
            raise RuntimeError("DeepL 需要在设置里填写 API Key")
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}

    def _endpoint(self) -> str:
        return (
            "https://api-free.deepl.com/v2/translate"
            if self.api_key.endswith(":fx")
            else "https://api.deepl.com/v2/translate"
        )

    def translate(self, texts: list[str], src: str = "auto", dst: str = "zh") -> list[str]:
        if not texts:
            return []
        data: list[tuple[str, str]] = [("target_lang", _CODE.get(dst, "ZH"))]
        if src not in ("auto", ""):
            data.append(("source_lang", _CODE.get(src, src.upper())))
        for text in texts:
            data.append(("text", text))
        resp = self.session.post(
            self._endpoint(),
            data=data,
            headers={"Authorization": f"DeepL-Auth-Key {self.api_key}"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        items = resp.json()["translations"]
        return [self.normalize(item["text"], dst) for item in items]
