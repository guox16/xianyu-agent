"""发帖生成命令行：输入要求、连续修改、保存与返回菜单。"""

from langgraph.errors import GraphRecursionError
from openai import APIConnectionError, APIStatusError, APITimeoutError

from app.posting.drafts import save_draft
from app.posting.agent import PostingAgent
from app.posting.schemas import PostingDraft, PostingRequest
from app.core.observability import flush_langfuse


def read_request() -> PostingRequest:
    def read(label, default=""):
        value = input(label).strip()
        if value.lower() == "/exit":
            raise EOFError
        return value or default

    return PostingRequest(
        current_game=read("当前游戏 [苏丹的游戏]：", "苏丹的游戏"),
        tone=read("语气 [自然]：", "自然"),
        length=read("长度 [简洁]：", "简洁"),
        focus=read("重点 [夸克交付和安装指导，明确不提供远程服务]：",
                   "夸克交付和安装指导，明确不提供远程服务"),
    )


def show_draft(draft: PostingDraft):
    if draft.questions:
        print("\n需要先确认：\n" + "\n".join(f"- {question}" for question in draft.questions))
    else:
        print(f"\n标题：\n{draft.title}\n\n正文：\n{draft.body}")
    print("\n待补充信息：\n" + ("\n".join(f"- {item}" for item in draft.missing_information) or "无"))


def main():
    print("发帖生成：本地资料和写作要求将发送给 DeepSeek。")
    print("直接输入修改要求；/save 保存，/retry 重试，/new 新草稿，/exit 返回菜单。")
    print("退出前请保存；本阶段只生成草稿。输入要求时也可用 /exit 返回。")
    try:
        agent = PostingAgent()
    except ValueError:
        print("配置无效，请检查本地 .env 中的密钥、模型名称和 HTTPS 接口地址。")
        return
    request = None  # 当前要求
    instruction = None  # 当前指令
    command = "/new"
    while True:
        try:
            if command == "/exit":
                break
            if command == "/save":
                # 追问后拒绝默默保存旧稿，避免用户误以为修改已经完成。
                if request != agent.request or agent.current_draft is None or agent.last_response.questions:
                    print("当前没有可保存的新草稿，请先完成生成或解决追问。")
                else:
                    path = save_draft(agent.request, agent.current_draft, agent.revisions)
                    print(f"草稿已保存：{path}")
            elif command == "/new":
                request = read_request()
                instruction = None
                print("正在查询资料并生成……")
                show_draft(agent.generate(request))
            elif command == "/retry" or (command and not command.startswith("/")):
                if command != "/retry":
                    instruction = command
                print("正在生成……")
                if instruction is None:
                    if request is None:
                        raise ValueError("请先使用 /new 输入要求。")
                    show_draft(agent.generate(request))
                else:
                    if request != agent.request:
                        raise ValueError("新草稿尚未生成成功，请使用 /new 重新输入要求。")
                    show_draft(agent.revise(instruction))
            elif command:
                print("未知命令，请使用 /save、/retry、/new 或 /exit。")
            else:
                print("修改要求不能为空。")
        except (EOFError, KeyboardInterrupt):
            break
        except APITimeoutError:
            print("请求超时，本轮未保存。输入 /retry 重试。")
        except APIConnectionError:
            print("连接失败，本轮未保存，请检查网络后 /retry。")
        except APIStatusError as error:
            hints = {401: "请检查密钥。", 402: "请检查账户余额。", 429: "请稍后再试。"}
            print(f"调用失败（HTTP {error.status_code}），本轮未保存。" + hints.get(error.status_code, "请检查配置后重试。"))
        except GraphRecursionError:
            print("生成达到循环上限，本轮未保存，请简化要求。")
        except ValueError as error:
            print(f"未完成：{error}")
        except OSError:
            print("保存失败，请检查目录权限和磁盘空间；当前草稿仍在内存中。")
        try:
            command = input("\n修改要求或命令：").strip()
            if command.startswith("/"):
                command = command.lower()
        except (EOFError, KeyboardInterrupt):
            break
    flush_langfuse()
    print("发帖会话已结束，已保存文件可在 drafts 目录查看。")


if __name__ == "__main__":
    main()
