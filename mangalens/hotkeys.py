"""全局快捷键定义（F7~F10，不与浏览器常用键冲突）。"""

from __future__ import annotations

from .win32util import MOD_CONTROL, VK_F7, VK_F8, VK_F9, VK_F10

#: 名称 -> (修饰键, 虚拟键, 说明)
HOTKEYS: dict[str, tuple[int, int, str]] = {
    "refresh": (0, VK_F7, "立即重新翻译"),
    "toggle": (0, VK_F8, "显示 / 隐藏译文"),
    "pick": (0, VK_F9, "框选翻译区域"),
    "mode": (0, VK_F10, "全屏 / 区域模式切换"),
}

DEFAULTS = HOTKEYS
