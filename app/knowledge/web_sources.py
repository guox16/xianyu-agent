"""补充来源：官网/发行商、维基百科、百度检索落地页。"""

import json
import re
from html.parser import HTMLParser
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

from app.knowledge.workflow import ResearchResult

# 仅把已知商店、开发商和发行商域名当作官方来源，不相信搜索标题中的“官网”。
OFFICIAL_HOSTS = {
    "store.epicgames.com", "gog.com", "ea.com", "ubisoft.com", "capcom.com",
    "nintendo.com", "playstation.com", "xbox.com", "rockstargames.com",
    "square-enix-games.com", "bandainamcoent.com", "valvesoftware.com",
    "bethesda.net", "blizzard.com", "cdprojektred.com",
}
REFERENCE_HOSTS = {"baike.baidu.com", "ign.com", "gamespot.com", "pcgamingwiki.com"}
NETWORK_HOSTS = OFFICIAL_HOSTS | REFERENCE_HOSTS | {"www.baidu.com", "zh.wikipedia.org", "en.wikipedia.org"}


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


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title, self.description, self.paragraphs, self.links = "", "", [], []
        self.in_title = False
        self.in_p = False
        self.paragraph = ""
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag == "title":
            self.in_title = True
        if tag == "p":
            self.in_p, self.paragraph = True, ""
        if tag == "meta" and (attrs.get("name", "").lower() == "description" or attrs.get("property") == "og:description"):
            self.description = attrs.get("content", "")
        for key in ("mu", "data-landurl"):
            if attrs.get(key):
                self.links.append(attrs[key])
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if tag == "title":
            self.in_title = False
        if tag == "p":
            self.in_p = False
            if self.paragraph.strip():
                self.paragraphs.append(self.paragraph.strip())

    def handle_data(self, data):
        if not self.hidden:
            if self.in_title:
                self.title += data
            if self.in_p:
                self.paragraph += data


def name_key(text):
    return re.sub(r"[\W_]+", "", text).casefold()


def has_identity(name, text):
    # 只接受完整标题片段，避免把 Portal 2 当成 Portal。
    pieces = re.split(r"[|｜–—]|\s-\s", text)
    for piece in pieces:
        piece = re.sub(r"\s*\((?:video game|电子游戏|電子遊戲|游戏|遊戲)\)\s*$", "", piece, flags=re.I)
        piece = re.sub(r"(?:官方网站|官方網站|官网|Official (?:Site|Website))\s*$", "", piece, flags=re.I)
        if name_key(piece) == name_key(name):
            return True
    return False


def is_game(text):
    return bool(re.search(r"电子游戏|電子遊戲|电脑游戏|電腦遊戲|游戏|遊戲|video game|videogame|gameplay", text, re.I))


def reference(name, text, url, label):
    return ResearchResult(content=(f"# {name}\n\n## {label}\n\n{text}\n\n"
        "## 卖家信息待确认\n\n本店安装包版本、DLC、售价、交付、联机、配置适用性及售后尚未确认。"
        "以上为外部参考资料，不代表卖家安装包内容。"), sources=[url])


def baidu_links(name, official=False):
    query = name + (" 游戏 官网 开发商" if official else " 游戏 介绍")
    html, _ = fetch("https://www.baidu.com/s?" + urlencode({"wd": query}))
    page = Page()
    page.feed(html)
    if "安全验证" in page.title or "验证码" in page.title:
        raise ValueError("百度要求安全验证，暂不可访问")
    # 不使用搜索摘要作为正文，只拿到链接后读取实际来源。
    return list(dict.fromkeys(url for url in page.links if url.startswith("https://")))


def search_pages(name, official=False):
    hosts = OFFICIAL_HOSTS if official else REFERENCE_HOSTS
    links = baidu_links(name, official)
    candidates = [url for url in links if host_in(url, hosts) or url.startswith("https://www.baidu.com/link?")][:5]
    reasons = []
    matches = []
    for url in candidates:
        try:
            html, final_url = fetch(url)
            if not host_in(final_url, hosts):
                continue
            page = Page()
            page.feed(html)
            if not has_identity(name, page.title):
                continue
            texts = [page.description, *page.paragraphs]
            text = next((text.strip() for text in texts if len(text.strip()) >= 40 and is_game(text)), "")
            if text:
                matches.append((text[:1200], final_url))
        except (OSError, ValueError) as error:
            reasons.append(type(error).__name__)
    if matches:
        # 单页的标题不能证明同名作品身份；多个同类结果则交由人工核实。
        if len({url for _, url in matches}) > 1:
            return ResearchResult(status="名称待确认", reason="多个页面匹配同名游戏，需要核对开发商或平台")
        text, url = matches[0]
        return reference(name, text, url, "官网/商店参考资料" if official else "百度检索来源参考资料")
    return ResearchResult(reason="未找到可读取且名称匹配的来源页面" + ("；部分页面读取失败" if reasons else ""))


def research_official(name):
    return search_pages(name, official=True)


def research_baidu(name):
    return search_pages(name)


def research_wikipedia(name):
    failures, ambiguous = [], False
    for language in ("zh", "en"):
        # 标题查询使用维基自身重定向和简繁转换，不自行猜测别名。
        titles = [name, name + " (电子游戏)", name + " (游戏)"] if language == "zh" else [name, name + " (video game)"]
        params = dict(action="query", format="json", formatversion=2, titles="|".join(titles),
                      redirects=1, converttitles=1, prop="extracts|pageprops|info",
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
                    ambiguous = True
                    continue
                text = page.get("extract", "").strip()
                # 介绍开头须表明这是游戏，排除同名电影、小说等页面。
                if not is_game(text[:350]) or re.search(r"游戏系列|遊戲系列|video game (?:series|franchise)", text[:350], re.I):
                    ambiguous = True
                    continue
                url = page.get("fullurl", "")
                if text and host_in(url, {f"{language}.wikipedia.org"}):
                    matches[page["pageid"]] = (text, url)
            if len(matches) == 1:
                text, url = next(iter(matches.values()))
                return reference(name, text.split("\n")[0][:1200], url, "维基百科参考资料")
            if len(matches) > 1:
                return ResearchResult(status="名称待确认", reason="维基百科有多个同名游戏条目")
        except (OSError, ValueError) as error:
            failures.append(f"{language}：{type(error).__name__}")
    return ResearchResult(status="名称待确认" if ambiguous else "补充失败",
                          reason="维基百科没有唯一可用的游戏条目" + ("；" + "、".join(failures) if failures else ""))
