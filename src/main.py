"""编排：轮询来源 -> 去重 -> 规则预筛 -> LLM 提炼 -> 飞书推送。"""
from __future__ import annotations

import logging
import os
import time

from . import cluster as cluster_mod
from . import priority as priority_mod
from . import schedule as schedule_mod
from . import urgent as urgent_mod
from .config import load_config, load_keywords
from .digester_factory import build_digester
from .feishu import FeishuNotifier
from .prefilter import PreFilter
from .sources.base import Source
from .sources.cls import ClsSource
from .sources.wallstreetcn import WallstreetcnSource
from .storage import Store

log = logging.getLogger(__name__)


def build_sources(cfg: dict) -> list[Source]:
    sources: list[Source] = []
    s = cfg.get("sources", {})
    if s.get("cls", {}).get("enabled"):
        c = s["cls"]
        sources.append(ClsSource(rn=c.get("rn", 50),
                                 only_important=c.get("only_important", False)))
    if s.get("wallstreetcn", {}).get("enabled"):
        w = s["wallstreetcn"]
        sources.append(WallstreetcnSource(limit=w.get("limit", 50),
                                          max_pages=w.get("max_pages", 10)))
    return sources


def fetch_and_urgent(sources, store, notifier,
                     similarity_threshold: float = 0.45,
                     urgent_cfg: dict | None = None) -> list:
    """采集 + 加急直通道。返回本轮新增的「非加急」条目（供汇总缓冲累积）。

    加急(行情突变/交易所通知)在此当场绕过 LLM、立即单独 🚨 推送并标记已推。
    """
    raw = []
    for src in sources:
        items = src.fetch(store.last_ts(src.name))
        log.info("[%s] 拉取 %d 条", src.name, len(items))
        raw.extend(items)

    fresh = store.filter_new(raw)
    if not fresh:
        return []
    log.info("新增 %d 条", len(fresh))

    ucfg = urgent_cfg or {}
    if ucfg.get("enabled", True):
        urgent_mod.mark(fresh, ucfg)
        urgent_items = [it for it in fresh if it.urgent]
        if urgent_items:
            u_reps, u_members = cluster_mod.cluster(urgent_items, similarity_threshold)
            log.info("🚨 加急命中 %d 条（聚类后 %d 条）", len(urgent_items), len(u_reps))
            if notifier.send_urgent(u_reps):
                for r in u_reps:
                    for m in u_members.get(r.uid, [r]):
                        store.mark_pushed(m)
                log.info("已加急推送 %d 条", len(u_reps))
            urgent_uids = {m.uid for g in u_members.values() for m in g}
            fresh = [it for it in fresh if it.uid not in urgent_uids]
    return fresh


def run_digest(buffer, store, prefilter, digester, notifier,
               similarity_threshold: float = 0.45,
               retention_days: int = 30) -> None:
    """对缓冲里的「非加急」条目做：预筛 → 聚类 → LLM 提炼 → 汇总推送。"""
    candidates = prefilter.apply(buffer)
    log.info("汇总：预筛后候选 %d 条（缓冲 %d 条）", len(candidates), len(buffer))
    if candidates:
        priority_mod.mark(candidates)
        reps, members = cluster_mod.cluster(candidates, similarity_threshold)
        log.info("聚类后 %d 组", len(reps))
        digests = digester.digest(reps)

        to_push = []
        for d in digests:
            if d.important or d.item.priority >= 1:
                if not d.summary:
                    d.summary = d.item.text[:60]
                d.important = True
                to_push.append(d)
        log.info("判定重要(含高优先级强制) %d 条", len(to_push))
        to_push.sort(key=lambda d: (-d.item.priority, -d.item.timestamp))

        if to_push and notifier.send_digests(to_push):
            for d in to_push:
                for m in members.get(d.item.uid, [d.item]):
                    store.mark_pushed(m)
            log.info("已汇总推送 %d 条", len(to_push))

    removed = store.prune(retention_days)
    if removed:
        log.info("清理 %d 条 %d 天前的旧记录", removed, retention_days)


def run_once(sources, store, prefilter, digester, notifier,
             similarity_threshold: float = 0.45,
             retention_days: int = 30,
             urgent_cfg: dict | None = None) -> None:
    """单轮全流程（--once 测试用）：加急 + 立即汇总本轮非加急条目。"""
    fresh = fetch_and_urgent(sources, store, notifier, similarity_threshold, urgent_cfg)
    if not fresh:
        log.info("无新增（非加急）条目")
        store.prune(retention_days)
        return
    run_digest(fresh, store, prefilter, digester, notifier,
               similarity_threshold, retention_days)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    cfg = load_config()
    log.info("使用配置: %s", cfg.get("_path"))

    root = cfg.get("_root", os.getcwd())
    storage_cfg = cfg.get("storage", {})
    db_path = storage_cfg.get("db_path", "data/seen.db")
    if not os.path.isabs(db_path):
        db_path = os.path.join(root, db_path)
    retention_days = storage_cfg.get("retention_days", 30)

    sources = build_sources(cfg)
    if not sources:
        raise SystemExit("没有启用任何来源，请检查 config.yaml 的 sources 段。")

    store = Store(db_path)
    kw = load_keywords(root)
    log.info("词库 keywords.yaml: 预筛 %d 词 / 加急名 %d / 动作 %d / 突变 %d / 排除 %d",
             len(kw.get("prefilter", [])), len(kw.get("urgent_names", [])),
             len(kw.get("urgent_actions", [])), len(kw.get("urgent_moves", [])),
             len(kw.get("urgent_excludes", [])))
    pf_cfg = cfg.get("prefilter", {})
    prefilter = PreFilter(
        keywords=pf_cfg.get("keywords") or kw.get("prefilter", []),
        keep_source_important=pf_cfg.get("keep_source_important", True),
    )
    digester = build_digester(cfg)
    log.info("LLM 提供方: %s", cfg.get("llm", {}).get("provider", "claude"))
    f_cfg = cfg.get("feishu", {})
    notifier = FeishuNotifier(
        webhook_url=f_cfg.get("webhook_url", ""),
        secret=f_cfg.get("secret", ""),
    )

    threshold = pf_cfg.get("similarity_threshold", 0.45)
    urgent_cfg = {
        **cfg.get("urgent", {}),
        "names": kw.get("urgent_names", []),
        "actions": kw.get("urgent_actions", []),
        "moves": kw.get("urgent_moves", []),
        "excludes": kw.get("urgent_excludes", []),
    }
    sched_cfg = cfg.get("schedule", {})

    u_interval = schedule_mod.urgent_interval(sched_cfg)
    log.info("启动：加急每 %ds 抓一次（全天候）；常规汇总活跃/夜间分档。Ctrl+C 退出。",
             u_interval)

    buffer: list = []          # 累积「非加急」条目，到汇总间隔再一次性走 LLM
    last_digest = 0.0          # 0 表示首轮即汇总（处理启动时的增量回填）
    try:
        while True:
            try:
                # 加急快循环：每 u_interval 秒抓取一次，命中加急立即推
                fresh = fetch_and_urgent(sources, store, notifier, threshold, urgent_cfg)
                buffer.extend(fresh)

                # 常规汇总：到点才走 LLM（耗额度的部分按时段控频）
                d_interval, label = schedule_mod.digest_interval(sched_cfg)
                if time.time() - last_digest >= d_interval:
                    if buffer:
                        log.info("[%s 汇总] 处理缓冲 %d 条", label, len(buffer))
                        run_digest(buffer, store, prefilter, digester, notifier,
                                   threshold, retention_days)
                        buffer = []
                    last_digest = time.time()
            except Exception as e:  # noqa: BLE001
                log.exception("本轮处理出错: %s", e)
            time.sleep(u_interval)
    except KeyboardInterrupt:
        log.info("收到退出信号，关闭。")
    finally:
        store.close()


if __name__ == "__main__":
    main()
