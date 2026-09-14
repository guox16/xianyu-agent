"""分层查询参考资料；不使用模型猜测售价、安装包版本或售后承诺。"""

import json
import re
from html import unescape
from urllib.parse import urlencode
from urllib.request import urlopen

from app.knowledge.workflow import ResearchResult


def get_json(endpoint, **params):
    with urlopen("https://store.steampowered.com/api/" + endpoint + "?" + urlencode(params), timeout=20) as response:
        return json.load(response)


def plain(value):
    text = re.sub(r"<br\s*/?>|</(?:p|li)>", "\n", value or "", flags=re.I)
    return unescape(re.sub(r"<[^>]+>", "", text)).strip()


def normalize(name):
    return re.sub(r"\s+", "", name).casefold()


def research_steam(game_name):
    """只接受唯一的完整名称匹配；译名和版本名不一致时留给人工确认。"""
    result = get_json("storesearch/", term=game_name, l="schinese", cc="CN")
    if not isinstance(result.get("items"), list):
        raise ValueError("Steam 搜索响应格式无效")
    items = result["items"]
    matches = {str(item["id"]): item for item in items if normalize(item["name"]) == normalize(game_name)}
    if not matches:
        return ResearchResult(status="名称待确认" if items else "补充失败",
                              reason="Steam 未找到完整名称匹配，可能存在译名或版本差异" if items else "Steam 未搜到该游戏")
    if len(matches) != 1:
        return ResearchResult(status="名称待确认", reason="Steam 存在多个同名条目")
    app_id = next(iter(matches))
    detail = get_json("appdetails", appids=app_id, l="schinese", cc="CN").get(app_id, {})
    if not detail.get("success"):
        return ResearchResult(reason="Steam 详情不可访问")
    data = detail["data"]
    if data.get("type") != "game" or normalize(data.get("name", "")) != normalize(game_name):
        return ResearchResult(status="名称待确认", reason="详情名称或商品类型不匹配")
    description = plain(data.get("short_description"))
    if not description:
        return ResearchResult(reason="Steam 缺少可用游戏介绍")
    lines = [f"# {game_name}", "", "## 官方商店参考资料", "", description]
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
    from app.knowledge.web_sources import research_official, research_wikipedia, research_baidu

    reasons, ambiguous = [], False
    for label, provider in (("Steam", research_steam), ("官网/其他商店", research_official),
                            ("维基百科", research_wikipedia), ("百度", research_baidu)):
        try:
            result = provider(game_name)
        except Exception as error:
            reasons.append(f"{label}：查询异常（{type(error).__name__}）")
            continue
        if result.content.strip() and result.sources:
            return result
        ambiguous = ambiguous or result.status == "名称待确认"
        reasons.append(f"{label}：{result.reason}")
    return ResearchResult(status="名称待确认" if ambiguous else "补充失败", reason="；".join(reasons))
