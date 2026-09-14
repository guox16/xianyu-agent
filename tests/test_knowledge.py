import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.knowledge import KnowledgeBase, ResearchResult


class KnowledgeTests(unittest.TestCase):
    def test_multiple_games_share_one_file_and_updates_are_isolated(self):
        with TemporaryDirectory() as directory:
            kb = KnowledgeBase(Path(directory))
            kb.register(["甲", "乙"])
            for outcome in kb.process(lambda name: ResearchResult(content=name + "资料", sources=["https://example.com"])):
                self.assertEqual(kb.confirm(outcome["preview_id"]), kb.knowledge_file)
            self.assertEqual(set(kb.materials()), {"甲", "乙"})
            self.assertEqual({entry["material_file"] for entry in kb.entries()}, {"knowledge.json"})
            self.assertEqual(list(kb.root.glob("*.md")), [])
            outcome = kb.process(lambda _: ResearchResult(content="甲新版", sources=["https://example.com"]),
                                 statuses=["已补充"], game_names=["甲"])[0]
            kb.confirm(outcome["preview_id"])
            self.assertIn("甲新版", kb.lookup("甲")["content"])
            self.assertIn("乙资料", kb.lookup("乙")["content"])
            self.assertNotIn("甲新版", kb.lookup("乙")["content"])

    def test_migration_preserves_originals_and_is_repeatable(self):
        with TemporaryDirectory() as directory:
            kb = KnowledgeBase(Path(directory))
            kb.register(["旧游戏"])
            entries = kb.entries()
            entries[0].update(status="已补充", material_file="old.md")
            kb._write(kb.catalog_file, entries)
            (kb.root / "old.md").write_text("原资料及来源", encoding="utf-8")
            self.assertEqual(kb.migrate_materials(), ["旧游戏"])
            self.assertEqual(kb.migrate_materials(), [])
            self.assertEqual(kb.lookup("旧游戏")["content"], "原资料及来源")
            self.assertTrue((kb.root / "old.md").exists())

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
            entries = kb.entries()
            entries[1]["content"] = None
            kb._write(kb.catalog_file, entries)
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
