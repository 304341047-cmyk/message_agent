"""LLM 提炼层：通过 headless 的 `claude -p` 调用，复用 Claude 订阅额度。

不直接调 Anthropic API（订阅不提供可嵌入的 API key），而是 shell 调本机
已登录的 claude CLI。CCSwitch 切到哪个 provider/模型，这里就用哪个。
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess

from .digester_base import BaseDigester, extract_json_array

log = logging.getLogger(__name__)


def _resolve_command(cmd: str) -> str:
    """把 'claude' 解析成实际可执行文件。

    Windows 上 npm 全局装的是 claude.cmd / claude.ps1（不是 .exe），
    Python subprocess 直接调 'claude' 会 FileNotFoundError，需补扩展名。
    """
    if os.path.splitext(cmd)[1]:           # 配置里已带扩展名/绝对路径
        return shutil.which(cmd) or cmd
    if os.name == "nt":
        for ext in (".cmd", ".exe", ".bat"):  # 优先可被 subprocess 直接执行的
            found = shutil.which(cmd + ext)
            if found:
                return found
    return shutil.which(cmd) or cmd


class LLMDigester(BaseDigester):
    """Claude CLI 提炼器（保留原有实现与配置兼容性）。"""

    def __init__(self, command: str = "claude", model: str = "",
                 batch_size: int = 15, timeout_seconds: int = 120):
        super().__init__(batch_size)
        self.command = _resolve_command(command)
        self.model = model
        self.timeout_seconds = timeout_seconds

    def _call_model(self, prompt: str) -> str | None:
        cmd = [self.command, "-p"]
        if self.model:
            cmd += ["--model", self.model]
        try:
            proc = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError:
            log.error("找不到 claude 可执行文件（%s）。请确认已安装 Claude Code 并在 PATH 中，"
                      "或在配置里用绝对路径。", self.command)
            return None
        except subprocess.TimeoutExpired:
            log.error("claude 调用超时（%ss）。", self.timeout_seconds)
            return None

        if proc.returncode != 0:
            log.error("claude 退出码 %s，stderr: %s", proc.returncode, (proc.stderr or "")[:300])
            return None
        return proc.stdout


def _extract_json_array(text: str):
    """向后兼容原模块中的解析函数。"""
    return extract_json_array(text)
