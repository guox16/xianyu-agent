import json
import unittest
from unittest.mock import patch

from app.knowledge.research import research_game
from app.knowledge.web_sources import research_wikipedia, research_baidu, has_identity
from app.knowledge.workflow import ResearchResult


class ResearchLayerTests(unittest.TestCase):
    def test_steam_success_stops_fallback(self):
        success = ResearchResult(content="正文", sources=["https://store.steampowered.com/app/1/"])
        with patch("app.knowledge.research.research_steam", return_value=success), \
                patch("app.knowledge.web_sources.research_official") as official:
            self.assertIs(research_game("游戏"), success)
            official.assert_not_called()

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
                patch("app.knowledge.web_sources.research_official", side_effect=provider("official", ResearchResult())), \
                patch("app.knowledge.web_sources.research_wikipedia", side_effect=provider("wiki", success)), \
                patch("app.knowledge.web_sources.research_baidu") as baidu:
            self.assertEqual(research_game("游戏").content, "百科正文")
            self.assertEqual(calls, ["steam", "official", "wiki"])
            baidu.assert_not_called()

    def test_final_failure_keeps_each_source_reason(self):
        with patch("app.knowledge.research.research_steam", return_value=ResearchResult(reason="搜不到")), \
                patch("app.knowledge.web_sources.research_official", return_value=ResearchResult(reason="官网不可读")), \
                patch("app.knowledge.web_sources.research_wikipedia", return_value=ResearchResult(status="名称待确认", reason="同名")), \
                patch("app.knowledge.web_sources.research_baidu", side_effect=TimeoutError):
            result = research_game("游戏")
            self.assertEqual(result.status, "名称待确认")
            for label in ["Steam", "官网", "维基百科", "百度"]:
                self.assertIn(label, result.reason)

    def test_wiki_reads_actual_article_not_search_snippet(self):
        payload = {"query": {"pages": [{"pageid": 1, "title": "傳送門", "extract": "传送门是一款电子游戏。\n后文", "fullurl": "https://zh.wikipedia.org/wiki/傳送門"}]}}
        with patch("app.knowledge.web_sources.fetch", return_value=(json.dumps(payload), "https://zh.wikipedia.org")):
            result = research_wikipedia("传送门")
            self.assertIn("传送门是一款电子游戏", result.content)
            self.assertNotIn("后文", result.content)

    def test_baidu_captcha_never_becomes_material(self):
        with patch("app.knowledge.web_sources.fetch", return_value=("<title>百度安全验证</title>", "https://www.baidu.com")):
            with self.assertRaises(ValueError):
                research_baidu("游戏")

    def test_search_summary_alone_is_not_material(self):
        with patch("app.knowledge.web_sources.fetch", return_value=("<p>游戏的搜索摘要，非常精彩。</p>", "https://www.baidu.com")):
            self.assertFalse(research_baidu("游戏").content)
        self.assertFalse(has_identity("Portal", "Portal 2 | Official Site"))
