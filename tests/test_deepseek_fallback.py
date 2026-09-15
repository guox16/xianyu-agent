import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.knowledge.deepseek_fallback import suggest_names, research_with_deepseek
from app.knowledge.research import research_game
from app.knowledge.workflow import ResearchResult


class DeepSeekFallbackTests(unittest.TestCase):
    def test_model_output_is_only_candidate_not_material(self):
        with patch("app.core.model.create_model") as model:
            model.return_value.invoke.return_value = SimpleNamespace(
                text='{"names":["Caribbean Legend: Age of Pirates"]}', response_metadata={})
            self.assertEqual(suggest_names("加勒比传奇：海盗时代"), ["Caribbean Legend: Age of Pirates"])
            model.return_value.invoke.assert_called_once()

    def test_changed_number_and_missing_subtitle_are_filtered(self):
        with patch("app.core.model.create_model") as model:
            model.return_value.invoke.return_value = SimpleNamespace(
                text='{"names":["Game 2: Chapter", "Game 3"]}', response_metadata={})
            self.assertEqual(suggest_names("游戏3：章节"), [])

    def test_model_success_without_readable_source_is_failure(self):
        with patch("app.knowledge.deepseek_fallback.suggest_names", return_value=["Game"]), \
                patch("app.knowledge.research.research_steam", return_value=ResearchResult()), \
                patch("app.knowledge.web_sources.research_wikipedia", return_value=ResearchResult()):
            result = research_with_deepseek("游戏")
            self.assertFalse(result.content)
            self.assertEqual(result.status, "补充失败")

    def test_deepseek_is_last_and_source_is_preserved(self):
        calls = []
        def fail(label):
            def run(name):
                calls.append(label)
                return ResearchResult()
            return run
        def translate(name):
            calls.append("translation")
            return "Game"
        def final(name):
            calls.append("deepseek")
            return ResearchResult(content="有依据正文", sources=["https://example.com"])
        with patch("app.knowledge.research.research_steam", side_effect=fail("steam")), \
                patch("app.knowledge.web_sources.research_wikipedia", side_effect=fail("wiki")), \
                patch("app.knowledge.research.translate_name", side_effect=translate), \
                patch("app.knowledge.research.research_deepseek", side_effect=final):
            self.assertTrue(research_game("游戏").content)
        self.assertEqual(calls, ["steam", "wiki", "translation", "steam", "deepseek"])

    def test_earlier_success_does_not_call_model(self):
        with patch("app.knowledge.research.research_steam", return_value=ResearchResult(content="正文", sources=["https://example.com"])), \
                patch("app.knowledge.research.research_deepseek") as model:
            research_game("游戏")
            model.assert_not_called()
