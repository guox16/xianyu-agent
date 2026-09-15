import json
import unittest
from unittest.mock import patch

from app.knowledge.research import research_game
from app.knowledge.web_sources import research_wikipedia
from app.knowledge.workflow import ResearchResult


class ResearchLayerTests(unittest.TestCase):
    def test_wiki_success_stops_without_deepseek(self):
        wiki = ResearchResult(content="欧卡百科", sources=["https://zh.wikipedia.org/wiki/欧洲卡车模拟2"],
                              aliases=["Euro Truck Simulator 2"])
        with patch("app.knowledge.research.research_steam", return_value=ResearchResult()) as search, \
                patch("app.knowledge.research.research_deepseek") as deepseek, \
                patch("app.knowledge.web_sources.research_wikipedia", return_value=wiki):
            result = research_game("欧洲卡车模拟2")
            search.assert_called_once_with("欧洲卡车模拟2")
            deepseek.assert_not_called()
            self.assertIn("欧卡百科", result.content)
            self.assertEqual(len(result.sources), 1)
            self.assertEqual(result.aliases, ["Euro Truck Simulator 2"])

    def test_english_store_failure_keeps_available_wiki_content(self):
        wiki = ResearchResult(content="百科资料", sources=["https://zh.wikipedia.org/wiki/游戏"], aliases=["Game"])
        with patch("app.knowledge.research.research_steam", side_effect=[ResearchResult(), TimeoutError()]), \
                patch("app.knowledge.web_sources.research_wikipedia", return_value=wiki):
            self.assertEqual(research_game("游戏").content, "百科资料")

    def test_steam_success_stops_fallback(self):
        success = ResearchResult(content="正文", sources=["https://store.steampowered.com/app/1/"])
        with patch("app.knowledge.research.research_steam", return_value=success), \
                patch("app.knowledge.web_sources.research_wikipedia") as wiki:
            self.assertIs(research_game("游戏"), success)
            wiki.assert_not_called()

    def test_exception_and_no_match_fall_through_in_order(self):
        calls = []
        def provider(label, result=None):
            def run(name):
                calls.append(label)
                if result is None:
                    raise TimeoutError()
                return result
            return run
        success = ResearchResult(content="百科正文", sources=["https://zh.wikipedia.org/wiki/游戏"])
        with patch("app.knowledge.research.research_steam", side_effect=provider("steam")), \
                patch("app.knowledge.web_sources.research_wikipedia", side_effect=provider("wiki", success)):
            self.assertEqual(research_game("游戏").content, "百科正文")
            self.assertEqual(calls, ["steam", "wiki"])

    def test_final_failure_keeps_each_source_reason(self):
        with patch("app.knowledge.research.research_steam", return_value=ResearchResult(reason="搜不到")), \
                patch("app.knowledge.research.research_deepseek", return_value=ResearchResult(reason="未找到资料")), \
                patch("app.knowledge.web_sources.research_wikipedia", return_value=ResearchResult(status="补充失败", reason="同名")):
            result = research_game("游戏")
            self.assertEqual(result.status, "补充失败")
            for label in ["Steam", "维基百科", "DeepSeek"]:
                self.assertIn(label, result.reason)

    def test_deepseek_fallback_runs_directly_after_source_failures(self):
        calls = []
        def steam(name):
            calls.append(name)
            return ResearchResult(content="英文游戏资料", sources=["https://store.steampowered.com/app/1/"]) if name == "Caribbean Legend" else ResearchResult()
        def wiki(name):
            calls.append("wiki")
            return ResearchResult()
        with patch("app.knowledge.research.research_steam", side_effect=steam), \
                patch("app.knowledge.web_sources.research_wikipedia", side_effect=wiki), \
                patch("app.knowledge.research.research_deepseek", return_value=ResearchResult(
                    content="AI 简要资料", model_generated=True)):
            result = research_game("加勒比传奇")
        self.assertEqual(calls, ["加勒比传奇", "wiki"])
        self.assertEqual(result.content, "AI 简要资料")
        self.assertEqual(result.aliases, [])
        self.assertEqual(result.sources, [])

    def test_wiki_reads_actual_article_not_search_snippet(self):
        payload = {"query": {"pages": [{"pageid": 1, "title": "傳送門", "extract": "传送门是一款电子游戏。\n后文", "fullurl": "https://zh.wikipedia.org/wiki/傳送門"}]}}
        with patch("app.knowledge.web_sources.fetch", return_value=(json.dumps(payload), "https://zh.wikipedia.org")):
            result = research_wikipedia("传送门")
            self.assertIn("传送门是一款电子游戏", result.content)
            self.assertNotIn("后文", result.content)
