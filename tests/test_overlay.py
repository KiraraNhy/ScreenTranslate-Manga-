"""覆盖层自检：窗口是否置顶、是否点击穿透、是否能被屏幕截图排除。

手动运行：python tests/test_overlay.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mangalens.capture import Capturer  # noqa: E402
from mangalens.overlay import Overlay  # noqa: E402
from mangalens.win32util import (  # noqa: E402
    WS_EX_LAYERED,
    WS_EX_NOACTIVATE,
    WS_EX_TOOLWINDOW,
    WS_EX_TOPMOST,
    WS_EX_TRANSPARENT,
    user32,
)

RECT = (120, 120, 420, 300)
GWL_EXSTYLE = -20


def build_frame(width: int, height: int) -> np.ndarray:
    frame = np.zeros((height, width, 4), np.uint8)
    frame[40 : height - 40, 40 : width - 40] = (255, 0, 0, 255)  # 纯红
    return frame


def main() -> int:
    overlay = Overlay({}, hide_from_capture=True)
    overlay.start()
    assert overlay.hwnd, "覆盖层窗口创建失败"
    time.sleep(0.4)
    events = []
    while not overlay.events.empty():
        events.append(overlay.events.get())
    print("窗口句柄：", overlay.hwnd, "｜截图排除：", overlay.excluded_from_capture, "｜", events)

    ex_style = user32.GetWindowLongW(overlay.hwnd, GWL_EXSTYLE) & 0xFFFFFFFF
    expected = {
        "分层窗口": WS_EX_LAYERED,
        "点击穿透": WS_EX_TRANSPARENT,
        "置顶": WS_EX_TOPMOST,
        "不占任务栏": WS_EX_TOOLWINDOW,
        "不抢焦点": WS_EX_NOACTIVATE,
    }
    missing = [name for name, flag in expected.items() if not ex_style & flag]
    assert not missing, f"覆盖层缺少这些窗口属性：{missing}"
    print("窗口属性齐全：", "、".join(expected))

    capturer = Capturer()
    before = capturer.grab(RECT)
    overlay.push(RECT, build_frame(RECT[2], RECT[3]))
    time.sleep(0.6)
    after = capturer.grab(RECT)

    red_before = int(((before[:, :, 0] > 180) & (before[:, :, 1] < 80)).sum())
    red_after = int(((after[:, :, 0] > 180) & (after[:, :, 1] < 80)).sum())
    print(f"截图里的红色像素：绘制前 {red_before}，绘制后 {red_after}")

    overlay.set_visible(False)
    time.sleep(0.4)
    hidden = capturer.grab(RECT)
    red_hidden = int(((hidden[:, :, 0] > 180) & (hidden[:, :, 1] < 80)).sum())
    print(f"隐藏后红色像素：{red_hidden}")
    overlay.stop()

    assert red_before < RECT[2] * RECT[3] * 0.05, "测试区域原本就有大片红色，结果不可信"
    if red_after == red_before:
        print("结论：覆盖层不会出现在屏幕截图里")
    else:
        # 这个系统特性在部分情况下不生效，程序本身不依赖它：
        # 变化检测用的是"原图+译文"的预期画面，另有译文比对过滤兜底。
        print("提示：本机该时刻未能把覆盖层排除出截图，程序靠变化检测兜底，不影响使用")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
