"""离线验证会话状态，不发送 API 请求，不读取本地密钥。"""

import contextlib
import io
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from langchain_core.messages import AIMessage
from openai import APITimeoutError

import model_call
from config import Settings


class ConversationTests(unittest.TestCase):
    def setUp(self):
        settings = patch.object(model_call, "load_settings", return_value=Settings(
            "test-key", "test-model", "https://example.com",
        ))
        settings.start()
        self.addCleanup(settings.stop)
        factory = patch.object(model_call, "ChatDeepSeek")
        self.model = factory.start().return_value
        self.addCleanup(factory.stop)
        self.model.invoke.return_value = AIMessage(content="测试回复")

    def test_followup_and_session_isolation(self):
        history = []
        model_call.ask_model("我用笔记本", "测试商品资料", history)
        model_call.ask_model("还需要什么配置？", "测试商品资料", history)
        sent = self.model.invoke.call_args.args[0]
        self.assertEqual([role for role, _ in sent], ["system", "human", "human", "ai", "human"])
        self.assertEqual(sent[2], ("human", "我用笔记本"))
        self.assertEqual(sum("测试商品资料" in text for _, text in sent), 1)
        self.assertEqual(len(history), 4)
        model_call.ask_model("新的买家", "测试商品资料", [])
        self.assertNotIn(("human", "我用笔记本"), self.model.invoke.call_args.args[0])
        model_call.ask_model("独立调用")
        self.assertEqual(len(self.model.invoke.call_args.args[0]), 2)

    def test_failed_turn_does_not_change_history(self):
        history = [("human", "旧问题"), ("ai", "旧回复")]
        original = history.copy()
        self.model.invoke.side_effect = APITimeoutError(request=httpx.Request("POST", "https://example.com"))
        with self.assertRaises(APITimeoutError):
            model_call.ask_model("失败问题", history=history)
        self.assertEqual(history, original)
        self.model.invoke.side_effect = None
        self.model.invoke.return_value = AIMessage(content="")
        with self.assertRaises(ValueError):
            model_call.ask_model("空回复问题", history=history)
        self.assertEqual(history, original)
        self.model.invoke.return_value = AIMessage(content="重试成功")
        model_call.ask_model("重试问题", history=history)
        self.assertEqual(history[-2:], [("human", "重试问题"), ("ai", "重试成功")])

    def test_clear_retains_material_and_commands_do_not_call_model(self):
        inputs = ["  ", "旧问题", "/clear", "新问题", "/exit"]
        with patch.object(model_call, "load_material", return_value="测试商品资料"), \
                patch("builtins.input", side_effect=inputs), contextlib.redirect_stdout(io.StringIO()):
            model_call.main(Path("material.md"))
        self.assertEqual(self.model.invoke.call_count, 2)
        sent = self.model.invoke.call_args.args[0]
        self.assertEqual(len(sent), 3)
        self.assertIn("测试商品资料", sent[1][1])
        self.assertNotIn(("human", "旧问题"), sent)

    def test_cli_continues_after_timeout_and_handles_eof(self):
        self.model.invoke.side_effect = [
            APITimeoutError(request=httpx.Request("POST", "https://example.com")),
            AIMessage(content="成功"),
        ]
        with patch("builtins.input", side_effect=["失败", "重试", EOFError()]), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            model_call.main()
        self.assertIn("请求超时", output.getvalue())
        self.assertIn("成功", output.getvalue())
        self.assertNotIn(("human", "失败"), self.model.invoke.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
