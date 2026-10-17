"""财联社电报采集。

财联社的电报接口需要一个 sign 参数：对排序后的 query 串先 SHA1、再 MD5。
该接口为非官方公开接口，财联社若调整签名算法或字段，此处可能需要维护。
失败时返回空列表，不影响其它来源。
"""
from __future__ import annotations

import hashlib
import logging
from urllib.parse import urlencode

import requests

from ..models import NewsItem
from .base import Source

log = logging.getLogger(__name__)

_API = "https://www.cls.cn/v1/roll/get_roll_list"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.cls.cn/telegraph",
}

# 国内站点，直连即可。trust_env=False 让 requests 忽略系统/环境代理
# (HTTP_PROXY/HTTPS_PROXY)，避免本地代理(Clash 等)没开时连接被拒(WinError 10061)。
_session = requests.Session()
_session.trust_env = False


def _sign(params: dict) -> str:
    query = urlencode(sorted(params.items()))
    sha1 = hashlib.sha1(query.encode("utf-8")).hexdigest()
    return hashlib.md5(sha1.encode("utf-8")).hexdigest()


class ClsSource(Source):
    name = "cls"

    def __init__(self, rn: int = 50, only_important: bool = False):
        # 该接口 rn 上限为 50（>50 返回 0 条），且不支持 last_time 游标翻页，
        # 故无法"增量取全"，只能每轮取最新 rn 条、靠去重兜底。
        self.rn = min(rn, 50)
        self.only_important = only_important

    def fetch(self, since_ts: int = 0) -> list[NewsItem]:  # since_ts 忽略：接口无游标
        params = {
            "app": "CailianpressWeb",
            "category": "red" if self.only_important else "",
            "last_time": "",
            "os": "web",
            "rn": str(self.rn),
            "sv": "8.4.6",
        }
        params["sign"] = _sign(params)

        try:
            resp = _session.get(_API, params=params, headers=_HEADERS, timeout=10)
            data = resp.json()
        except Exception as e:  # noqa: BLE001
            log.error("[cls] 拉取失败: %s", e)
            return []

        if data.get("errno"):
            log.error("[cls] 接口返回错误: errno=%s msg=%s", data.get("errno"), data.get("msg"))
            return []

        roll = (data.get("data") or {}).get("roll_data") or []
        out: list[NewsItem] = []
        for it in roll:
            try:
                if it.get("is_ad"):
                    continue
                sid = str(it.get("id"))
                title = it.get("title") or ""
                content = it.get("content") or it.get("brief") or ""
                ts = int(it.get("ctime") or 0)
                url = it.get("shareurl") or f"https://www.cls.cn/detail/{sid}"
                out.append(NewsItem(
                    source=self.name,
                    source_id=sid,
                    title=title,
                    content=content,
                    url=url,
                    timestamp=ts,
                    important=bool(it.get("bold")),  # 加粗/红色电报视为重要
                ))
            except Exception as e:  # noqa: BLE001
                log.debug("[cls] 跳过一条解析失败的条目: %s", e)
        return out
