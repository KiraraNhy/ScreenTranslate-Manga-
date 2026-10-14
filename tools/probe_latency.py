"""实测 MyMemory 的延迟结构：并发多条 vs 合并成一条。"""

from __future__ import annotations

import concurrent.futures
import time

import requests

UA = {"User-Agent": "MangaLens/0.1 (screen translation)"}
ENDPOINT = "https://api.mymemory.translated.net/get"

TEXTS = [
    "おはよう、今日はいい天気だね。",
    "俺は海賊王になる男だ",
    "なんだって！？そんなはずはない！",
    "その日、世界は大きく変わった。",
    "お前の力はそんなものじゃないだろう。",
    "ここで待っていてくれ、すぐ戻る。",
]


def one(text: str, tag: str = "") -> tuple[str, float]:
    start = time.perf_counter()
    resp = requests.get(
        ENDPOINT, params={"q": text, "langpair": "ja|zh-CN"}, headers=UA, timeout=20
    )
    data = resp.json()
    value = (data.get("responseData") or {}).get("translatedText", "")
    return value, time.perf_counter() - start


def run_parallel(workers: int) -> None:
    start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda t: one(t, "parallel"), TEXTS))
    total = time.perf_counter() - start
    each = ", ".join(f"{ms:.2f}s" for _v, ms in results)
    print(f"[并发 {workers} 条] 总耗时 {total:.2f}s   单条: {each}")


def run_sequential() -> None:
    start = time.perf_counter()
    for text in TEXTS:
        one(text, "seq")
        time.sleep(0.12)
    print(f"[串行 6 条] 总耗时 {time.perf_counter() - start:.2f}s")


def run_merged(separator: str) -> None:
    joined = separator.join(TEXTS)
    print(f"[合并 1 条 分隔符={separator!r}] 原文 {len(joined.encode('utf-8'))} 字节")
    value, elapsed = one(joined, "merged")
    print(f"    耗时 {elapsed:.2f}s")
    print(f"    译文：{value!r}")
    parts = value.split(separator)
    print(f"    按分隔符切回 {len(parts)} 段：{parts}")


if __name__ == "__main__":
    run_merged("\n")
    run_merged("|||")
    run_sequential()
    for workers in (1, 3, 5):
        run_parallel(workers)
