"""独立客服 Agent 的本地 HTTP 入口，供 xianyu-Plus 调用。"""

from threading import Lock

from fastapi import FastAPI

from app.customer.plus_service import PlusCustomerAgent, ProductContext
from app.customer.schemas import CustomerReplyRequest, CustomerReplyResponse, Session
from app.core.observability import flush_langfuse


app = FastAPI(title="Xianyu Agent Customer API", docs_url=None, redoc_url=None)


@app.get("/health")
def health() -> dict[str, str]:
    """容器存活检查；不读取模型配置，也不调用模型。"""
    return {"status": "UP"}


_agents: dict[str, PlusCustomerAgent] = {}
_agents_lock = Lock()
_MAX_SESSIONS = 1_000


def _session_key(session: Session) -> str:
    return f"{session.accountId}:{session.sessionId}"


def _agent_for(session: Session) -> PlusCustomerAgent:
    key = _session_key(session)
    with _agents_lock:
        agent = _agents.get(key)
        if agent is None:
            # 有界缓存避免大量短会话无限占用内存；旧会话被淘汰后下轮重新开始即可。
            if len(_agents) >= _MAX_SESSIONS:
                _agents.pop(next(iter(_agents)))
            agent = PlusCustomerAgent(key)
            _agents[key] = agent
        return agent


@app.post("/customer/reply", response_model=CustomerReplyResponse)
def customer_reply(request: CustomerReplyRequest) -> CustomerReplyResponse:
    """返回候选文本；不执行任何闲鱼操作，也不决定 Plus 是否实际发送。"""
    buyer_message = "\n".join(message.content.strip() for message in request.messages)
    product = ProductContext(
        xy_goods_id=request.product.xyGoodsId,
        title=request.product.title,
        list_price=request.product.listPrice,
        detail_info=request.product.detailInfo,
        fixed_material=request.product.fixedMaterial,
        ai_prompt=request.product.aiPrompt,
    )
    try:
        reply = _agent_for(request.session).ask(product, buyer_message)
        return CustomerReplyResponse(status="answered", reply=reply)
    except Exception:
        # 不把模型、网络或配置细节传给 Plus；Plus 会保留回复记录并转人工处理。
        return CustomerReplyResponse(status="needs_human")
    finally:
        flush_langfuse()
