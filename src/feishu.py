"""飞书自定义机器人 webhook 推送。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time

import requests

from .models import Digest, NewsItem

log = logging.getLogger(__name__)


class FeishuNotifier:
    def __init__(self, webhook_url: str, secret: str = ""):
        self.webhook_url = webhook_url
        self.secret = secret

    def _sign(self, timestamp: int) -> str:
        # 飞书签名：以 "{timestamp}\n{secret}" 为 key 做 HMAC-SHA256，再 base64
        string_to_sign = f"{timestamp}\n{self.secret}"
        digest = hmac.new(
            string_to_sign.encode("utf-8"), b"", hashlib.sha256
        ).digest()
        return base64.b64encode(digest).decode("utf-8")

    def send_text(self, text: str) -> bool:
        if not self.webhook_url:
            log.warning("未配置飞书 webhook_url，跳过推送。消息内容:\n%s", text)
            return False

        body: dict = {"msg_type": "text", "content": {"text": text}}
        if self.secret:
            ts = int(time.time())
            body["timestamp"] = str(ts)
            body["sign"] = self._sign(ts)

        try:
            resp = requests.post(self.webhook_url, json=body, timeout=10)
            data = resp.json()
        except Exception as e:  # noqa: BLE001
            log.error("飞书推送失败: %s", e)
            return False

        if data.get("code", 0) != 0 and data.get("StatusCode", 0) != 0:
            log.error("飞书返回异常: %s", data)
            return False
        return True

    @staticmethod
    def _format_one(d: Digest, index: int | None = None) -> str:
        var = ("【" + "、".join(d.varieties) + "】") if d.varieties else ""
        hot = "🔥" if getattr(d.item, "priority", 0) >= 1 else ""
        prefix = f"{index}. " if index is not None else ""
        body = (d.summary or d.item.text[:80]).strip()
        dup = f"（+{d.item.dup_count - 1}条同类）" if getattr(d.item, "dup_count", 1) > 1 else ""
        line = f"{prefix}{hot}{var}{body}{dup}".strip()
        if d.item.url:
            line += f"\n   🔗 {d.item.url}"
        return line

    @staticmethod
    def _format_urgent(it: NewsItem, index: int | None = None) -> str:
        reason = f"【{it.urgent_reason}】" if it.urgent_reason else ""
        dup = f"（+{it.dup_count - 1}条同类）" if it.dup_count > 1 else ""
        prefix = f"{index}. " if index is not None else ""
        body = it.text.strip().replace("\n", " ")[:120]
        line = f"{prefix}{reason}{body}{dup}".strip()
        if it.url:
            line += f"\n   🔗 {it.url}"
        return line

    def send_urgent(self, items: list[NewsItem]) -> bool:
        """加急快讯：原文直推、单独成条、🚨 标识（不经 LLM）。"""
        if not items:
            return True
        if len(items) == 1:
            return self.send_text("🚨 加急快讯\n" + self._format_urgent(items[0]))
        header = f"🚨 加急快讯（{len(items)}条）"
        lines = [self._format_urgent(it, i + 1) for i, it in enumerate(items)]
        return self.send_text(header + "\n" + "\n".join(lines))

    def send_digest(self, d: Digest) -> bool:
        """把单条提炼结果格式化为飞书消息。"""
        text = "📊 期货资讯\n" + self._format_one(d)
        return self.send_text(text)

    def send_digests(self, digests: list[Digest]) -> bool:
        """把本轮多条重要资讯合并成一条飞书消息推送。"""
        if not digests:
            return True
        if len(digests) == 1:
            return self.send_digest(digests[0])
        header = f"📊 期货资讯汇总（{len(digests)}条）"
        lines = [self._format_one(d, i + 1) for i, d in enumerate(digests)]
        return self.send_text(header + "\n" + "\n".join(lines))
