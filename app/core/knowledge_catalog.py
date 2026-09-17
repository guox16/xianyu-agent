"""为业务 Agent 提供已确认知识库资料的只读查询。"""

from app.core.config import PROJECT_ROOT
from app.knowledge import KnowledgeBase


def lookup_game_material(game_name: str) -> dict:
    """按名称或确认别名查询一款可供业务使用的资料。"""
    name = game_name.strip()
    if not name:
        return {"status": "not_found", "game_name": name, "message": "游戏名称不能为空。"}
    try:
        result = KnowledgeBase(PROJECT_ROOT / "materials").lookup(name)
    except (OSError, ValueError):
        return {
            "status": "unavailable", "game_name": name,
            "message": "知识库暂时无法读取，请联系卖家核实。",
        }
    if result["registered"] is False:
        return {
            "status": "not_found", "game_name": name,
            "message": "知识库没有该游戏的已确认商品资料，请联系卖家确认。",
        }
    if result["registered"] is None:
        return {
            "status": "ambiguous", "game_name": name,
            "message": "知识库中的游戏名称或别名存在冲突，请联系卖家确认。",
        }
    if not result.get("content"):
        return {
            "status": "unavailable", "game_name": result["game_name"],
            "message": "该游戏已登记，但还没有可用于回答的确认资料，请联系卖家核实。",
        }
    return {
        "status": "ok", "game_name": result["game_name"], "content": result["content"],
    }


def available_game_count() -> int:
    """返回当前可用于客服和发帖的已确认游戏数量。"""
    try:
        return sum(
            entry.get("status") == "已补充" and bool(entry.get("content"))
            for entry in KnowledgeBase(PROJECT_ROOT / "materials").entries()
        )
    except (OSError, ValueError):
        return 0


def resolve_available_game(game_name: str) -> str:
    """将用户输入的名称或别名解析为知识库中的规范游戏名。"""
    result = lookup_game_material(game_name)
    if result["status"] != "ok":
        raise ValueError(result["message"])
    return result["game_name"]
