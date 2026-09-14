"""研究函数由调用方提供；先生成预览，再由入口提交为正式资料。"""

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
        self.knowledge_file = self.root / "knowledge.json"
        # 兼容导入模块的旧属性名，实际只读写这一个文件。
        self.catalog_file = self.knowledge_file

    def materials(self):
        """一次读取总资料文件，调用方按游戏名取出所需的一条。"""
        return {entry["game_name"]: entry for entry in self.entries() if entry.get("content")}

    def migrate_materials(self):
        """旧目录、正文和有效预览合并；不删除旧文件，不自动重试。"""
        entries = self.entries()
        current = json.loads(self.knowledge_file.read_text(encoding="utf-8-sig")) if self.knowledge_file.exists() else None
        if entries and current != entries:
            if current is not None:
                backup = self.root / "knowledge-before-merge.json"
                if not backup.exists():
                    self._write(backup, current)
            self._write(self.knowledge_file, entries)
            return [entry["game_name"] for entry in entries]
        return []

    def entries(self):
        data = json.loads(self.knowledge_file.read_text(encoding="utf-8-sig")) if self.knowledge_file.exists() else {}
        if isinstance(data, list):
            entries = data
        elif isinstance(data, dict):
            legacy = self.root / "catalog.json"
            entries = json.loads(legacy.read_text(encoding="utf-8-sig")) if legacy.exists() else []
            names = {entry["game_name"] for entry in entries}
            for name in data:
                if name not in names:
                    raise ValueError(f"旧知识库缺少对应登记记录：{name}")
            for entry in entries:
                material = data.get(entry["game_name"], {})
                entry.update({key: value for key, value in material.items() if key != "game_name"})
                # 迁移有效且尚未保存的旧版预览。
                for path in (self.root / "previews").glob("*.json"):
                    preview = json.loads(path.read_text(encoding="utf-8"))
                    if preview["game_name"] == entry["game_name"] and preview["last_attempt_at"] == entry["last_attempt_at"] and entry.get("preview_id") != path.stem and entry.get("material_file") != path.stem + ".md":
                        entry["pending_preview"] = dict(preview, preview_id=path.stem)
        else:
            raise ValueError("knowledge.json 必须是游戏记录数组。")
        for entry in entries:
            filename = entry.get("material_file")
            if filename and filename.endswith(".md") and not entry.get("content"):
                path = (self.root / filename).resolve()
                if not path.is_relative_to(self.root.resolve()):
                    raise ValueError("旧资料路径无效")
                entry.update(content=path.read_text(encoding="utf-8-sig").strip(), legacy_file=filename, preview_id=path.stem)
                entry["material_file"] = self.knowledge_file.name
            entry.setdefault("content", None)
            entry.setdefault("sources", [])
        return entries

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
                                    status="待补充", reason="", last_attempt_at=None, content=None, sources=[]))
                names.add(name.casefold())
        self._write(self.catalog_file, entries)

    def process(self, research, statuses=("待补充", "补充失败", "名称待确认"), game_names=None):
        """research(game_name) 返回 ResearchResult；单款查询异常不终止整轮。

        research 应检索并核对可靠网页，只提供来源支持的事实；不能把官方
        版本、配置或价格直接当作卖家安装包、售价和交付承诺。
        返回本轮各款处理结果，预览暂存在同一记录的 pending_preview 中。
        """
        outcomes = []
        for snapshot in self.entries():
            if snapshot["status"] not in statuses:
                continue
            if game_names is not None and snapshot["game_name"] not in game_names:
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
                entry["pending_preview"] = dict(
                    game_name=entry["game_name"], content=result.content,
                    sources=result.sources, last_attempt_at=attempted, preview_id=preview_id,
                )
                if not entry["material_file"]:
                    entry.update(status="待补充", reason="已生成预览，等待确认")
                outcomes.append(dict(game_name=entry["game_name"], result="等待确认", preview_id=preview_id))
            else:
                entry.pop("pending_preview", None)
                # 更新失败时保留此前确认的资料；新游戏资料文件仍为空。
                if not entry["material_file"]:
                    entry["status"] = "名称待确认" if result.status == "名称待确认" else "补充失败"
                entry["reason"] = result.reason or "未找到有依据的资料"
                outcomes.append(dict(game_name=entry["game_name"], result="补充失败", reason=entry["reason"]))
            self._write(self.catalog_file, entries)
        return outcomes

    def confirm(self, preview_id):
        """用户确认或已选择自动保存模式后调用。拒绝过期预览。"""
        if len(preview_id) != 32 or any(c not in "0123456789abcdef" for c in preview_id):
            raise ValueError("预览编号无效")
        entries = self.entries()
        entry = next((item for item in entries if item.get("pending_preview", {}).get("preview_id") == preview_id), None)
        if entry is None:
            raise ValueError("预览不存在或已过期")
        preview = entry["pending_preview"]
        if entry["last_attempt_at"] != preview["last_attempt_at"]:
            raise ValueError("预览已过期，请查看最新查询结果")
        content = preview["content"] + "\n\n## 资料来源\n\n" + "\n".join(f"- {url}" for url in preview["sources"]) + "\n"
        entry.update(content=content, sources=preview["sources"],
                     updated_at=preview["last_attempt_at"], preview_id=preview_id)
        entry.pop("pending_preview")
        entry.update(material_file=self.knowledge_file.name, status="已补充", reason="")
        self._write(self.catalog_file, entries)
        return self.knowledge_file

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
        result.pop("pending_preview", None)
        if entry["status"] == "已补充":
            result["content"] = entry.get("content") or None
        result["message"] = "读取知识库回答。" if result["content"] else "仓库已登记该游戏，但具体版本、配置等尚未确认。"
        return result
