"""规则预筛：在调用 LLM 前用便宜手段缩小候选集，省额度。"""
from __future__ import annotations

from .models import NewsItem


class PreFilter:
    def __init__(self, keywords: list[str], keep_source_important: bool = True):
        self.keywords = [k for k in (keywords or []) if k]
        self.keep_source_important = keep_source_important

    def keep(self, item: NewsItem) -> bool:
        if self.keep_source_important and item.important:
            return True
        if not self.keywords:
            # 没配关键词则全部交给 LLM
            return True
        text = item.text
        return any(kw in text for kw in self.keywords)

    def apply(self, items: list[NewsItem]) -> list[NewsItem]:
        return [it for it in items if self.keep(it)]
