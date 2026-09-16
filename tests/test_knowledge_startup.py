"""用真实子进程验证直接运行文件和 -m 模块启动。"""

import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


class KnowledgeStartupTests(unittest.TestCase):
    def test_both_startup_modes_prompt_for_link(self):
        root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        with TemporaryDirectory() as directory:
            modes = [([str(root / "app/knowledge/main.py")], directory),
                     (["-m", "app.knowledge.main"], root)]
            for args, cwd in modes:
                with self.subTest(args=args):
                    result = subprocess.run(
                        [sys.executable, "-X", "utf8", *args], input="",
                        capture_output=True, text=True, encoding="utf-8",
                        cwd=cwd, env=env, timeout=15,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("夸克分享链接：", result.stdout)
                    self.assertNotIn("请选择", result.stdout)
