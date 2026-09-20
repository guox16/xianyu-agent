"""供 Plus 调用的商品上下文客服 Agent。"""

from dataclasses import dataclass

from app.customer.agent import CustomerAgent


@dataclass(frozen=True)
class ProductContext:
    """Plus 已校验后传入的当前商品信息。"""

    xy_goods_id: str
    title: str | None
    list_price: str | None
    detail_info: str | None
    fixed_material: str | None
    ai_prompt: str | None

    def render(self) -> str:
        fields = (
            ("商品 ID", self.xy_goods_id),
            ("商品标题", self.title),
            ("标价", self.list_price),
            ("商品详情", self.detail_info),
            ("商品固定资料", self.fixed_material),
            ("商品回复规则", self.ai_prompt),
        )
        return "\n".join(f"{name}：{value.strip()}" for name, value in fields if value and value.strip())


class PlusCustomerAgent:
    """复用正式客服工作流；最终发送与风控仍属于 Plus。"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._customers: dict[str, CustomerAgent] = {}

    def ask(self, product: ProductContext, buyer_message: str) -> str:
        if not product.xy_goods_id.strip() or not buyer_message.strip():
            raise ValueError("商品和买家消息不能为空。")
        product_text = product.render()
        if not product_text:
            raise ValueError("当前商品资料为空。")
        customer = self._customers.get(product.xy_goods_id)
        if customer is None:
            # 同一买家可能从不同商品入口发消息，按商品隔离历史和工具结果。
            customer = CustomerAgent(
                product.title or product.xy_goods_id,
                session_id=f"{self.session_id}:{product.xy_goods_id}",
                trusted_product_context=product_text,
            )
            self._customers[product.xy_goods_id] = customer
        return customer.ask(buyer_message)
