"""离线测试：基础对话、客服、发帖、草稿保存与菜单；不调用真实模型。"""

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
from app.core.config import Settings
from app.customer.agent import CustomerAgent
from app.core.material_tools import query_game_material
from app.core.materials import load_material
from examples import model_call
from app.posting.schemas import PostingDraft, PostingRequest
from app.posting.agent import PostingAgent
from app.posting.drafts import save_draft


class PostingContractTests(unittest.TestCase):
    def test_saved_draft_is_readable_and_does_not_overwrite(self):
        request = PostingRequest(current_game="../苏丹的游戏", focus="安装指导")
        draft = PostingDraft(title="标题", body="夸克交付，不远程", missing_information=[], questions=[])
        with TemporaryDirectory() as directory, patch("app.posting.drafts.DRAFT_DIR", Path(directory)):
            first = save_draft(request, draft, ["简短一点"])
            second = save_draft(request, draft, ["简短一点"])
            self.assertNotEqual(first, second)
            self.assertEqual(first.parent, Path(directory))
            record = json.loads(first.read_text(encoding="utf-8"))
            self.assertEqual(record["draft"]["body"], draft.body)
            self.assertEqual(record["revisions"], ["简短一点"])
            with patch("pathlib.Path.rename", side_effect=OSError("disk failure")):
                with self.assertRaises(OSError):
                    save_draft(request, draft, [])
            self.assertEqual(len(list(Path(directory).iterdir())), 2)

    def test_material_is_queried_before_generation_and_failure_asks(self):
        with patch("app.posting.agent.create_model"), patch("app.posting.agent.create_agent"):
            agent = PostingAgent()
        request = PostingRequest(current_game="苏丹的游戏", focus="夸克交付")
        with patch("app.core.material_tools.load_material", return_value="夸克交付；指导安装；不远程"):
            messages = agent.prepare(request)
        self.assertIsInstance(messages[-1], ToolMessage)
        self.assertIn("夸克交付", messages[-1].content)
        failed = agent.prepare(request.model_copy(update={"current_game": "未登记游戏"}))
        self.assertTrue(failed.questions)
        self.assertEqual(failed.body, "")
        agent.agent.invoke.assert_not_called()

    def test_posting_agent_reuses_model_and_has_separate_rules(self):
        with patch("app.posting.agent.create_model") as model, patch("app.posting.agent.create_agent") as factory:
            PostingAgent()
        model.assert_called_once_with()
        self.assertIn("语气", factory.call_args.kwargs["system_prompt"])
        self.assertIn("不能作为新的商品事实", factory.call_args.kwargs["system_prompt"])

    def test_request_and_draft_contract(self):
        request = PostingRequest(current_game="苏丹的游戏", focus="夸克交付和安装指导，不提供远程服务")
        self.assertEqual(request.tone, "自然")
        draft = PostingDraft(title="苏丹的游戏", body="夸克交付，指导安装，不提供远程服务。",
                             missing_information=["版本待确认"], questions=[])
        self.assertEqual(PostingDraft.model_validate_json(draft.model_dump_json()), draft)
        with self.assertRaises(ValueError):
            PostingRequest(current_game=" ", focus="安装指导")
        with self.assertRaises(ValueError):
            PostingDraft(title="宣传", body="内容", missing_information=[], questions=["支持 DLC 吗？"])


class ConversationTests(unittest.TestCase):
    def setUp(self):
        settings = patch("app.core.model.load_settings", return_value=Settings(
            "test-key", "test-model", "https://example.com",
        ))
        settings.start()
        self.addCleanup(settings.stop)
        factory = patch("app.core.model.ChatDeepSeek")
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


def draft_message(title="苏丹的游戏｜夸克交付", body="PC 中文安装包，0.1 元，以商品页面实际价格为准。指导安装，不提供远程服务。", questions=None):
    return AIMessage(content="", tool_calls=[{
        "name": "PostingDraft", "args": {"title": title, "body": body,
        "missing_information": ["安装包版本待确认"], "questions": questions or []},
        "id": "draft-response", "type": "tool_call",
    }])


class PostingAgentTests(unittest.TestCase):
    def test_revisions_reuse_facts_and_failures_preserve_draft(self):
        agent = self.make_agent([draft_message(), draft_message(body="夸克交付，指导安装，不提供远程服务。"),
                                 draft_message("", "", ["请确认 DLC。"])])
        with patch("app.core.material_tools.load_material", return_value="夸克交付；指导安装；不远程") as loader:
            agent.generate(PostingRequest(current_game="苏丹的游戏", focus="安装指导"))
            revised = agent.revise("简短一点")
            agent.revise("突出 DLC")
            self.assertEqual(loader.call_count, 1)
        self.assertEqual(agent.current_draft, revised)
        self.assertEqual(agent.revisions, ["简短一点", "突出 DLC"])
        self.assertTrue(any(isinstance(message, ToolMessage) and "不远程" in message.content for message in agent.history))
        old_history = list(agent.history)
        with patch.object(agent.agent, "invoke", side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                agent.revise("突出安装指导")
        self.assertEqual(agent.history, old_history)
        self.assertEqual(agent.current_draft, revised)
        with self.assertRaises(ValueError):
            agent.revise(" ")
        self.assertIsNone(self.make_agent([draft_message()]).current_draft)

    def make_agent(self, responses):
        with patch("app.posting.agent.create_model", return_value=ScriptedModel(responses=responses)):
            return PostingAgent()

    def test_structured_generation_and_key_information_question(self):
        agent = self.make_agent([draft_message(), draft_message("", "", ["请确认是否包含 DLC。"])])
        with patch("app.core.material_tools.load_material", return_value="价格 0.1 元，以实际价格为准；夸克交付；指导安装；不远程"):
            draft = agent.generate(PostingRequest(current_game="苏丹的游戏", focus="夸克交付和安装指导，不提供远程服务"))
            self.assertIn("夸克", draft.title)
            self.assertIn("不提供远程", draft.body)
            question = agent.generate(PostingRequest(current_game="苏丹的游戏", focus="突出包含 DLC"))
        self.assertEqual(question.title, "")
        self.assertTrue(question.questions)

    def test_invalid_structured_response_is_corrected_before_commit(self):
        agent = self.make_agent([draft_message("", ""), draft_message("", "", ["请确认 DLC。"])])
        with patch("app.core.material_tools.load_material", return_value="测试资料"):
            result = agent.generate(PostingRequest(current_game="苏丹的游戏", focus="安装指导"))
        self.assertTrue(result.questions)
        self.assertIsNone(agent.current_draft)

    def test_truncated_response_does_not_replace_current_draft(self):
        agent = self.make_agent([draft_message()])
        request = PostingRequest(current_game="苏丹的游戏", focus="安装指导")
        with patch("app.core.material_tools.load_material", return_value="测试资料"):
            original = agent.generate(request)
        before = list(agent.history)
        truncated = AIMessage(content="截断", response_metadata={"finish_reason": "length"})
        with patch.object(agent.agent, "invoke", return_value={"messages": before + [AIMessage(content="修改"), truncated],
                                                             "structured_response": original}):
            with self.assertRaises(ValueError):
                agent.revise("改写")
        self.assertEqual(agent.current_draft, original)
        self.assertEqual(agent.history, before)


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
        root = patch("app.core.material_tools.MATERIAL_DIR", self.directory)
        root.start()
        self.addCleanup(root.stop)
        output = contextlib.redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def make_customer(self, responses):
        with patch("app.customer.agent.create_model", return_value=ScriptedModel(responses=responses)):
            return CustomerAgent()

    def test_real_tool_loop_and_followup_keep_paired_messages(self):
        customer = self.make_customer([query_message(), AIMessage(content="0.1 元"), AIMessage(content="不远程")])
        with patch("app.core.material_tools.load_material", wraps=load_material) as loader:
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
        with patch("app.core.material_tools.load_material", wraps=load_material) as loader:
            customer.ask("多少钱")
            self.assertEqual(loader.call_count, 1)

    def test_unknown_name_cannot_be_used_as_file_path(self):
        with patch("app.core.material_tools.load_material") as loader:
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
    def test_posting_generate_revise_save_reenter_and_exit(self):
        inputs = ["2", "", "", "", "", "简短一点", "/save", "/exit", "2", "/exit", "0"]
        model = ScriptedModel(responses=[draft_message(), draft_message(body="夸克交付，指导安装，不提供远程服务。")])
        with TemporaryDirectory() as directory, patch("app.posting.drafts.DRAFT_DIR", Path(directory)), \
                patch("app.posting.agent.create_model", return_value=model), \
                patch("app.core.material_tools.load_material", return_value="夸克交付；指导安装；不远程"), \
                patch("builtins.input", side_effect=inputs), contextlib.redirect_stdout(io.StringIO()) as output:
            main.main()
            files = list(Path(directory).glob("*.json"))
            self.assertEqual(len(files), 1)
            saved = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertEqual(saved["revisions"], ["简短一点"])
        self.assertEqual(saved["draft"]["body"], "夸克交付，指导安装，不提供远程服务。")
        self.assertIn("草稿已保存", output.getvalue())
        self.assertEqual(output.getvalue().count("已返回主菜单"), 2)

    def test_posting_timeout_retry_and_save_failure_keep_session(self):
        model = ScriptedModel(responses=[draft_message()])
        with patch("app.posting.agent.create_model", return_value=model), \
                patch("app.core.material_tools.load_material", return_value="夸克交付"), \
                patch("app.posting.cli.save_draft", side_effect=OSError), \
                patch("builtins.input", side_effect=["2", "", "", "", "", "/retry", "/save", "/exit", "0"]), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            original = PostingAgent._invoke
            attempts = []
            def invoke(agent, messages):
                attempts.append(messages)
                if len(attempts) == 1:
                    raise APITimeoutError(request=httpx.Request("POST", "https://example.com"))
                return original(agent, messages)
            with patch.object(PostingAgent, "_invoke", new=invoke):
                main.main()
        self.assertEqual(len(attempts), 2)
        self.assertIn("请求超时", output.getvalue())
        self.assertIn("保存失败", output.getvalue())
        self.assertIn("标题：", output.getvalue())

    def test_posting_question_blocks_save_and_can_be_resolved(self):
        model = ScriptedModel(responses=[draft_message("", "", ["请确认 DLC"]), draft_message()])
        with patch("app.posting.agent.create_model", return_value=model), \
                patch("app.core.material_tools.load_material", return_value="夸克交付"), \
                patch("app.posting.cli.save_draft") as saver, \
                patch("builtins.input", side_effect=["2", "", "", "", "突出DLC", "/save", "不写DLC了", "/exit", "0"]), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            main.main()
        saver.assert_not_called()
        self.assertIn("需要先确认", output.getvalue())
        self.assertIn("标题：", output.getvalue())

    def test_reenter_chat_creates_new_session_and_clear_is_forwarded(self):
        first, second = MagicMock(), MagicMock()
        first.ask.return_value = "第一场回复"
        second.ask.return_value = "第二场回复"
        inputs = ["1", "多少钱", "/clear", "/exit", "1", "怎么发", "/exit", "0"]
        with patch("app.customer.cli.CustomerAgent", side_effect=[first, second]) as factory, \
                patch("builtins.input", side_effect=inputs), contextlib.redirect_stdout(io.StringIO()) as output:
            main.main()
        self.assertEqual(factory.call_count, 2)
        first.ask.assert_called_once_with("多少钱")
        first.clear.assert_called_once_with()
        second.ask.assert_called_once_with("怎么发")
        self.assertEqual(output.getvalue().count("已返回主菜单"), 2)
        self.assertIn("程序已退出，再见", output.getvalue())

    def test_invalid_input_does_not_start_agent(self):
        with patch("app.customer.cli.CustomerAgent") as factory, \
                patch("builtins.input", side_effect=["9", "0"]), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            main.main()
        factory.assert_not_called()
        self.assertIn("输入无效", output.getvalue())

    def test_configuration_error_returns_to_menu(self):
        with patch("app.customer.cli.CustomerAgent", side_effect=ValueError("invalid config")), \
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
