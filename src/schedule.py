"""轮询节奏：加急与汇总解耦。

- 加急(行情突变 + 交易所通知)：全天候固定高频抓取(默认 60s)，命中即 🚨 立即推，不耗 LLM。
- 常规汇总(走 LLM)：较慢节奏，把期间攒下的普通消息一次性提炼。这是耗额度的部分，按时段控频：
  - 工作日 08:30–23:00 活跃：默认 15 分钟一次
  - 其余(夜间 23:00–08:30 / 周末)：默认 4 小时一次

均可在 config.yaml 的 schedule 段覆盖。
"""
from __future__ import annotations

from datetime import time as dtime, datetime

DEFAULTS = {
    "enabled": True,
    "urgent_interval": 60,            # 加急抓取间隔（全天候）
    "active_start": "08:30",
    "active_end": "23:00",
    "active_digest_interval": 900,    # 活跃时段汇总间隔（15 分钟）
    "off_digest_interval": 14400,     # 夜间 / 周末汇总间隔（4 小时）
}


def _parse(t: str) -> dtime:
    h, m = str(t).split(":")
    return dtime(int(h), int(m))


def urgent_interval(cfg: dict | None = None) -> int:
    c = {**DEFAULTS, **(cfg or {})}
    return int(c["urgent_interval"])


def digest_interval(cfg: dict | None = None,
                    now: datetime | None = None) -> tuple[int, str]:
    """返回 (汇总间隔秒, 时段标签)。"""
    c = {**DEFAULTS, **(cfg or {})}
    now = now or datetime.now()
    if now.weekday() < 5:  # 周一~周五
        t = now.time()
        if _parse(c["active_start"]) <= t < _parse(c["active_end"]):
            return int(c["active_digest_interval"]), "活跃"
    return int(c["off_digest_interval"]), "夜间/周末"
