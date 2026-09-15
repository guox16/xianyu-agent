"""MyMemory 仅翻译检索名称，不提供知识库正文或已确认别名。"""

import json
import re
from html import unescape
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def translate_name(name):
    if len(name.encode("utf-8")) > 500:
        raise ValueError("名称超过 MyMemory 单次 500 字节限制")
    if not re.search(r"[\u3400-\u9fff]", name):
        raise ValueError("名称已无中文，无需中译英")
    url = "https://api.mymemory.translated.net/get?" + urlencode({"q": name, "langpair": "zh-CN|en"})
    request = Request(url, headers={"User-Agent": "XianyuKnowledge/1.0"})
    with urlopen(request, timeout=15) as response:
        data = json.load(response)
    if data.get("quotaFinished"):
        raise ValueError("MyMemory 免费额度已用完")
    if str(data.get("responseStatus")) != "200":
        raise ValueError("MyMemory 未返回成功翻译")
    value = data.get("responseData", {}).get("translatedText")
    if not isinstance(value, str):
        raise ValueError("MyMemory 翻译结果格式无效")
    translated = unescape(value).strip()
    if not translated or len(translated) > 500 or re.search(r"[\u3400-\u9fff]", translated):
        raise ValueError("MyMemory 未返回可用英文名")
    if re.findall(r"\d+", name) != re.findall(r"\d+", translated):
        raise ValueError("翻译改变了作品编号，不能用于自动匹配")
    if re.search(r"[:：]", name) and not re.search(r"[:：]", translated):
        raise ValueError("翻译未保留副标题分隔，不能确认完整作品名称")
    return translated
