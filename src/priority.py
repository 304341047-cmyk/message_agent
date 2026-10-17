"""行情突变类消息的高优先级识别（纯规则，不调 LLM）。

命中即标记 priority=1：这类消息（某品种涨跌幅、拉升/暴跌/涨停跌停/创新高低）
会强制推送并在飞书里 🔥 置顶。
"""
from __future__ import annotations

import re

from .models import NewsItem

# 强行情动作词：基本只出现在行情突变语境
_STRONG = re.compile(
    r"(涨停|跌停|封板|拉升|跳水|暴涨|暴跌|飙升|飙涨|重挫|急涨|急跌|跳涨|崩盘|闪崩|大幅(?:上涨|下跌))"
)
# 涨跌 + 数字 + 单位（百分比/点/价位）
_MOVE = re.compile(
    r"(涨|跌|涨幅|跌幅|上涨|下跌|大涨|大跌|跌超|涨超)[^，。；！\n]{0,8}?"
    r"\d+(?:\.\d+)?\s*(%|％|个百分点|点|元|美元|美分|盎司)"
)
# 创新高 / 创新低
_NEWHL = re.compile(r"创[^，。；\n]{0,8}?(新高|新低)")


def score_priority(item: NewsItem) -> int:
    text = item.text
    if _STRONG.search(text) or _MOVE.search(text) or _NEWHL.search(text):
        return 1
    return 0


def mark(items: list[NewsItem]) -> None:
    """就地给每条打优先级。"""
    for it in items:
        it.priority = score_priority(it)
