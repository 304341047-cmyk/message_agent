from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from src.codex_llm import CodexDigester, _resolve_command
from src.digester_base import BaseDigester, extract_json_array
from src.digester_factory import build_digester
from src.llm import LLMDigester
from src.models import NewsItem


def _item(source_id: str, priority: int = 0) -> NewsItem:
    return NewsItem(
        source="test",
        source_id=source_id,
        title="",
        content="沪铜上涨",
        url="",
        timestamp=1,
        priority=priority,
    )


class FakeDigester(BaseDigester):
    def __init__(self, replies: list[str], batch_size: int = 15):
        super().__init__(batch_size)
        self.replies = iter(replies)
        self.prompts: list[str] = []

    def _call_model(self, prompt: str) -> str | None:
        self.prompts.append(prompt)
        return next(self.replies)


class DigesterTests(unittest.TestCase):
    def test_shared_batching_and_parsing(self) -> None:
        digester = FakeDigester([
            '[{"id":"0","important":true,"summary":"铜价上涨","varieties":["沪铜"]}]',
            '[{"id":"0","important":false,"summary":"","varieties":[]}]',
        ], batch_size=1)

        result = digester.digest([_item("1", priority=1), _item("2")])

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].summary, "铜价上涨")
        first_payload = json.loads(digester.prompts[0].rsplit("快讯：\n", 1)[1])
        second_payload = json.loads(digester.prompts[1].rsplit("快讯：\n", 1)[1])
        self.assertTrue(first_payload[0]["hot"])
        self.assertNotIn("hot", second_payload[0])

    def test_extract_json_array_rejects_non_array(self) -> None:
        self.assertIsNone(extract_json_array('{"items": []}'))
        self.assertEqual(extract_json_array("text\n```json\n[]\n```"), [])

    def test_codex_command_is_ephemeral_and_memory_free(self) -> None:
        command = CodexDigester(command="missing-codex", model="test-model")._command()

        self.assertIn("--strict-config", command)
        self.assertIn("--ephemeral", command)
        self.assertIn("--ignore-user-config", command)
        self.assertIn("features.memories=false", command)
        self.assertIn("memories.generate_memories=false", command)
        self.assertIn("memories.use_memories=false", command)
        self.assertEqual(command[-1], "-")
        self.assertNotIn("任何资讯正文", command)

    @unittest.skipUnless(os.name == "nt", "VS Code bundled Codex discovery is Windows-only")
    @patch("src.codex_llm.shutil.which", return_value=None)
    def test_codex_falls_back_to_vscode_extension(self, _which) -> None:
        with tempfile.TemporaryDirectory() as temp_home:
            executable = (
                Path(temp_home)
                / ".vscode"
                / "extensions"
                / "openai.chatgpt-99.0.0-win32-x64"
                / "bin"
                / "windows-x86_64"
                / "codex.exe"
            )
            executable.parent.mkdir(parents=True)
            executable.touch()

            with patch.dict(os.environ, {"USERPROFILE": temp_home}):
                self.assertEqual(_resolve_command("codex"), str(executable))

    @patch("src.codex_llm.subprocess.run")
    def test_codex_prompt_uses_stdin_and_empty_temp_directory(self, run) -> None:
        run.return_value = subprocess.CompletedProcess([], 0, stdout="[]", stderr="")
        digester = CodexDigester(command="missing-codex")

        self.assertEqual(digester._call_model("任何资讯正文"), "[]")

        args, kwargs = run.call_args
        self.assertEqual(args[0][-1], "-")
        self.assertEqual(kwargs["input"], "任何资讯正文")
        self.assertTrue(kwargs["cwd"])
        self.assertNotIn("任何资讯正文", json.dumps(args[0], ensure_ascii=False))

    def test_provider_factory_keeps_both_implementations(self) -> None:
        codex = build_digester({"llm": {"provider": "codex"}})
        claude = build_digester({"llm": {"provider": "claude"}})
        legacy = build_digester({"llm": {"command": "old-claude"}})

        self.assertIsInstance(codex, CodexDigester)
        self.assertIsInstance(claude, LLMDigester)
        self.assertIsInstance(legacy, LLMDigester)
        self.assertEqual(legacy.command, "old-claude")


if __name__ == "__main__":
    unittest.main()
