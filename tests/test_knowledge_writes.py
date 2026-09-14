"""模拟 Windows 临时占用目标文件时的替换失败。"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.knowledge.workflow import KnowledgeBase


class KnowledgeWriteTests(unittest.TestCase):
    def test_access_denied_is_not_retried_and_preserves_original(self):
        with TemporaryDirectory() as directory:
            target = Path(directory) / "catalog.json"
            target.write_text('["old"]', encoding="utf-8")
            calls = []

            def busy(source, destination):
                calls.append(source)
                error = PermissionError(13, "拒绝访问")
                error.winerror = 5
                raise error

            with patch.object(Path, "replace", busy), self.assertRaises(PermissionError):
                KnowledgeBase._write(target, ["new"])
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), ["old"])
            self.assertEqual(len(calls), 1)
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])
