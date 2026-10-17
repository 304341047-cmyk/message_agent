"""入口：python run.py

可选：
  python run.py --once    只跑一轮就退出（方便测试）
"""
from __future__ import annotations

import sys

from src.main import (
    FeishuNotifier, PreFilter, Store, build_digester, build_sources, load_config,
    load_keywords, logging, os, run_once,
)


def _once() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    cfg = load_config()
    root = cfg.get("_root", os.getcwd())
    storage_cfg = cfg.get("storage", {})
    db_path = storage_cfg.get("db_path", "data/seen.db")
    if not os.path.isabs(db_path):
        db_path = os.path.join(root, db_path)
    retention_days = storage_cfg.get("retention_days", 30)
    store = Store(db_path)
    kw = load_keywords(root)
    pf = cfg.get("prefilter", {})
    prefilter = PreFilter(pf.get("keywords") or kw.get("prefilter", []),
                          pf.get("keep_source_important", True))
    digester = build_digester(cfg)
    fc = cfg.get("feishu", {})
    notifier = FeishuNotifier(fc.get("webhook_url", ""), fc.get("secret", ""))
    threshold = pf.get("similarity_threshold", 0.45)
    urgent_cfg = {
        **cfg.get("urgent", {}),
        "names": kw.get("urgent_names", []),
        "actions": kw.get("urgent_actions", []),
        "moves": kw.get("urgent_moves", []),
        "excludes": kw.get("urgent_excludes", []),
    }
    run_once(build_sources(cfg), store, prefilter, digester, notifier,
             threshold, retention_days, urgent_cfg)
    store.close()


if __name__ == "__main__":
    if "--once" in sys.argv:
        _once()
    else:
        from src.main import main
        main()
