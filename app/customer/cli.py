"""通过资料查询工具进行多轮客服对话。"""

from langgraph.errors import GraphRecursionError
from openai import APIConnectionError, APIStatusError, APITimeoutError

from app.customer.agent import CustomerAgent
from app.core.knowledge_catalog import available_game_count, resolve_available_game
from app.core.observability import flush_langfuse


def choose_current_game() -> str:
    count = available_game_count()
    if not count:
        raise ValueError("知识库没有可用的已确认商品资料，请先在菜单 3 维护知识库。")
    name = input(f"当前游戏（知识库已有 {count} 款，输入名称或已确认别名）：").strip()
    if name.lower() == "/exit":
        raise EOFError
    return resolve_available_game(name)


def main():
    try:
        current_game = choose_current_game()
        customer = CustomerAgent(current_game)
    except (EOFError, KeyboardInterrupt):
        return
    except ValueError:
        print("无法进入客服，请检查知识库、游戏名称和模型配置。")
        return
    print(f"当前商品：{current_game}。Agent 将按需查询知识库资料并发送给 DeepSeek。")
    print("/clear 清空会话，/exit 退出；历史只保存在本次运行中。")
    while True:
        try:
            question = input("\n你：").strip()
            if question.lower() == "/exit":
                break
            if question.lower() == "/clear":
                customer.clear()
                print("已清空问答和工具记录。")
                continue
            if not question:
                print("问题不能为空。")
                continue
            print("Agent 正在处理……")
            print(f"\n客服：\n{customer.ask(question)}")
        except (EOFError, KeyboardInterrupt):
            break
        except APITimeoutError:
            print("请求超时，本轮未保存，可以重试。")
        except APIConnectionError:
            print("连接失败，本轮未保存，请检查网络和接口地址。")
        except APIStatusError as error:
            # 不展示服务器原始报错，避免请求或凭证出现在终端。
            hints = {401: "请检查密钥。", 402: "请检查账户余额。", 429: "请稍后再试。"}
            print(f"调用失败（HTTP {error.status_code}），本轮未保存。" + hints.get(error.status_code, "请检查模型配置或稍后重试。"))
        except GraphRecursionError:
            print("本轮处理达到循环上限，未保存。请简化问题后重试。")
        except ValueError:
            print("配置或模型返回格式异常，本轮未保存，请检查配置后重试。")
    flush_langfuse()
    print("会话已结束。")


if __name__ == "__main__":
    main()
