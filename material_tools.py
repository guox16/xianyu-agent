"""把本地商品资料查询注册成 LangChain 工具。"""

from pathlib import Path

from langchain.tools import tool

from model_call import load_material


MATERIAL_DIR = Path(__file__).resolve().parent / "materials"
# 只读取已登记文件，不把模型给出的名称直接拼成磁盘路径。
GAME_FILES = {"苏丹的游戏": "sultans-game.md", "sultan's game": "sultans-game.md"}

#把函数包装为langchain工具
@tool
def query_game_material(game_name: str) -> dict:
    """按游戏名称精确查询本店资料，获取价格、交付、配置和售后信息。

    game_name 是游戏中文名或英文名，不是文件路径。
    返回 status、game_name，以及成功时的 content 或失败时的 message。
    未找到或读取失败时，不能据此编造商品信息。
    """
    # @tool 根据函数名、注释和参数类型生成给模型看的工具说明。
    name = game_name.strip()
    filename = GAME_FILES.get(name.casefold())
    print(f"[资料工具] 查询：{name[:80]!r}")
    if filename is None:
        print("[资料工具] 未找到已登记的游戏")
        return {"status": "not_found", "game_name": name, "message": "没有该游戏的商品资料，请联系卖家确认。"}
    try:
        content = load_material(MATERIAL_DIR / filename)
    except ValueError:
        print("[资料工具] 资料文件不可用")
        return {"status": "unavailable", "game_name": name, "message": "本地资料缺失、为空或无法读取，请联系卖家核实。"}

    # 正文返回给 Agent，不打印到终端；实际调用工具时才读取文件。
    print(f"[资料工具] 已读取 {len(content)} 字符")
    return {"status": "ok", "game_name": name, "content": content}
