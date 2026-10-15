"""翻译后端接口。"""

from __future__ import annotations

import re

# 中文标点/汉字之间多余的空格（谷歌、部分模型会插入）
_CJK = r"\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef"
_SPACE_BETWEEN_CJK = re.compile(rf"(?<=[{_CJK}])[ \t]+(?=[{_CJK}])")
_SPACE_AROUND_PUNCT = re.compile(rf"\s+(?=[{_CJK}])|(?<=[{_CJK}])\s+")


class Translator:
    """把一批文本从 src 翻译到 dst。子类实现 :meth:`translate`。"""

    name = "base"
    label = "基础"
    needs_network = True
    #: 可选：翻译过程中的进度回调（例如 "3/9"）
    on_progress = None

    def translate(self, texts: list[str], src: str, dst: str) -> list[str]:
        raise NotImplementedError

    def close(self) -> None:
        pass

    # ------------------------------------------------------------------ 工具
    @staticmethod
    def normalize(text: str, dst: str) -> str:
        """整理译文排版。"""

        text = text.replace("\r\n", "\n").strip()
        if dst.startswith("zh"):
            text = _SPACE_BETWEEN_CJK.sub("", text)
            text = _SPACE_BETWEEN_CJK.sub("", text)
            # 只去掉紧贴标点的空格，保留中英之间的空格
            text = re.sub(r"[ \t]+(?=[，。！？；：、）】》」』])", "", text)
            text = re.sub(r"(?<=[（【《「『])[ \t]+", "", text)
        return text
