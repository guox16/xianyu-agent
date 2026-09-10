"""离线测试：基础对话、客服 Agent 与菜单；不调用真实模型。"""

import contextlib
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import httpx
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.errors import GraphRecursionError
from openai import APITimeoutError

import main
from app.config import Settings
from app.customer_agent import CustomerAgent
from app.material_tools import query_game_material
from app.materials import load_material
from examples import model_call


class ConversationTests(unittest.TestCase):
    def setUp(self):
        settings = patch("app.model.load_settings", return_value=Settings(
            "test-key", "test-model", "https://example.com",
        ))
        settings.start()
        self.addCleanup(settings.stop)
        factory = patch("app.model.ChatDeepSeek")
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


class ScriptedModel(FakeMessagesListChatModel):
    """只模拟模型决策；工具执行和 Agent 编排使用真实代码。"""

    def bind_tools(self, tools, **kwargs):
        return self


def query_message(name="苏丹的游戏"):
    return AIMessage(content="", tool_calls=[{
        "name": "query_game_material", "args": {"game_name": name}, "id": "query-1", "type": "tool_call",
    }])


class CustomerAgentTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.file = self.directory / "sultans-game.md"
        self.file.write_text("测试商品价格：0.1 元；夸克交付；不远程。", encoding="utf-8")
        root = patch("app.material_tools.MATERIAL_DIR", self.directory)
        root.start()
        self.addCleanup(root.stop)
        output = contextlib.redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def make_customer(self, responses):
        with patch("app.customer_agent.create_model", return_value=ScriptedModel(responses=responses)):
            return CustomerAgent()

    def test_real_tool_loop_and_followup_keep_paired_messages(self):
        customer = self.make_customer([query_message(), AIMessage(content="0.1 元"), AIMessage(content="不远程")])
        with patch("app.material_tools.load_material", wraps=load_material) as loader:
            self.assertEqual(customer.ask("多少钱"), "0.1 元")
            self.assertEqual(customer.ask("能远程吗"), "不远程")
            self.assertEqual(loader.call_count, 1)
        self.assertEqual([message.type for message in customer.history], ["human", "ai", "tool", "ai", "human", "ai"])
        tool_result = customer.history[2]
        self.assertIsInstance(tool_result, ToolMessage)
        self.assertEqual(tool_result.tool_call_id, customer.history[1].tool_calls[0]["id"])
        self.assertEqual(json.loads(tool_result.content)["status"], "ok")
        self.assertIn("0.1", tool_result.content)

    def test_clear_and_new_session_do_not_retain_tool_results(self):
        customer = self.make_customer([query_message(), AIMessage(content="0.1 元")])
        customer.ask("多少钱")
        customer.clear()
        self.assertEqual(customer.history, [])
        other = self.make_customer([query_message(), AIMessage(content="0.1 元")])
        self.assertEqual(other.history, [])
        with patch("app.material_tools.load_material", wraps=load_material) as loader:
            customer.ask("多少钱")
            self.assertEqual(loader.call_count, 1)

    def test_unknown_name_cannot_be_used_as_file_path(self):
        with patch("app.material_tools.load_material") as loader:
            for name in ("未登记的游戏", "../.env", str(self.file)):
                self.assertEqual(query_game_material.invoke({"game_name": name})["status"], "not_found")
            loader.assert_not_called()

    def test_missing_empty_and_invalid_encoding_return_unavailable(self):
        self.file.unlink()
        self.assertEqual(query_game_material.invoke({"game_name": "苏丹的游戏"})["status"], "unavailable")
        for content in (b"", b"\xff"):
            self.file.write_bytes(content)
            self.assertEqual(query_game_material.invoke({"game_name": "苏丹的游戏"})["status"], "unavailable")

    def test_failure_and_loop_limit_do_not_commit_partial_history(self):
        customer = self.make_customer([AIMessage(content="旧回复")])
        customer.ask("你好")
        old = list(customer.history)
        with patch.object(customer.agent, "invoke", side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                customer.ask("多少钱")
        self.assertEqual(customer.history, old)
        # 每次模拟调用都返回独立消息与调用 ID，与真实 API 一致。
        calls = [AIMessage(content="", tool_calls=[{
            "name": "query_game_material", "args": {"game_name": "苏丹的游戏"},
            "id": f"query-{index}", "type": "tool_call",
        }]) for index in range(20)]
        looping = self.make_customer(calls)
        with self.assertRaises(GraphRecursionError):
            looping.ask("多少钱")
        self.assertEqual(looping.history, [])


class MenuTests(unittest.TestCase):
    def test_reenter_chat_creates_new_session_and_clear_is_forwarded(self):
        first, second = MagicMock(), MagicMock()
        first.ask.return_value = "第一场回复"
        second.ask.return_value = "第二场回复"
        inputs = ["1", "多少钱", "/clear", "/exit", "1", "怎么发", "/exit", "0"]
        with patch("app.chat_cli.CustomerAgent", side_effect=[first, second]) as factory, \
                patch("builtins.input", side_effect=inputs), contextlib.redirect_stdout(io.StringIO()) as output:
            main.main()
        self.assertEqual(factory.call_count, 2)
        first.ask.assert_called_once_with("多少钱")
        first.clear.assert_called_once_with()
        second.ask.assert_called_once_with("怎么发")
        self.assertEqual(output.getvalue().count("已返回主菜单"), 2)
        self.assertIn("程序已退出，再见", output.getvalue())

    def test_invalid_input_and_unimplemented_option_do_not_start_agent(self):
        with patch("app.chat_cli.CustomerAgent") as factory, \
                patch("builtins.input", side_effect=["9", "2", "0"]), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            main.main()
        factory.assert_not_called()
        self.assertIn("输入无效", output.getvalue())
        self.assertIn("暂未开发", output.getvalue())

    def test_configuration_error_returns_to_menu(self):
        with patch("app.chat_cli.CustomerAgent", side_effect=ValueError("invalid config")), \
                patch("builtins.input", side_effect=["1", "0"]), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            main.main()
        self.assertIn("配置无效", output.getvalue())
        self.assertIn("已返回主菜单", output.getvalue())

    def test_end_of_input_exits_cleanly(self):
        with patch("builtins.input", side_effect=EOFError), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            main.main()
        self.assertIn("程序已退出", output.getvalue())


if __name__ == "__main__":
    unittest.main()
