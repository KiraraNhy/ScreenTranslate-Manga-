"""翻译结果缓存（sqlite），避免同一页反复请求。"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from pathlib import Path

from ..config import app_home
from .base import Translator

_SCHEMA = """
CREATE TABLE IF NOT EXISTS translations (
    key      TEXT PRIMARY KEY,
    source   TEXT NOT NULL,
    target   TEXT NOT NULL,
    value    TEXT NOT NULL,
    updated  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_updated ON translations(updated);
"""


class TranslationCache:
    def __init__(self, path: Path | None = None, max_rows: int = 50000) -> None:
        target = Path(path) if path else app_home() / "cache.sqlite3"
        self.path = target
        self.max_rows = max_rows
        self._lock = threading.Lock()
        try:
            self._conn = sqlite3.connect(self.path, check_same_thread=False)
        except Exception:
            # 磁盘不可写时退回内存缓存，功能照常，只是不跨会话保留
            self.path = Path(":memory:")
            self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    @staticmethod
    def make_key(backend: str, src: str, dst: str, text: str) -> str:
        raw = f"{backend}\x00{src}\x00{dst}\x00{text}".encode("utf-8")
        return hashlib.sha1(raw).hexdigest()

    def get_many(self, keys: list[str]) -> dict[str, str]:
        if not keys:
            return {}
        found: dict[str, str] = {}
        with self._lock:
            for start in range(0, len(keys), 400):
                chunk = keys[start : start + 400]
                marks = ",".join("?" * len(chunk))
                rows = self._conn.execute(
                    f"SELECT key, value FROM translations WHERE key IN ({marks})", chunk
                )
                found.update(dict(rows))
        return found

    def put_many(self, items: dict[str, tuple[str, str, str]]) -> None:
        """items: key -> (source, target, value)"""

        if not items:
            return
        now = time.time()
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO translations(key, source, target, value, updated)"
                " VALUES (?,?,?,?,?)",
                [
                    (key, src, dst, value, now)
                    for key, (src, dst, value) in items.items()
                ],
            )
            self._conn.commit()
            count = self._conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
            if count > self.max_rows:
                self._conn.execute(
                    "DELETE FROM translations WHERE key IN ("
                    "  SELECT key FROM translations ORDER BY updated ASC LIMIT ?)",
                    (count - self.max_rows,),
                )
                self._conn.commit()

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM translations")
            self._conn.commit()

    def size(self) -> int:
        with self._lock:
            return int(
                self._conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
            )

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class CachedTranslator(Translator):
    """带缓存的包装器。"""

    def __init__(self, inner: Translator, cache: TranslationCache) -> None:
        self.inner = inner
        self.cache = cache
        self.name = inner.name
        self.label = inner.label
        self.last_hits = 0
        self.last_misses = 0

    @property
    def last_error(self) -> str:
        return getattr(self.inner, "last_error", "")

    @property
    def on_progress(self):
        return getattr(self.inner, "on_progress", None)

    @on_progress.setter
    def on_progress(self, value) -> None:
        # 进度回调要透传给真正的翻译后端，否则面板看不到进度
        try:
            self.inner.on_progress = value
        except Exception:
            pass

    def translate(self, texts: list[str], src: str = "auto", dst: str = "zh") -> list[str]:
        keys = [TranslationCache.make_key(self.inner.name, src, dst, t) for t in texts]
        cached = self.cache.get_many(keys)
        missing = [
            (index, text)
            for index, (key, text) in enumerate(zip(keys, texts))
            if key not in cached
        ]
        self.last_hits = len(texts) - len(missing)
        self.last_misses = len(missing)
        results = [cached.get(key, "") for key in keys]
        if missing:
            fresh = self.inner.translate([text for _, text in missing], src, dst)
            updates: dict[str, tuple[str, str, str]] = {}
            for (index, text), value in zip(missing, fresh):
                results[index] = value
                if value:
                    updates[keys[index]] = (src, dst, value)
            self.cache.put_many(updates)
        return results

    def close(self) -> None:
        self.inner.close()
