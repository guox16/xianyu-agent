"""离线验证实际 Agent 工具循环，不消耗 API 额度。"""

import contextlib
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.errors import GraphRecursionError

from app.customer_agent import CustomerAgent
from app.material_tools import query_game_material
from app.materials import load_material


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


if __name__ == "__main__":
    unittest.main()
