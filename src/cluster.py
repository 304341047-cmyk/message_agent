"""相似消息聚类：把讲同一件事的多条快讯合成一组，只把代表喂给 LLM，省调用。

用字符二元组 Jaccard 相似度做无依赖的中文近重复聚类，单轮候选量很小（十几条），
O(n^2) 足够。聚类只在本轮新增候选内进行（相邻时间的重复是主要场景）。
"""
from __future__ import annotations

import re

from .models import NewsItem

# 归一化：去掉「财联社X月X日电」「【标题】」式前缀、空白和标点，降低噪声
_PREFIX = re.compile(r"财联社\d{0,2}月\d{0,2}日电[，,]?")
_PUNCT = re.compile(r"[\s，。、；：！？“”‘’\"'（）()【】《》\-—~·.,!?:;]")


def _normalize(text: str) -> str:
    text = _PREFIX.sub("", text)
    text = _PUNCT.sub("", text)
    return text


def _bigrams(text: str) -> set[str]:
    t = _normalize(text)
    if len(t) < 2:
        return {t} if t else set()
    return {t[i:i + 2] for i in range(len(t) - 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _pick_representative(group: list[NewsItem]) -> NewsItem:
    """优先级高 > 来源标重要 > 文本更长（信息更全） 作为代表。"""
    rep = max(group, key=lambda it: (it.priority, int(it.important), len(it.text)))
    rep.dup_count = len(group)
    # 组内若有任一高优先级/重要/加急，代表也继承
    rep.priority = max(it.priority for it in group)
    rep.important = any(it.important for it in group)
    if any(it.urgent for it in group):
        rep.urgent = True
        if not rep.urgent_reason:
            rep.urgent_reason = next((it.urgent_reason for it in group if it.urgent_reason), "")
    return rep


def cluster(items: list[NewsItem], threshold: float = 0.45
            ) -> tuple[list[NewsItem], dict[str, list[NewsItem]]]:
    """返回 (代表列表, {代表uid: 该组全部成员})。"""
    grams = [_bigrams(it.text) for it in items]
    assigned = [False] * len(items)
    reps: list[NewsItem] = []
    members: dict[str, list[NewsItem]] = {}

    for i in range(len(items)):
        if assigned[i]:
            continue
        group = [items[i]]
        assigned[i] = True
        for j in range(i + 1, len(items)):
            if assigned[j]:
                continue
            if _jaccard(grams[i], grams[j]) >= threshold:
                group.append(items[j])
                assigned[j] = True
        rep = _pick_representative(group)
        reps.append(rep)
        members[rep.uid] = group
    return reps, members
