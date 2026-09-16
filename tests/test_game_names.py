import unittest
from unittest.mock import patch

from app.knowledge.game_names import search_name, identity_key, match_score
from app.knowledge.research import research_game, research_steam
from app.knowledge.workflow import ResearchResult


class GameNameTests(unittest.TestCase):
    def test_numbered_short_title_matches_full_title_but_not_other_works(self):
        self.assertGreater(match_score("巫师3：狂猎次世代", "巫师3"), 0)
        self.assertGreater(match_score("巫师3", "巫师3：狂猎"), 0)
        self.assertEqual(match_score("巫师3", "巫师2"), 0)
        self.assertEqual(match_score("巫师3", "巫师30"), 0)
        self.assertEqual(match_score("巫师3", "巫师3：狂猎 DLC"), 0)
        self.assertEqual(match_score("使命召唤", "使命召唤：现代战争"), 0)
        self.assertEqual(match_score("游戏3：甲", "游戏3：乙"), 0)

    def test_base_search_is_used_if_full_search_returns_nothing(self):
        with patch("app.knowledge.research.get_json", side_effect=[
            {"items": []}, {"items": [{"id": 1, "name": "巫师3"}]},
            {"1": {"success": True, "data": {"type": "game", "name": "巫师3", "short_description": "游戏介绍"}}},
        ]) as fetch:
            result = research_steam("巫师3：狂猎次世代")
            self.assertTrue(result.content)
            self.assertEqual(fetch.call_args_list[1].kwargs["term"], "巫师3")

    def test_exact_match_wins_and_tied_short_matches_remain_ambiguous(self):
        candidates = [{"id": 1, "name": "游戏3：甲"}, {"id": 2, "name": "游戏3：乙"}]
        with patch("app.knowledge.research.get_json", return_value={"items": candidates}) as fetch:
            self.assertEqual(research_steam("游戏3").status, "补充失败")
            self.assertEqual(fetch.call_count, 1)
        with patch("app.knowledge.research.get_json", side_effect=[
            {"items": candidates + [{"id": 3, "name": "游戏3"}]},
            {"3": {"success": True, "data": {"type": "game", "name": "游戏3", "short_description": "正文"}}},
        ]):
            self.assertEqual(research_steam("游戏3").sources, ["https://store.steampowered.com/app/3/"])

    def test_version_suffixes_and_punctuation(self):
        for name in ["巫师3：狂猎次世代", "巫师3：狂猎（次世代版）", "巫师3：狂猎 次世代 豪华版"]:
            self.assertEqual(identity_key(name), identity_key("巫师3:狂猎"))
        self.assertEqual(search_name("Portal 2 Deluxe Edition"), "Portal 2")

    def test_sequels_subtitles_and_remakes_are_distinct(self):
        self.assertNotEqual(identity_key("巫师3：狂猎"), identity_key("巫师2"))
        self.assertNotEqual(identity_key("Portal"), identity_key("Portal 2"))
        self.assertNotEqual(identity_key("巫师3：狂猎"), identity_key("巫师3：狂猎 血与酒"))
        self.assertEqual(search_name("游戏重制版"), "游戏重制版")

    def test_all_layers_get_base_name_and_result_keeps_warehouse_name(self):
        with patch("app.knowledge.research.research_steam", return_value=ResearchResult()), \
                patch("app.knowledge.web_sources.research_wikipedia", return_value=ResearchResult(content="正文", sources=["https://example.com"])) as official:
            result = research_game("巫师3：狂猎次世代")
            official.assert_called_once_with("巫师3:狂猎")
            self.assertIn("巫师3：狂猎次世代", result.content)
            self.assertIn("不代表已核实", result.content)

    def test_steam_search_uses_base_title_and_reads_matching_game(self):
        with patch("app.knowledge.research.get_json", side_effect=[
            {"items": [{"id": 1, "name": "巫师3：狂猎"}]},
            {"1": {"success": True, "data": {"type": "game", "name": "巫师3：狂猎", "short_description": "游戏介绍"}}},
        ]) as fetch:
            self.assertTrue(research_steam("巫师3：狂猎次世代").content)
            self.assertEqual(fetch.call_args_list[0].kwargs["term"], "巫师3:狂猎")
