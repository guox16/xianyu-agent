"""检索名称与仓库名称分开：仅去掉明确的版本后缀，保留作品编号和副标题。"""

import re
import unicodedata


def search_name(name):
    name = unicodedata.normalize("NFKC", name).strip()
    # 不包含“重制版”、DLC 名称等可能代表独立作品的词。
    suffix = r"(?:次世代(?:版|版本)?|豪华版|终极版|完整版|年度版|典藏版|\bdeluxe edition|\bcomplete edition|\bgame of the year edition|\bnext[- ]gen(?: edition)?)"
    while True:
        shortened = re.sub(r"\s*[-:：—–]?\s*[（(【\[]?\s*" + suffix + r"\s*[）)】\]]?\s*$", "", name, flags=re.I).strip()
        if not shortened or shortened == name:
            return name
        name = shortened


def identity_key(name):
    return re.sub(r"[\W_]+", "", search_name(name)).casefold()


def query_names(name):
    """完整名称优先，再用带作品编号的基础名称扩大检索。"""
    full = search_name(name)
    base = re.split(r"[:：]|\s[-–—]\s", full, maxsplit=1)[0].strip()
    if base != full and re.search(r"\d", base):
        return [full, base]
    return [full]


def match_score(requested, candidate):
    """完整匹配优先；其次接受编号相同且一方省略副标题的简称。"""
    left, right = identity_key(requested), identity_key(candidate)
    if left == right:
        return 100
    if re.search(r"\b(?:dlc|soundtrack|season pass|expansion)\b|原声|原聲|季票|资料片|資料片|重制版", search_name(candidate), re.I):
        return 0
    if re.findall(r"\d+", left) != re.findall(r"\d+", right):
        return 0
    left_base, right_base = query_names(requested)[-1], query_names(candidate)[-1]
    base = identity_key(left_base)
    if re.search(r"\d", base) and base == identity_key(right_base) and (left == base or right == base):
        return 80
    return 0
