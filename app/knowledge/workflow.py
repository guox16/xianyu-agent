"""研究函数由调用方提供；预览不写入正式知识库，确认后才关联资料。"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


@dataclass
class ResearchResult:
    content: str = ""
    sources: list[str] = field(default_factory=list)
    status: str = "补充失败"
    reason: str = "未找到有依据的资料"


class KnowledgeBase:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.catalog_file = self.root / "catalog.json"

    def entries(self):
        if not self.catalog_file.exists():
            return []
        return json.loads(self.catalog_file.read_text(encoding="utf-8-sig"))

    @staticmethod
    def _write(path, value):
        temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
        try:
            temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def register(self, game_names):
        """登记原始仓库名称；重复导入保留已维护状态，不自动猜测别名。"""
        entries = self.entries()
        names = {entry["game_name"].casefold() for entry in entries}
        for name in game_names:
            name = name.strip()
            if name and name.casefold() not in names:
                entries.append(dict(game_name=name, aliases=[], material_file=None,
                                    status="待补充", reason="", last_attempt_at=None))
                names.add(name.casefold())
        self._write(self.catalog_file, entries)

    def process(self, research, statuses=("待补充", "补充失败", "名称待确认")):
        """research(game_name) 返回 ResearchResult；单款查询异常不终止整轮。

        research 应检索并核对可靠网页，只提供来源支持的事实；不能把官方
        版本、配置或价格直接当作卖家安装包、售价和交付承诺。
        返回本轮各款处理结果，预览保存在 previews/，等待显式确认。
        """
        outcomes = []
        for snapshot in self.entries():
            if snapshot["status"] not in statuses:
                continue
            entries = self.entries()
            entry = next(item for item in entries if item["game_name"] == snapshot["game_name"])
            attempted = datetime.now(timezone.utc).isoformat()
            try:
                result = research(entry["game_name"])
                usable = bool(result.content.strip()) and bool(result.sources) and all(
                    url.startswith(("https://", "http://")) for url in result.sources
                )
            except Exception as exc:
                result = ResearchResult(reason=f"查询失败：{type(exc).__name__}")
                usable = False
            entry["last_attempt_at"] = attempted
            if usable:
                preview_id = uuid4().hex
                directory = self.root / "previews"
                directory.mkdir(exist_ok=True)
                self._write(directory / f"{preview_id}.json", dict(
                    game_name=entry["game_name"], content=result.content,
                    sources=result.sources, last_attempt_at=attempted,
                ))
                if not entry["material_file"]:
                    entry.update(status="待补充", reason="已生成预览，等待确认")
                outcomes.append(dict(game_name=entry["game_name"], result="等待确认", preview_id=preview_id))
            else:
                # 更新失败时保留此前确认的资料；新游戏资料文件仍为空。
                if not entry["material_file"]:
                    entry["status"] = "名称待确认" if result.status == "名称待确认" else "补充失败"
                entry["reason"] = result.reason or "未找到有依据的资料"
                outcomes.append(dict(game_name=entry["game_name"], result="补充失败", reason=entry["reason"]))
            self._write(self.catalog_file, entries)
        return outcomes

    def confirm(self, preview_id):
        """调用方展示预览并获得用户确认后调用。拒绝过期预览。"""
        if len(preview_id) != 32 or any(c not in "0123456789abcdef" for c in preview_id):
            raise ValueError("预览编号无效")
        preview = json.loads((self.root / "previews" / f"{preview_id}.json").read_text(encoding="utf-8"))
        entries = self.entries()
        entry = next(item for item in entries if item["game_name"] == preview["game_name"])
        if entry["last_attempt_at"] != preview["last_attempt_at"]:
            raise ValueError("预览已过期，请查看最新查询结果")
        filename = f"{preview_id}.md"
        content = preview["content"] + "\n\n## 资料来源\n\n" + "\n".join(f"- {url}" for url in preview["sources"]) + "\n"
        (self.root / filename).write_text(content, encoding="utf-8")
        entry.update(material_file=filename, status="已补充", reason="")
        self._write(self.catalog_file, entries)
        return self.root / filename

    def lookup(self, name):
        """先匹配目录；资料缺失不能解释为没有这个游戏。"""
        matches = [entry for entry in self.entries() if name.strip().casefold() in {
            value.strip().casefold() for value in [entry["game_name"], *entry["aliases"]]
        }]
        if not matches:
            return dict(registered=False, message="当前目录未查到，需要卖家确认。")
        if len(matches) > 1:
            return dict(registered=None, message="存在同名或别名冲突，需要卖家确认。")
        entry = matches[0]
        result = dict(entry, registered=True, content=None)
        if entry["status"] == "已补充" and entry["material_file"]:
            path = (self.root / entry["material_file"]).resolve()
            if path.is_relative_to(self.root.resolve()) and path.suffix == ".md":
                try:
                    result["content"] = path.read_text(encoding="utf-8-sig").strip() or None
                except (OSError, UnicodeError):
                    pass
        result["message"] = "读取知识库回答。" if result["content"] else "仓库已登记该游戏，但具体版本、配置等尚未确认。"
        return result
