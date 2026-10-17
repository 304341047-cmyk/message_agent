"""配置加载。"""
from __future__ import annotations

import os
from typing import Any

import yaml


def load_config(path: str | None = None) -> dict[str, Any]:
    """加载 config.yaml；找不到时回退到 config.example.yaml。"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = []
    if path:
        candidates.append(path)
    candidates.append(os.path.join(root, "config.yaml"))
    candidates.append(os.path.join(root, "config.example.yaml"))

    for p in candidates:
        if p and os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            cfg["_path"] = p
            cfg["_root"] = root
            return cfg

    raise FileNotFoundError(
        "未找到 config.yaml 或 config.example.yaml，请先复制示例配置。"
    )


def load_keywords(root: str | None = None) -> dict[str, list[str]]:
    """加载可随时编辑的 keywords.yaml（预筛/加急词库）。
    找不到时回退 keywords.example.yaml，再找不到返回空 dict（由各处用代码内置默认兜底）。"""
    root = root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in ("keywords.yaml", "keywords.example.yaml"):
        p = os.path.join(root, name)
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            # 过滤空值，保证返回的都是非空 list
            return {k: [w for w in (v or []) if w] for k, v in data.items()}
    return {}
