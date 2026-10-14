"""探测可用的免密钥翻译接口。"""

from __future__ import annotations

import json
import re
import sys

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
TEXT = "おはよう、今日はいい天気だね。"


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    return s


def _bing_tokens(html: str) -> dict[str, str] | None:
    ig = re.search(r'IG:"([0-9A-F]+)"', html)
    iid = re.search(r'data-iid="([0-9a-zA-Z.\-]+)"', html)
    helper = re.search(r"params_AbusePreventionHelper\s*=\s*\[(\d+),\s*\"([^\"]+)\"", html)
    if not (ig and iid and helper):
        return None
    return {
        "IG": ig.group(1),
        "IID": iid.group(1),
        "key": helper.group(1),
        "token": helper.group(2),
    }


def try_bing() -> None:
    s = session()
    for host in ("https://www.bing.com", "https://cn.bing.com"):
        try:
            page = s.get(f"{host}/translator", timeout=10)
        except Exception as exc:
            print(f"bing {host} 首页失败 {type(exc).__name__}")
            continue
        tokens = _bing_tokens(page.text)
        print(f"bing {host} 状态 {page.status_code} 长度 {len(page.text)} tokens={bool(tokens)}")
        if not tokens:
            continue
        try:
            resp = s.post(
                f"{host}/ttranslatev3",
                params={"isVertical": "1", "IG": tokens["IG"], "IID": tokens["IID"]},
                data={
                    "fromLang": "ja",
                    "text": TEXT,
                    "to": "zh-Hans",
                    "token": tokens["token"],
                    "key": tokens["key"],
                    "tryFetchingGenderDebiasedTranslations": "true",
                },
                timeout=10,
            )
            print("  bing 翻译:", resp.status_code, resp.text[:250])
        except Exception as exc:
            print("  bing 翻译失败", type(exc).__name__, str(exc)[:120])


def try_edge_auth() -> None:
    s = session()
    for url in (
        "https://edge.microsoft.com/translate/auth",
        "https://edge.microsoft.com/translate/auth?client=edge",
    ):
        try:
            resp = s.get(url, timeout=8)
            print("edge auth", resp.status_code, len(resp.text), repr(resp.text[:40]))
        except Exception as exc:
            print("edge auth ERR", type(exc).__name__)


def try_mymemory() -> None:
    s = session()
    try:
        resp = s.get(
            "https://api.mymemory.translated.net/get",
            params={"q": TEXT, "langpair": "ja|zh-CN"},
            timeout=10,
        )
        data = resp.json()
        print("mymemory:", resp.status_code, repr(data.get("responseData", {}).get("translatedText"))[:80])
    except Exception as exc:
        print("mymemory ERR", type(exc).__name__, str(exc)[:100])


def try_deepl_web() -> None:
    """DeepL 网页版的免费接口（有限流，不需要密钥）。"""

    s = session()
    try:
        page = s.get("https://www2.deepl.com/jsonrpc", timeout=8)
        print("deepl web:", page.status_code)
    except Exception as exc:
        print("deepl web ERR", type(exc).__name__)


def try_papago() -> None:
    """Naver Papago 网页版（免密钥，ja/zh/en/ko 之间互译）。"""

    import uuid

    s = session()
    try:
        page = s.get("https://papago.naver.com/", timeout=10)
        html = page.text
        key = re.search(r'"KEY":"([^"]+)"', html) or re.search(r'key["\']?\s*[:=]\s*"([^"]+)"', html)
        print("papago 页面", page.status_code, len(html), "key found", bool(key))
        if not key:
            return
        device = str(uuid.uuid4())
        resp = s.post(
            "https://papago.naver.com/apis/n2mt/translate",
            data={
                "deviceId": device,
                "locale": "zh-CN",
                "dict": "true",
                "dictDisplay": "30",
                "honorific": "false",
                "instant": "false",
                "paging": "true",
                "source": "ja",
                "target": "zh-CN",
                "text": TEXT,
            },
            headers={"Referer": "https://papago.naver.com/", "X-Apigw-Partnerid": "papago"},
            timeout=10,
        )
        print("  papago 翻译:", resp.status_code, resp.text[:200])
    except Exception as exc:
        print("papago ERR", type(exc).__name__, str(exc)[:120])


def try_mymemory_more() -> None:
    s = session()
    samples = [
        "なんだって！？そんなはずはない！",
        "その日、世界は大きく変わった。",
        "お前の力はそんなものじゃないだろう。",
    ]
    for text in samples:
        try:
            resp = s.get(
                "https://api.mymemory.translated.net/get",
                params={"q": text, "langpair": "ja|zh-CN"},
                timeout=10,
            )
            data = resp.json()
            print("mymemory:", text, "->", data.get("responseData", {}).get("translatedText"))
        except Exception as exc:
            print("mymemory ERR", type(exc).__name__)


if __name__ == "__main__":
    for fn in (try_mymemory_more, try_papago, try_bing):
        fn()
        print("-" * 40)


