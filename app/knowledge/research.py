"""分层查询参考资料；不使用模型猜测售价、安装包版本或售后承诺。"""

import json
import re
from html import unescape
from urllib.parse import urlencode
from urllib.request import urlopen

from app.knowledge.workflow import ResearchResult
from app.knowledge.game_names import search_name, identity_key, query_names, match_score
from app.knowledge.translation import translate_name


def get_json(endpoint, **params):
    with urlopen("https://store.steampowered.com/api/" + endpoint + "?" + urlencode(params), timeout=20) as response:
        return json.load(response)


def plain(value):
    text = re.sub(r"<br\s*/?>|</(?:p|li)>", "\n", value or "", flags=re.I)
    return unescape(re.sub(r"<[^>]+>", "", text)).strip()


def normalize(name):
    return identity_key(name)


def research_steam(game_name):
    """忽略明确版本后缀；仍要求作品名称唯一匹配。"""
    items = []
    matches = {}
    for term in query_names(game_name):
        result = get_json("storesearch/", term=term, l="schinese", cc="CN")
        if not isinstance(result.get("items"), list):
            raise ValueError("Steam 搜索响应格式无效")
        items.extend(result["items"])
        scored = [(match_score(game_name, item["name"]), item) for item in items]
        best = max((score for score, _ in scored), default=0)
        matches = {str(item["id"]): item for score, item in scored if score == best and score > 0}
        if matches:
            break
    if not matches:
        return ResearchResult(status="名称待确认" if items else "补充失败",
                              reason="Steam 没有匹配到对应作品，可能存在译名差异" if items else "Steam 未搜到该游戏")
    if len(matches) != 1:
        return ResearchResult(status="名称待确认", reason="Steam 存在多个同名条目")
    app_id = next(iter(matches))
    detail = get_json("appdetails", appids=app_id, l="schinese", cc="CN").get(app_id, {})
    if not detail.get("success"):
        return ResearchResult(reason="Steam 详情不可访问")
    data = detail["data"]
    if data.get("type") != "game" or not match_score(game_name, data.get("name", "")):
        return ResearchResult(status="名称待确认", reason="详情名称或商品类型不匹配")
    description = plain(data.get("short_description"))
    if not description:
        return ResearchResult(reason="Steam 缺少可用游戏介绍")
    lines = [f"# {game_name}", "", f"来源作品名称：{data['name']}", "", "## 官方商店参考资料", "", description]
    for label, key in [("开发商", "developers"), ("发行商", "publishers")]:
        if data.get(key):
            lines.extend(["", f"{label}：{'、'.join(data[key])}"])
    requirements = data.get("pc_requirements")
    if isinstance(requirements, dict):
        for label, key in [("最低配置", "minimum"), ("推荐配置", "recommended")]:
            if requirements.get(key):
                lines.extend(["", f"## {label}（Steam 官方参考）", "", plain(requirements[key])])
    lines.extend(["", "## 卖家信息待确认", "",
                  "本店安装包版本、包含的 DLC、售价、交付方式、语言、联机支持、兼容性和售后政策尚未确认。",
                  "以上为 Steam 商店参考资料，不代表仓库安装包具备相同内容或功能。"])
    return ResearchResult(content="\n".join(lines), sources=[f"https://store.steampowered.com/app/{app_id}/"])


def research_game(game_name):
    """按层降级；单个来源不可用不会阻止其他来源，不自动重试。"""
    from app.knowledge.web_sources import research_wikipedia

    reasons, ambiguous = [], False
    query_name = search_name(game_name)
    for label, provider in (("Steam", research_steam), ("维基百科", research_wikipedia)):
        try:
            result = provider(query_name)
        except Exception as error:
            reasons.append(f"{label}：查询异常（{type(error).__name__}）")
            continue
        if result.content.strip() and result.sources:
            if query_name != game_name:
                result.content = (f"# 仓库游戏：{game_name}\n\n"
                                  f"检索使用基础名称：{query_name}。版本后缀仅用于名称匹配，"
                                  "不代表已核实该版本功能、内容或配置。\n\n" + result.content)
            return result
        ambiguous = ambiguous or result.status == "名称待确认"
        reasons.append(f"{label}：{result.reason}")
    # 前两个资料来源都不可用时，翻译仅作为新的检索线索。
    try:
        translated = translate_name(query_name)
    except Exception as error:
        detail = str(error) if isinstance(error, ValueError) else type(error).__name__
        reasons.append(f"MyMemory：{detail}")
    else:
        try:
            result = research_steam(translated)
        except Exception as error:
            reasons.append(f"Steam 英文查询：{type(error).__name__}")
        else:
            if result.content.strip() and result.sources:
                result.content = (f"# 仓库游戏：{game_name}\n\n"
                                  f"MyMemory 候选检索名：{translated}。以下资料来自匹配的 Steam 游戏页面；"
                                  "机器翻译不作为已确认别名，仓库安装包版本仍需核实。\n\n" + result.content)
                result.aliases = []
                return result
            ambiguous = ambiguous or result.status == "名称待确认"
            reasons.append(f"Steam 英文查询：{result.reason}")
    return ResearchResult(status="名称待确认" if ambiguous else "补充失败", reason="；".join(reasons))
