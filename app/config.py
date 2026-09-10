"""读取、检查模型配置。本文件不会向 DeepSeek 发送请求。"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


# config.py 位于 app 包内，项目根目录在它的上一层。
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    """把配置放在一个对象里，后续调用模型时可以统一读取。"""

    # repr=False 避免打印 Settings 对象时意外显示密钥。
    api_key: str = field(repr=False)
    model: str
    base_url: str


def load_settings() -> Settings:
    """读取项目根目录的 .env；已有的系统环境变量优先。"""
    # 使用当前文件的位置定位配置，不受终端工作目录影响。
    env_path = PROJECT_ROOT / ".env"
    load_dotenv(env_path, override=False, encoding="utf-8")

    # getenv 从环境变量中取值；strip 去掉误输入的首尾空格。
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    model = os.getenv("DEEPSEEK_MODEL", "").strip()
    base_url = os.getenv("DEEPSEEK_BASE_URL", "").strip().rstrip("/")

    if not api_key or api_key == "your_deepseek_api_key_here":
        raise ValueError("请在 .env 中填写 DEEPSEEK_API_KEY。")
    if not model:
        raise ValueError("请在 .env 中填写 DEEPSEEK_MODEL。")
    url = urlparse(base_url)
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError("DEEPSEEK_BASE_URL 必须是有效的 HTTPS 地址，不能包含账号密码。")

    return Settings(api_key=api_key, model=model, base_url=base_url)


if __name__ == "__main__":
    # 直接运行 config.py 只检查本地配置；不会验证密钥是否有效或账户余额。
    try:
        settings = load_settings()
    except ValueError as error:
        raise SystemExit(f"配置检查失败：{error}") from None

    print("配置读取成功。")
    print(f"模型：{settings.model}")
    print("API Key：已配置（不显示内容）")
    print("接口地址：已通过本地格式检查")
    print("本次未调用模型，尚未验证 API 连通性和密钥有效性。")
