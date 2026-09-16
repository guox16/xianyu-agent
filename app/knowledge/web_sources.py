"""维基百科公开资料与跨语言名称查询。"""

import json
import re
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

from app.knowledge.workflow import ResearchResult
from app.knowledge.game_names import query_names

NETWORK_HOSTS = {"zh.wikipedia.org", "en.wikipedia.org"}


def host_in(url, hosts):
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    return (parsed.scheme == "https" and not parsed.username and not parsed.password
            and parsed.port in (None, 443)
            and any(host == allowed or host.endswith("." + allowed) for allowed in hosts))


class CheckedRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not host_in(newurl, NETWORK_HOSTS):
            raise ValueError("来源跳转到不支持的域名或安全验证页面")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url):
    if not host_in(url, NETWORK_HOSTS):
        raise ValueError("不支持的资料来源地址")
    request = Request(url, headers={"User-Agent": "XianyuKnowledge/1.0 (personal game catalog)"})
    with build_opener(CheckedRedirect()).open(request, timeout=15) as response:
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("来源页面超过读取上限")
        return raw.decode(response.headers.get_content_charset() or "utf-8"), response.url


def is_game(text):
    return bool(re.search(r"电子游戏|電子遊戲|电脑游戏|電腦遊戲|游戏|遊戲|video game|videogame|gameplay", text, re.I))


def reference(name, text, url, label):
    return ResearchResult(content=(f"# {name}\n\n## {label}\n\n{text}\n\n"
        "## 卖家信息待确认\n\n本店安装包版本、DLC、售价、交付、联机、配置适用性及售后尚未确认。"
        "以上为外部参考资料，不代表卖家安装包内容。"), sources=[url])


def research_wikipedia(name):
    failures = []
    for language in ("zh", "en"):
        # 标题查询使用维基自身重定向和简繁转换，不自行猜测别名。
        titles = [title + suffix for title in query_names(name)
                  for suffix in (("", " (电子游戏)", " (游戏)") if language == "zh" else ("", " (video game)"))]
        params = dict(action="query", format="json", formatversion=2, titles="|".join(titles),
                      redirects=1, converttitles=1, prop="extracts|pageprops|info|langlinks", lllang="en", lllimit=1,
                      exintro=1, explaintext=1, inprop="url", variant="zh-cn")
        try:
            raw, _ = fetch(f"https://{language}.wikipedia.org/w/api.php?" + urlencode(params))
            data = json.loads(raw)
            if "query" not in data:
                raise ValueError("维基百科响应无效")
            pages = data["query"].get("pages", [])
            matches = {}
            for page in pages:
                if page.get("missing"):
                    continue
                if "disambiguation" in page.get("pageprops", {}):
                    continue
                text = page.get("extract", "").strip()
                # 介绍开头须表明这是游戏，排除同名电影、小说等页面。
                if not is_game(text[:350]) or re.search(r"游戏系列|遊戲系列|video game (?:series|franchise)", text[:350], re.I):
                    continue
                url = page.get("fullurl", "")
                if text and host_in(url, {f"{language}.wikipedia.org"}):
                    aliases = [link["title"] for link in page.get("langlinks", []) if link.get("lang") == "en" and link.get("title")]
                    if language == "en" and page.get("title"):
                        aliases.append(page["title"])
                    matches[page["pageid"]] = (text, url, aliases)
            if len(matches) == 1:
                text, url, aliases = next(iter(matches.values()))
                result = reference(name, text.split("\n")[0][:1200], url, "维基百科参考资料")
                result.aliases = aliases
                return result
            if len(matches) > 1:
                return ResearchResult(status="补充失败", reason="维基百科有多个同名游戏条目")
        except (OSError, ValueError) as error:
            failures.append(f"{language}：{type(error).__name__}")
    return ResearchResult(status="补充失败",
                          reason="维基百科没有唯一可用的游戏条目" + ("；" + "、".join(failures) if failures else ""))
