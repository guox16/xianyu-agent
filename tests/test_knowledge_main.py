import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.knowledge.main import generate, main, pending_previews, update_from_share
from app.knowledge.research import research_steam
from app.knowledge.workflow import KnowledgeBase, ResearchResult


class KnowledgeMainTests(unittest.TestCase):
    def test_all_entries_processed_without_quantity_limit(self):
        with TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            kb = KnowledgeBase(Path(directory))
            kb.register([f"游戏{i}" for i in range(8)])
            with patch("builtins.input", side_effect=AssertionError("不能询问数量")):
                generate(kb, lambda name: ResearchResult(content=name, sources=["https://example.com"]))
            self.assertEqual(len(kb.entries()), 8)
            self.assertTrue(all(e["status"] == "已补充" for e in kb.entries()))
            self.assertFalse((kb.root / "catalog.json").exists())
            self.assertFalse((kb.root / "previews").exists())

    def test_import_failure_does_not_start_generation(self):
        with TemporaryDirectory() as directory, patch("builtins.input", side_effect=["bad"]), \
                patch("app.knowledge.main.generate") as generate_mock, contextlib.redirect_stdout(io.StringIO()):
            main(Path(directory))
            generate_mock.assert_not_called()

    def test_direct_call_imports_and_generates_without_input(self):
        report = {"games": [{"game_name": "游戏", "status": "待补充", "reason": ""}]}
        with TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()), \
                patch("builtins.input", side_effect=AssertionError("接口不能要求输入")), \
                patch("app.knowledge.main.scan", return_value=report):
            result = update_from_share("https://pan.quark.cn/s/abc", root=Path(directory),
                                       research=lambda _: ResearchResult(content="正文", sources=["https://example.com"]))
            self.assertEqual(result["added"], 1)
            self.assertEqual(result["results"][0]["result"], "已保存")

    def test_cli_only_asks_for_link(self):
        with patch("builtins.input", side_effect=["https://pan.quark.cn/s/abc"]) as ask, \
                patch("app.knowledge.main.update_from_share") as update:
            main()
            ask.assert_called_once()
            update.assert_called_once_with("https://pan.quark.cn/s/abc", root=None)

    def test_generation_saves_without_per_game_input_and_continues_after_failure(self):
        with TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            kb = KnowledgeBase(Path(directory))
            kb.register(["失败游戏", "成功游戏", "歧义游戏"])

            def research(name):
                if name == "失败游戏":
                    raise TimeoutError()
                if name == "歧义游戏":
                    return ResearchResult(status="补充失败", reason="同名游戏")
                return ResearchResult(content="已核实正文", sources=["https://example.com"])

            with patch("builtins.input", side_effect=AssertionError("批量生成不应询问")) as ask:
                generate(kb, research)
            self.assertEqual(ask.call_count, 0)
            self.assertEqual(kb.entries()[0]["status"], "补充失败")
            self.assertEqual(kb.entries()[1]["status"], "已补充")
            self.assertIn("已核实正文", kb.lookup("成功游戏")["content"])
            self.assertEqual(kb.entries()[2]["status"], "补充失败")
            self.assertIsNone(kb.entries()[2]["material_file"])
            self.assertEqual(pending_previews(kb), {})
            self.assertFalse((kb.root / "generation-report.json").exists())

    def test_existing_preview_is_saved_without_research(self):
        with TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            kb = KnowledgeBase(Path(directory))
            kb.register(["游戏"])
            kb.process(lambda _: ResearchResult(content="正文", sources=["https://example.com"]))
            with patch("builtins.input", side_effect=AssertionError("不应询问")), patch("app.knowledge.main.research_game") as research:
                generate(kb, research)
                research.assert_not_called()
            self.assertEqual(kb.entries()[0]["status"], "已补充")

    def test_save_failure_keeps_preview_and_continues(self):
        with TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            kb = KnowledgeBase(Path(directory))
            kb.register(["保存失败", "成功"])
            confirm = kb.confirm
            def save(preview_id):
                if pending_previews(kb)["保存失败"][0] == preview_id:
                    raise OSError("磁盘写入失败")
                return confirm(preview_id)
            with patch("builtins.input", side_effect=["all"]), patch.object(kb, "confirm", side_effect=save):
                generate(kb, lambda _: ResearchResult(content="正文", sources=["https://example.com"]))
            self.assertIn("保存失败", pending_previews(kb))
            self.assertEqual(kb.entries()[1]["status"], "已补充")

    def test_menu_returns_on_eof(self):
        with TemporaryDirectory() as directory, patch("builtins.input", side_effect=EOFError), \
                contextlib.redirect_stdout(io.StringIO()):
            main(Path(directory))


class SteamResearchTests(unittest.TestCase):
    def test_non_exact_match_does_not_use_wrong_game(self):
        with patch("app.knowledge.research.get_json", return_value={"items": [{"id": 620, "name": "Portal 2"}]}) as fetch:
            result = research_steam("Portal")
            self.assertEqual(result.status, "补充失败")
            self.assertFalse(result.content)
            self.assertEqual(fetch.call_count, 1)

    def test_official_details_generate_reference_without_seller_price(self):
        with patch("app.knowledge.research.get_json", side_effect=[
            {"items": [{"id": 400, "name": "Portal"}]},
            {"400": {"success": True, "data": {"type": "game", "name": "Portal",
                "short_description": "<b>解谜游戏</b>", "pc_requirements": {"minimum": "内存<br>2 GB"},
                "price_overview": {"final_formatted": "¥ 99"}}}},
        ]):
            result = research_steam("Portal")
            self.assertIn("解谜游戏", result.content)
            self.assertIn("内存\n2 GB", result.content)
            self.assertNotIn("99", result.content)
            self.assertEqual(result.sources, ["https://store.steampowered.com/app/400/"])
