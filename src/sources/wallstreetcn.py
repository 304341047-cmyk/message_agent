"""华尔街见闻 快讯采集。

使用公开的 live news 接口，返回 JSON，无需登录。
"""
from __future__ import annotations

import logging

import requests

from ..models import NewsItem
from .base import Source

log = logging.getLogger(__name__)

_API = "https://api-one.wallstcn.com/apiv1/content/lives"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://wallstreetcn.com/live/global",
}

# 国内站点，直连即可。trust_env=False 让 requests 忽略系统/环境代理
# (HTTP_PROXY/HTTPS_PROXY)，避免本地代理(Clash 等)没开时连接被拒(WinError 10061)。
_session = requests.Session()
_session.trust_env = False


class WallstreetcnSource(Source):
    name = "wallstreetcn"

    def __init__(self, limit: int = 50, max_pages: int = 10):
        # 接口单页上限 100；limit 为每页条数，max_pages 为单轮最多翻几页（防失控）。
        self.limit = min(limit, 100)
        self.max_pages = max(1, max_pages)

    def _parse(self, it: dict) -> NewsItem | None:
        try:
            sid = str(it.get("id"))
            score = it.get("score") or 0
            ts = int(it.get("display_time") or it.get("created_at") or 0)
            return NewsItem(
                source=self.name,
                source_id=sid,
                title=it.get("title") or "",
                content=it.get("content_text") or it.get("content") or "",
                url=it.get("uri") or f"https://wallstreetcn.com/livenews/{sid}",
                timestamp=ts,
                important=bool(score and score >= 2),
            )
        except Exception as e:  # noqa: BLE001
            log.debug("[wallstreetcn] 跳过一条解析失败的条目: %s", e)
            return None

    def fetch(self, since_ts: int = 0) -> list[NewsItem]:
        out: list[NewsItem] = []
        cursor = ""
        # 首轮（库里没有该源记录）只取一页，避免回填全站历史。
        pages = 1 if since_ts <= 0 else self.max_pages
        for _ in range(pages):
            params = {"channel": "global-channel", "client": "pc", "limit": self.limit}
            if cursor:
                params["cursor"] = cursor
            try:
                data = _session.get(_API, params=params, headers=_HEADERS, timeout=10).json()
            except Exception as e:  # noqa: BLE001
                log.error("[wallstreetcn] 拉取失败: %s", e)
                break
            d = data.get("data") or {}
            items_raw = d.get("items") or []
            if not items_raw:
                break

            reached = False
            for it in items_raw:
                ni = self._parse(it)
                if ni is None:
                    continue
                if since_ts and ni.timestamp <= since_ts:
                    reached = True  # 已翻到上次见过的位置，停止
                    continue
                out.append(ni)
            cursor = d.get("next_cursor") or ""
            if reached or not cursor:
                break
        return out
