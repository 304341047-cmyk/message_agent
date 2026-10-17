"""核心数据结构。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NewsItem:
    """一条原始快讯。"""

    source: str            # 来源标识，如 "cls" / "wallstreetcn"
    source_id: str         # 来源内的唯一 id（用于去重）
    title: str             # 标题（可能为空）
    content: str           # 正文 / 快讯文本
    url: str               # 原文链接
    timestamp: int         # unix 秒
    important: bool = False  # 来源是否标记为重要
    priority: int = 0      # 行情突变等高优先级标记（0 普通，1 高）
    dup_count: int = 1     # 聚类后代表本条覆盖了多少条同类消息
    urgent: bool = False   # 命中加急规则：绕过 LLM、当轮立即单独推送
    urgent_reason: str = ""  # 加急原因（如「交易所公告·保证金」「涨停」）

    @property
    def uid(self) -> str:
        """全局唯一键。"""
        return f"{self.source}:{self.source_id}"

    @property
    def text(self) -> str:
        """用于关键词匹配 / 喂给 LLM 的合并文本。"""
        if self.title and self.title not in self.content:
            return f"{self.title}\n{self.content}"
        return self.content or self.title


@dataclass
class Digest:
    """LLM 提炼后的结果，对应一条 NewsItem。"""

    item: NewsItem
    important: bool                       # LLM 判断是否值得推送
    summary: str                          # 精华摘要
    varieties: list[str] = field(default_factory=list)  # 相关期货品种
