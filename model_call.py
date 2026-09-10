"""第二步：完成一次模型调用。直接运行本文件即可输入问题。"""

from langchain_deepseek import ChatDeepSeek
from openai import APIConnectionError, APIStatusError, APITimeoutError

from config import load_settings


def ask_model(question: str) -> str:
    """把一个问题交给 DeepSeek，返回回复文字；不保存聊天历史。"""
    question = question.strip()
    if not question:
        raise ValueError("问题不能为空，请输入一句话。")

    # 1. 复用上一步的配置读取功能，不在代码里写密钥。
    settings = load_settings()

    # 2. 创建 LangChain 模型对象；创建对象本身不会发送对话请求。
    model = ChatDeepSeek(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout=30,       # 网络请求超时，避免一直等待。
        max_retries=0,    # 学习阶段失败就提示，由用户决定是否再次调用。
        max_tokens=512,   # 限制单次输出长度，适合简短问答。
        # DeepSeek 扩展参数：这一步使用非思考模式学习基本调用。
        extra_body={"thinking": {"type": "disabled"}},
    )

    # 3. system 定义回答规则；human 表示用户的问题。
    messages = [
        ("system", "你是一个友好的中文助手。请简洁回答，不确定时明确说明。"),
        ("human", question),
    ]

    # 4. invoke 才真正发出请求。返回值是 AIMessage，不只是一个字符串。
    response = model.invoke(messages)
    answer = response.text.strip()
    if not answer:
        raise ValueError("模型没有返回文字，请检查模型配置后再试。")
    if response.response_metadata.get("finish_reason") == "length":
        answer += "\n（回复达到本次长度上限，可能不完整。）"
    return answer


def main():
    """命令行入口：输入一次、回答一次，然后结束。"""
    try:
        question = input("请输入问题：")
        if not question.strip():
            raise ValueError("问题不能为空，请输入一句话。")
        print("正在调用 DeepSeek，请稍候……")
        answer = ask_model(question)
    except (EOFError, KeyboardInterrupt):
        raise SystemExit("\n已取消。") from None
    except APITimeoutError:
        raise SystemExit("请求超时，请稍后重试。") from None
    except APIConnectionError:
        raise SystemExit("连接失败，请检查网络和 .env 中的接口地址。") from None
    except APIStatusError as error:
        # 只展示状态码和解释，不输出原始请求、响应或密钥。
        hints = {
            401: "密钥无效，请检查本地 .env 配置。",
            402: "账户余额不足，请检查 DeepSeek 账户。",
            403: "请求被拒绝，请检查账户权限。",
            429: "请求过于频繁，请稍后重试。",
        }
        hint = hints.get(error.status_code, "请检查模型配置或稍后重试。")
        raise SystemExit(f"调用失败（HTTP {error.status_code}）：{hint}") from None
    except ValueError as error:
        raise SystemExit(str(error)) from None

    print(f"\n模型回复：\n{answer}")


if __name__ == "__main__":
    main()
