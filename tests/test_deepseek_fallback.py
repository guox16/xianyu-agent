import unittest
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.knowledge.deepseek_fallback import research_with_deepseek
from app.knowledge.research import research_game
from app.knowledge.workflow import ResearchResult


class DeepSeekFallbackTests(unittest.TestCase):
    def test_model_output_becomes_short_unverified_material(self):
        model = MagicMock()
        model.return_value.invoke.return_value = SimpleNamespace(
                text='{"summary":"一款海盗题材角色扮演游戏。"}', response_metadata={})
        with patch.dict(sys.modules, {"app.core.model": SimpleNamespace(create_model=model)}):
            result = research_with_deepseek("加勒比传奇：海盗时代")
            self.assertTrue(result.model_generated)
            self.assertIn("DeepSeek 简要资料（待核验）", result.content)
            self.assertEqual(result.sources, [])
            model.return_value.invoke.assert_called_once()

    def test_overlong_or_empty_model_output_is_rejected(self):
        model = MagicMock()
        model.return_value.invoke.return_value = SimpleNamespace(
                text='{"summary":""}', response_metadata={})
        with patch.dict(sys.modules, {"app.core.model": SimpleNamespace(create_model=model)}):
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
        def final(name):
            calls.append("deepseek")
            return ResearchResult(content="AI 整理正文", model_generated=True)
        with patch("app.knowledge.research.research_steam", side_effect=fail("steam")), \
                patch("app.knowledge.web_sources.research_wikipedia", side_effect=fail("wiki")), \
                patch("app.knowledge.research.research_deepseek", side_effect=final):
            self.assertTrue(research_game("游戏").content)
        self.assertEqual(calls, ["steam", "wiki", "deepseek"])

    def test_earlier_success_does_not_call_model(self):
        with patch("app.knowledge.research.research_steam", return_value=ResearchResult(content="正文", sources=["https://example.com"])), \
                patch("app.knowledge.research.research_deepseek") as model:
            research_game("游戏")
            model.assert_not_called()
