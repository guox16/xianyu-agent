"""把本地商品资料查询注册成 LangChain 工具。"""

from langchain.tools import tool

from app.core.knowledge_catalog import lookup_game_material

#把函数包装为langchain工具
@tool
def query_game_material(game_name: str) -> dict:
    """按游戏名称精确查询本店资料，获取价格、交付、配置和售后信息。

    game_name 是游戏中文名或英文名，不是文件路径。
    返回 status、game_name，以及成功时的 content 或失败时的 message。
    未找到或读取失败时，不能据此编造商品信息。
    """
    # @tool 根据函数名、注释和参数类型生成给模型看的工具说明。
    result = lookup_game_material(game_name)
    print(f"[资料工具] 查询：{game_name.strip()[:80]!r}，结果：{result['status']}")
    return result
