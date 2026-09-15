"""读取夸克公开分享目录，不转存、不下载；仅支持网页允许匿名访问的分享。"""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen

from app.core.config import PROJECT_ROOT
from app.knowledge.workflow import KnowledgeBase

API = "https://drive-m.quark.cn/1/clouddrive/share/sharepage/"


class QuarkError(ValueError):
    """分享不可访问或目录未能完整读取。"""


def parse_share(url):
    parts = urlsplit(url.strip())
    match = re.fullmatch(r"/s/([a-zA-Z0-9]+)/*", parts.path)
    if parts.scheme != "https" or parts.netloc != "pan.quark.cn" or not match:
        raise QuarkError("请输入 https://pan.quark.cn/s/分享编号 格式的链接。")
    return match[1], parse_qs(parts.query).get("pwd", [""])[0]


class QuarkClient:
    def __init__(self, url, passcode=""):
        self.share_id, embedded_code = parse_share(url)
        self.passcode = passcode or embedded_code
        self.token = None

    def _request(self, endpoint, params=None, body=None):
        query = urlencode({"pr": "ucpro", "fr": "pc", **(params or {})})
        request = Request(
            API + endpoint + "?" + query,
            data=json.dumps(body).encode("utf-8") if body is not None else None,
            headers={"Referer": "https://pan.quark.cn/", "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=25) as response:
                result = json.load(response)
        except HTTPError as exc:
            raise QuarkError(f"夸克返回 HTTP {exc.code}，请检查分享是否需要登录或验证。") from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise QuarkError("夸克请求失败或响应无效，请稍后重试。") from None
        if not isinstance(result, dict) or result.get("code") != 0:
            code = result.get("code", "未知") if isinstance(result, dict) else "未知"
            raise QuarkError(f"夸克拒绝访问（代码 {code}），请检查分享有效期、提取码或登录要求。")
        return result

    def list_folder(self, folder_id="0"):
        if self.token is None:
            self.token = self._request("token", body={
                "pwd_id": self.share_id, "passcode": self.passcode,
            }).get("data", {}).get("stoken")
            if not self.token:
                raise QuarkError("未取得分享访问凭证。")
        files, seen = [], set()
        for page in range(1, 1001):
            result = self._request("detail", params={
                "pwd_id": self.share_id, "stoken": self.token, "pdir_fid": folder_id,
                "_page": page, "_size": 100, "_fetch_total": 1,
            })
            batch = result.get("data", {}).get("list")
            total = result.get("metadata", {}).get("_total")
            if not isinstance(batch, list) or not isinstance(total, int) or total < 0:
                raise QuarkError("目录响应格式变化，停止导入，避免遗漏商品。")
            for item in batch:
                if not isinstance(item, dict) or not isinstance(item.get("file_name"), str) or not item.get("fid"):
                    raise QuarkError("目录条目格式无效。")
                if item["fid"] in seen:
                    raise QuarkError("目录分页重复，停止导入，请重试。")
                seen.add(item["fid"])
                files.append(item)
            if len(files) == total:
                return files
            if not batch or len(files) > total:
                raise QuarkError("目录数量发生变化或分页不完整，请重新读取。")
        raise QuarkError("目录超过分页上限，未导入。")


def is_category(name):
    return bool(re.fullmatch(r"[A-Z]{1,8}", name)) or name == "数字开头游戏" or name.startswith("游戏合集")


def candidate(item, path):
    raw = item["file_name"].strip()
    titles = re.findall(r"《([^《》]+)》", raw)
    certain = len(titles) == 1 and titles[0].strip() != ""
    return dict(
        game_name=titles[0].strip() if certain else raw,
        status="待补充" if certain else "补充失败",
        reason="" if certain else "目录名称无法唯一提取游戏名，需要人工确认",
        raw_name=raw, source_path="/".join(path + [raw]), fid=item["fid"],
    )


def scan(client):
    """仅进入已识别的合集/字母分类；停在游戏层，不遍历安装包内部。"""
    queue = [("0", [], 0)]
    visited, games, skipped = set(), [], []
    while queue:
        folder_id, path, depth = queue.pop(0)
        if folder_id in visited or depth > 8 or len(visited) >= 200:
            raise QuarkError("目录结构重复或超过扫描上限，未导入。")
        visited.add(folder_id)
        for item in client.list_folder(folder_id):
            name = item["file_name"].strip()
            if not name:
                raise QuarkError("目录名称为空，未导入。")
            if item.get("dir") and is_category(name):
                queue.append((item["fid"], path + [name], depth + 1))
            elif name == "游戏模拟器及其它软件" or re.search(r"\.(txt|pdf|url|jpg|png|md)$", name, re.I):
                skipped.append({"source_path": "/".join(path + [name]), "reason": "软件分类或说明文件"})
            elif item.get("dir") or re.search(r"\.(zip|rar|7z|exe|iso)(\.\d+)?$", name, re.I):
                games.append(candidate(item, path))
            else:
                skipped.append({"source_path": "/".join(path + [name]), "reason": "未识别的非目录文件"})
    return dict(share_url=f"https://pan.quark.cn/s/{client.share_id}",
                scanned_at=datetime.now(timezone.utc).isoformat(), games=games, skipped=skipped)


def import_catalog(kb, report):
    """完整扫描后一次性登记；保留原有资料状态，不把目录宣传当作知识。"""
    entries = kb.entries()
    names = {entry["game_name"].strip().casefold() for entry in entries}
    added = 0
    for game in report["games"]:
        key = game["game_name"].casefold()
        if key in names:
            continue
        entries.append(dict(game_name=game["game_name"], aliases=[], material_file=None,
                            status=game["status"], reason=game["reason"], last_attempt_at=None,
                            content=None, sources=[]))
        names.add(key)
        added += 1
    kb._write(kb.catalog_file, entries)
    return added


def main():
    parser = argparse.ArgumentParser(description="读取夸克游戏分享目录，保存扫描报告，可登记到商品目录。")
    parser.add_argument("url", help="夸克分享链接")
    parser.add_argument("--passcode", default="", help="分享提取码（如有）")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT / "materials")
    parser.add_argument("--import-catalog", action="store_true", help="把扫描结果登记到 knowledge.json")
    args = parser.parse_args()
    try:
        print("正在读取分享目录……", flush=True)
        report = scan(QuarkClient(args.url, args.passcode))
        kb = KnowledgeBase(args.root)
        report_path = args.root / "quark-scan.json"
        kb._write(report_path, report)
        unique = len({game["game_name"].casefold() for game in report["games"]})
        print(f"读取 {len(report['games'])} 个游戏候选项，去重后 {unique} 个，跳过 {len(report['skipped'])} 项。")
        print(f"原始目录与名称预览：{report_path}")
        if args.import_catalog:
            print(f"已新增登记 {import_catalog(kb, report)} 款；原有条目保持不变。")
    except (QuarkError, OSError, ValueError) as exc:
        parser.exit(1, f"读取或保存失败：{exc}\n")


if __name__ == "__main__":
    main()
