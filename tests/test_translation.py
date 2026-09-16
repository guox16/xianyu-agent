import io
import json
import unittest
from unittest.mock import patch

from app.knowledge.translation import translate_name


class TranslationTests(unittest.TestCase):
    def response(self, text, **extra):
        return io.BytesIO(json.dumps(dict(responseStatus=200, responseData={"translatedText": text}, **extra)).encode())

    def test_no_key_and_only_name_is_sent(self):
        with patch("app.knowledge.translation.urlopen", return_value=self.response("Caribbean Legend")) as request:
            self.assertEqual(translate_name("加勒比传奇"), "Caribbean Legend")
            self.assertIn("langpair=zh-CN%7Cen", request.call_args.args[0].full_url)
            self.assertNotIn("key=", request.call_args.args[0].full_url)

    def test_quota_and_changed_identity_are_rejected(self):
        for name, text, extra in [("游戏2", "Game 3", {}), ("游戏：副标题", "Game", {}),
                                  ("游戏", "MYMEMORY WARNING", {"quotaFinished": True}), ("游戏", "", {})]:
            with self.subTest(name=name, text=text), patch("app.knowledge.translation.urlopen", return_value=self.response(text, **extra)):
                with self.assertRaises(ValueError):
                    translate_name(name)

    def test_oversize_name_does_not_call_network(self):
        with patch("app.knowledge.translation.urlopen") as request:
            with self.assertRaises(ValueError):
                translate_name("游" * 200)
            request.assert_not_called()
