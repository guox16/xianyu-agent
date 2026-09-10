"""通过资料查询工具进行多轮客服对话。"""

from langgraph.errors import GraphRecursionError
from openai import APIConnectionError, APIStatusError, APITimeoutError

from customer_agent import CustomerAgent


def main():
    try:
        customer = CustomerAgent()
    except ValueError:
        print("配置无效，请检查本地 .env 中的密钥、模型名称和 HTTPS 接口地址。")
        return
    print("当前商品：苏丹的游戏。Agent 将按需查询本地资料并发送给 DeepSeek。")
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
    print("会话已结束。")


if __name__ == "__main__":
    main()
