"""Langfuse 可观测性接入；未配置时不改变业务调用。"""

import os
from collections.abc import Sequence
from typing import Any

from app.core.config import PROJECT_ROOT


def _is_configured() -> bool:
    """仅在公钥和私钥都已配置时启用，避免意外上报。"""
    # load_settings() 会读取 .env；这里也支持知识库等独立入口。
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env", override=False, encoding="utf-8")
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    return bool(public_key and secret_key)


def langfuse_config(
    run_name: str,
    *,
    session_id: str | None = None,
    tags: Sequence[str] = (),
) -> dict[str, Any]:
    """返回 LangChain 调用配置；未配置 Langfuse 时返回空配置。"""
    if not _is_configured():
        return {}

    # 延迟导入使未启用可观测性时不依赖 SDK 的运行时初始化。
    from langfuse.langchain import CallbackHandler

    metadata: dict[str, Any] = {"langfuse_tags": list(tags)}
    if session_id:
        metadata["langfuse_session_id"] = session_id
    return {
        "callbacks": [CallbackHandler()],
        "run_name": run_name,
        "metadata": metadata,
    }


def flush_langfuse() -> None:
    """在短生命周期 CLI 退出前尽力发送已积累的追踪事件。"""
    if not _is_configured():
        return
    from langfuse import get_client

    get_client().flush()
