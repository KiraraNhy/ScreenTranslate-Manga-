"""中文字体选择。"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

# (路径, ttc 索引)。优先能同时显示中文和日文假名的字体。
_CANDIDATES: list[tuple[str, int]] = [
    (r"C:\Windows\Fonts\msyh.ttc", 0),  # 微软雅黑
    (r"C:\Windows\Fonts\msyhbd.ttc", 0),
    (r"C:\Windows\Fonts\Deng.ttf", 0),  # 等线
    (r"C:\Windows\Fonts\simhei.ttf", 0),  # 黑体
    (r"C:\Windows\Fonts\simsun.ttc", 0),  # 宋体
    (r"C:\Windows\Fonts\NotoSansSC-VF.ttf", 0),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0),
    ("/System/Library/Fonts/PingFang.ttc", 0),
]


@lru_cache(maxsize=1)
def default_font() -> tuple[str, int]:
    for path, index in _CANDIDATES:
        if os.path.exists(path):
            return path, index
    raise RuntimeError("找不到可用的中文字体，请在设置里手动指定字体文件")


def resolve_font(user_path: str = "") -> tuple[str, int]:
    if user_path and Path(user_path).exists():
        return user_path, 0
    return default_font()


@lru_cache(maxsize=64)
def load_font(size: int, path: str = "", index: int = 0):
    from PIL import ImageFont

    if not path:
        path, index = resolve_font()
    return ImageFont.truetype(path, size=size, index=index)
