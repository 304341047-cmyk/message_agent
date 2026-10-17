"""根据配置选择 Claude 或 Codex 提炼器。"""
from __future__ import annotations

from .codex_llm import CodexDigester
from .digester_base import BaseDigester
from .llm import LLMDigester


def build_digester(cfg: dict) -> BaseDigester:
    """创建配置指定的提炼器，并兼容旧版 Claude 配置。"""
    llm_cfg = cfg.get("llm", {})
    provider = str(llm_cfg.get("provider", "claude")).strip().lower()
    batch_size = llm_cfg.get("batch_size", 15)
    timeout_seconds = llm_cfg.get("timeout_seconds", 120)

    if provider == "claude":
        provider_cfg = llm_cfg.get("claude", {}) or {}
        return LLMDigester(
            command=provider_cfg.get("command", llm_cfg.get("command", "claude")),
            model=provider_cfg.get("model", llm_cfg.get("model", "")),
            batch_size=batch_size,
            timeout_seconds=timeout_seconds,
        )
    if provider == "codex":
        provider_cfg = llm_cfg.get("codex", {}) or {}
        return CodexDigester(
            command=provider_cfg.get("command", "codex"),
            model=provider_cfg.get("model", ""),
            batch_size=batch_size,
            timeout_seconds=timeout_seconds,
        )
    raise ValueError("llm.provider 只支持 'claude' 或 'codex'，当前为: " + provider)
