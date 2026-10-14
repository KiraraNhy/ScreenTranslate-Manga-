"""MangaLens - 屏幕实时漫画翻译。

把屏幕(或框选区域)里的日文/外文识别出来，翻译成中文，并直接盖回原文所在位置。
"""

import os

# PaddlePaddle 与 PyTorch 各自带了一份 OpenMP 运行时，同一进程里会互相冲突。
# 这个开关让两者共存（社区通用做法），必须在导入它们之前设置。
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

__version__ = "0.1.0"
APP_NAME = "MangaLens"
APP_TITLE = "MangaLens 屏幕实时翻译"
