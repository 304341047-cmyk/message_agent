"""Codex CLI 提炼器：使用 ChatGPT/Codex 订阅，以临时、无记忆会话运行。"""
from __future__ import annotations

import logging
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from .digester_base import BaseDigester

log = logging.getLogger(__name__)


def _find_vscode_codex() -> str | None:
    """查找 VS Code / VS Code Insiders 扩展随附的 Codex CLI。"""
    if os.name != "nt":
        return None

    user_home = Path(os.environ.get("USERPROFILE") or Path.home())
    extension_roots = (
        user_home / ".vscode" / "extensions",
        user_home / ".vscode-insiders" / "extensions",
    )
    candidates: list[Path] = []
    for root in extension_roots:
        candidates.extend(
            root.glob("openai.chatgpt-*/bin/windows-x86_64/codex.exe")
        )

    existing = [path for path in candidates if path.is_file()]
    if not existing:
        return None

    # 扩展更新后目录名会变化；按修改时间选最新安装的一份。
    return str(max(existing, key=lambda path: path.stat().st_mtime))


def _resolve_command(cmd: str) -> str:
    """解析 Codex 可执行文件，兼容 Windows 的 npm ``codex.cmd``。"""
    cmd = os.path.expandvars(os.path.expanduser(cmd.strip()))
    if os.path.splitext(cmd)[1] or os.path.dirname(cmd):
        return shutil.which(cmd) or cmd
    if os.name == "nt":
        for ext in (".cmd", ".exe", ".bat"):
            found = shutil.which(cmd + ext)
            if found:
                return found
    found = shutil.which(cmd)
    if found:
        return found

    if cmd.lower() == "codex":
        bundled = _find_vscode_codex()
        if bundled:
            log.info("PATH 中未找到 codex，改用 VS Code 扩展内置版本：%s", bundled)
            return bundled
    return cmd


class CodexDigester(BaseDigester):
    """通过 ``codex exec`` 进行一次性批量提炼。

    每次调用都强制使用 ephemeral 会话并关闭记忆读写；相关参数不支持时直接失败，
    不会降级成可能出现在历史记录或参与记忆生成的普通会话。
    """

    def __init__(self, command: str = "codex", model: str = "",
                 batch_size: int = 15, timeout_seconds: int = 120):
        super().__init__(batch_size)
        self.command = _resolve_command(command)
        self.model = model
        self.timeout_seconds = int(timeout_seconds)

    def _command(self) -> list[str]:
        cmd = [
            self.command,
            "exec",
            "--strict-config",
            "--ephemeral",
            "--ignore-user-config",
            "--sandbox", "read-only",
            "--skip-git-repo-check",
            "--color", "never",
            "-c", "features.memories=false",
            "-c", "memories.generate_memories=false",
            "-c", "memories.use_memories=false",
        ]
        if self.model:
            cmd += ["--model", self.model]
        # 从 stdin 读取提示词，避免资讯正文出现在进程命令行中。
        cmd.append("-")
        return cmd

    def _call_model(self, prompt: str) -> str | None:
        try:
            # 在一次性空目录中运行，避免 Codex 自动读取项目文件或项目级说明。
            with tempfile.TemporaryDirectory(prefix="message-agent-codex-") as workdir:
                proc = subprocess.run(
                    self._command(),
                    input=prompt,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=self.timeout_seconds,
                    cwd=workdir,
                )
        except FileNotFoundError:
            log.error("找不到 codex 可执行文件（%s）。请安装 Codex CLI、执行 codex login，"
                      "或在配置里填写绝对路径。", self.command)
            return None
        except subprocess.TimeoutExpired:
            log.error("codex 调用超时（%ss）。", self.timeout_seconds)
            return None
        except OSError as e:
            log.error("无法启动 codex（%s）: %s", self.command, e)
            return None

        if proc.returncode != 0:
            log.error("codex 退出码 %s，stderr: %s", proc.returncode, (proc.stderr or "")[:500])
            return None
        return proc.stdout
