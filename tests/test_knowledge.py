import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.knowledge import KnowledgeBase, ResearchResult


class KnowledgeTests(unittest.TestCase):
    def test_failure_continues_preview_requires_confirmation_and_lookup(self):
        with TemporaryDirectory() as directory:
            kb = KnowledgeBase(Path(directory))
            kb.register(["搜不到", "可补充", "搜不到"])

            def research(name):
                if name == "搜不到":
                    raise TimeoutError()
                return ResearchResult(content="有依据的资料", sources=["https://example.com/game"])

            outcomes = kb.process(research)
            self.assertEqual(len(outcomes), 2)
            self.assertEqual(kb.entries()[0]["status"], "补充失败")
            self.assertIsNone(kb.entries()[0]["material_file"])
            self.assertTrue(kb.lookup("可补充")["registered"])
            self.assertIsNone(kb.lookup("可补充")["content"])
            kb.confirm(outcomes[1]["preview_id"])
            self.assertIn("有依据的资料", kb.lookup("可补充")["content"])
            self.assertFalse(kb.lookup("未登记")["registered"])
            kb.register(["可补充"])
            self.assertEqual(kb.entries()[1]["status"], "已补充")
            (kb.root / kb.entries()[1]["material_file"]).unlink()
            self.assertTrue(kb.lookup("可补充")["registered"])
            self.assertIsNone(kb.lookup("可补充")["content"])

    def test_no_sources_and_ambiguous_name_do_not_create_material(self):
        with TemporaryDirectory() as directory:
            kb = KnowledgeBase(Path(directory))
            kb.register(["同名游戏"])
            kb.process(lambda _: ResearchResult(content="未核实内容", status="名称待确认", reason="存在同名游戏"))
            self.assertEqual(kb.entries()[0]["status"], "名称待确认")
            self.assertIsNone(kb.entries()[0]["material_file"])

    def test_retry_invalidates_old_preview(self):
        with TemporaryDirectory() as directory:
            kb = KnowledgeBase(Path(directory))
            kb.register(["游戏"])
            preview = kb.process(lambda _: ResearchResult(content="资料", sources=["https://example.com"]))[0]
            kb.process(lambda _: ResearchResult(reason="网页无法访问"))
            with self.assertRaises(ValueError):
                kb.confirm(preview["preview_id"])
