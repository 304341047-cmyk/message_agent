"""SQLite 去重 + 持久化。"""
from __future__ import annotations

import os
import sqlite3
import time
from collections.abc import Iterable

from .models import NewsItem


class Store:
    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seen (
                uid        TEXT PRIMARY KEY,
                source     TEXT,
                title      TEXT,
                content    TEXT,
                url        TEXT,
                ts         INTEGER,
                pushed     INTEGER DEFAULT 0,
                created_at INTEGER
            )
            """
        )
        self.conn.commit()

    def filter_new(self, items: Iterable[NewsItem]) -> list[NewsItem]:
        """返回数据库中尚未出现过的条目，并把它们登记入库（pushed=0）。"""
        fresh: list[NewsItem] = []
        now = int(time.time())
        for it in items:
            cur = self.conn.execute("SELECT 1 FROM seen WHERE uid = ?", (it.uid,))
            if cur.fetchone():
                continue
            self.conn.execute(
                "INSERT INTO seen (uid, source, title, content, url, ts, pushed, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
                (it.uid, it.source, it.title, it.content, it.url, it.timestamp, now),
            )
            fresh.append(it)
        self.conn.commit()
        return fresh

    def mark_pushed(self, item: NewsItem) -> None:
        self.conn.execute("UPDATE seen SET pushed = 1 WHERE uid = ?", (item.uid,))
        self.conn.commit()

    def last_ts(self, source: str) -> int:
        """某来源已入库条目的最大时间戳；没有则返回 0。
        用于增量翻页：只取比它更新的条目。"""
        cur = self.conn.execute(
            "SELECT MAX(ts) FROM seen WHERE source = ?", (source,)
        )
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def prune(self, retention_days: int) -> int:
        """删除 created_at 早于 retention_days 天前的旧行，返回删除条数。
        只影响磁盘体积——去重只需保留到 uid 不再可能重现（接口滚动窗口仅几小时），
        故删旧行绝对安全。retention_days<=0 表示不清理。"""
        if retention_days <= 0:
            return 0
        cutoff = int(time.time()) - retention_days * 86400
        cur = self.conn.execute("DELETE FROM seen WHERE created_at < ?", (cutoff,))
        self.conn.commit()
        return cur.rowcount

    def close(self) -> None:
        self.conn.close()
