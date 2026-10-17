"""来源采集器基类。"""
from __future__ import annotations

import abc

from ..models import NewsItem


class Source(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def fetch(self, since_ts: int = 0) -> list[NewsItem]:
        """拉取快讯（不负责去重）。失败时应返回 [] 而非抛异常。

        since_ts: 已入库的最新时间戳。支持游标翻页的来源应一直往前翻、
        取回所有比 since_ts 更新的条目（首轮 since_ts=0 时只取一页避免回填全站历史）。
        不支持翻页的来源可忽略此参数，靠去重兜底。"""
        raise NotImplementedError
