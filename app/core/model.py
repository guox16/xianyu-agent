"""统一创建业务和学习示例使用的模型。"""

from langchain_deepseek import ChatDeepSeek

from app.core.config import load_settings


def create_model() -> ChatDeepSeek:
    """统一创建模型，供普通问答和工具 Agent 复用。"""
    # 复用配置读取功能，不在代码里写密钥。
    settings = load_settings()

    # 创建 LangChain 模型对象；创建对象本身不会发送对话请求。
    return ChatDeepSeek(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout=30,       # 网络请求超时，避免一直等待。
        max_retries=0,    # 学习阶段失败就提示，由用户决定是否再次调用。
        max_tokens=512,   # 限制单次输出长度，适合简短问答。
        # DeepSeek 扩展参数：这一步使用非思考模式学习基本调用。
        extra_body={"thinking": {"type": "disabled"}},
    )
