"""把 OCR 出来的零散文字行合并成"对话框"级别的文本块，并排好阅读顺序。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .ocr.base import TextLine

_HAS_LETTER = re.compile(r"[A-Za-z\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]")
_CJK = r"\u3000-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef"
_CJK_ANY = re.compile(rf"[{_CJK}]")
_SPACE_BETWEEN_CJK = re.compile(rf"(?<=[{_CJK}])[ \t]+(?=[{_CJK}])")
_SPACE_BEFORE_PUNCT = re.compile(rf"(?<=[{_CJK}])[ \t]+(?=[!?.,;:。、！？；：…])")


def normalize_source_text(text: str) -> str:
    """OCR 常把中日文按字拆开加空格，这里还原成连续文本。"""

    if not _CJK_ANY.search(text):
        return text
    text = _SPACE_BETWEEN_CJK.sub("", text)
    text = _SPACE_BEFORE_PUNCT.sub("", text)
    return text


@dataclass
class Block:
    lines: list[TextLine] = field(default_factory=list)
    vertical: bool = False
    bbox: tuple[float, float, float, float] = (0, 0, 0, 0)
    text_src: str = ""
    text_dst: str = ""
    conf: float = 1.0
    failed: bool = False

    @property
    def width(self) -> float:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> float:
        return self.bbox[3] - self.bbox[1]

    def quads(self) -> list[list[tuple[float, float]]]:
        return [line.quad for line in self.lines]


def _union(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> tuple[float, float, float, float]:
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _gap(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> tuple[float, float]:
    dx = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
    return dx, dy


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


class _UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def group_lines(
    lines: list[TextLine],
    gap_ratio: float = 0.85,
    min_block_height: float = 0.0,
) -> list[Block]:
    """把同一段文字里的行/列合并成一个块。"""

    lines = [ln for ln in lines if ln.text.strip()]
    if not lines:
        return []

    boxes = [ln.bbox for ln in lines]
    heights = [max(1.0, box[3] - box[1]) for box in boxes]
    widths = [max(1.0, box[2] - box[0]) for box in boxes]
    h_med = _median(heights)
    w_med = _median(widths)

    uf = _UnionFind(len(lines))
    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            dx, dy = _gap(boxes[i], boxes[j])
            if lines[i].vertical and lines[j].vertical:
                tol = gap_ratio * max(w_med, widths[i], widths[j])
            else:
                tol = gap_ratio * max(h_med, heights[i], heights[j])
            if dx <= tol and dy <= tol:
                uf.union(i, j)

    buckets: dict[int, list[int]] = {}
    for index in range(len(lines)):
        buckets.setdefault(uf.find(index), []).append(index)

    blocks: list[Block] = []
    for members in buckets.values():
        items = [lines[i] for i in members]
        vertical_votes = sum(
            len(ln.text) for ln in items if ln.vertical
        )
        total_votes = sum(len(ln.text) for ln in items) or 1
        block = Block(
            lines=items,
            vertical=vertical_votes * 2 >= total_votes,
            conf=min((ln.conf for ln in items), default=1.0),
        )
        block.lines = _order_lines(items, block.vertical)
        bbox = boxes[members[0]]
        for index in members[1:]:
            bbox = _union(bbox, boxes[index])
        block.bbox = bbox
        block.text_src = _join(block.lines, block.vertical)
        if block.height < min_block_height:
            continue
        blocks.append(block)

    blocks.sort(key=lambda b: (round(b.bbox[1] / 10), b.bbox[0]))
    return blocks


def _order_lines(items: list[TextLine], vertical: bool) -> list[TextLine]:
    if vertical:
        # 竖排：从右往左分列，列内从上到下
        return sorted(items, key=lambda ln: (-ln.center[0], ln.center[1]))
    # 横排：从上到下分行，行内从左到右
    return sorted(items, key=lambda ln: (round(ln.center[1] / 8), ln.center[0]))


def _join(items: list[TextLine], vertical: bool) -> str:
    if vertical:
        return "".join(ln.text for ln in items)
    text = "\n".join(ln.text for ln in items)
    return text


def is_translatable(text: str) -> bool:
    """过滤掉纯数字/符号，避免把页码、拟声符号送进翻译。"""

    stripped = text.strip()
    if len(stripped) < 2:
        return False
    return bool(_HAS_LETTER.search(stripped))
