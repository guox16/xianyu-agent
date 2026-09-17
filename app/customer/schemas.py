"""客服 HTTP 接口的传输模型，供现有和后续接口复用。"""

from pydantic import BaseModel, Field


class Session(BaseModel):
    """Plus 中的买家会话范围。"""

    accountId: int
    sessionId: str = Field(min_length=1, max_length=256)
    buyerUserId: str | None = Field(default=None, max_length=256)
    buyerUserName: str | None = Field(default=None, max_length=256)


class Product(BaseModel):
    """Plus 传入的当前商品资料。"""

    xyGoodsId: str = Field(min_length=1, max_length=256)
    title: str | None = Field(default=None, max_length=500)
    listPrice: str | None = Field(default=None, max_length=100)
    detailInfo: str | None = Field(default=None, max_length=20_000)
    fixedMaterial: str | None = Field(default=None, max_length=20_000)
    aiPrompt: str | None = Field(default=None, max_length=8_000)


class Message(BaseModel):
    """一条已由 Plus 接收并聚合的买家消息。"""

    messageId: str | None = Field(default=None, max_length=256)
    content: str = Field(min_length=1, max_length=8_000)
    sentAt: int | None = None


class CustomerReplyRequest(BaseModel):
    """生成客服候选回复的请求。"""

    session: Session
    product: Product
    messages: list[Message] = Field(min_length=1, max_length=20)


class CustomerReplyResponse(BaseModel):
    """Agent 的候选回复结果，最终是否发送由 Plus 决定。"""

    status: str
    reply: str | None = None
