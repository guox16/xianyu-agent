"""知识库交互入口：支持直接运行本文件或 python -m app.knowledge.main。"""

from pathlib import Path
import sys

# 编辑器直接运行本文件时，Python 只把当前文件夹加入模块搜索路径。
# 根据文件位置补上项目根目录，才能导入 app；-m 启动时无需处理。
if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.config import PROJECT_ROOT
from app.core.observability import flush_langfuse
from app.knowledge.quark import QuarkClient, import_catalog, scan, parse_share
from app.knowledge.research import research_game
from app.knowledge.workflow import KnowledgeBase


def read(prompt):
    value = input(prompt).strip()
    if value.lower() == "/exit":
        raise EOFError
    return value


def import_quark(kb, url, passcode=""):
    print("正在读取目录，请稍候……", flush=True)
    report = scan(QuarkClient(url, passcode))
    kb._write(kb.root / "quark-scan.json", report)
    added = import_catalog(kb, report)
    print(f"读取 {len(report['games'])} 个候选项，新增登记 {added} 条。")
    return {"scanned": len(report["games"]), "added": added}


def pending_previews(kb):
    return {entry["game_name"]: (entry["pending_preview"]["preview_id"], entry["pending_preview"])
            for entry in kb.entries() if entry.get("pending_preview")}


def save_preview(kb, name, preview_id):
    """用户已选择自动保存模式；磁盘错误保留预览，供下次重试。"""
    try:
        path = kb.confirm(preview_id)
    except (OSError, ValueError) as error:
        return dict(game_name=name, result="补充失败", reason=f"保存失败：{error}")
    return dict(game_name=name, result="已保存", material_file=path.name)


def show_summary(results):
    print("\n本轮处理完成：")
    for status in ("已保存", "补充失败"):
        items = [item for item in results if item["result"] == status]
        print(f"{status}：{len(items)} 条")


def generate(kb, research=research_game):
    pending = pending_previews(kb)
    entries = [entry for entry in kb.entries() if entry["status"] in {"待补充", "补充失败"}]
    if not entries:
        print("没有需要处理的条目。")
        return []
    print(f"可处理 {len(entries)} 条。匹配成功自动保存，搜不到或有歧义则记录后继续。")
    results = []
    for index, entry in enumerate(entries, 1):
        name = entry["game_name"]
        print(f"\n[{index}/{len(entries)}] 正在查询：{name}", flush=True)
        try:
            if name in pending:
                result = save_preview(kb, name, pending[name][0])
            else:
                outcome = kb.process(research, game_names=[name])[0]
                if outcome["result"] == "等待确认":
                    result = save_preview(kb, name, outcome["preview_id"])
                else:
                    current = next(item for item in kb.entries() if item["game_name"] == name)
                    result = dict(game_name=name, result=current["status"], reason=outcome["reason"])
        except (OSError, ValueError) as error:
            result = dict(game_name=name, result="补充失败", reason=f"处理或写入失败：{error}")
        results.append(result)
        print(f"{name}：{result['result']}")
    show_summary(results)
    return results


def update_from_share(url, passcode="", root=None, research=research_game):
    """供接口直接调用；无 input，返回导入数量和逐款处理结果。

    分享/读写错误向调用方抛出；单款检索失败记录在 results 中。
    """
    parse_share(url)
    kb = KnowledgeBase(root or PROJECT_ROOT / "materials")
    kb.migrate_materials()
    imported = import_quark(kb, url, passcode)
    results = generate(kb, research)
    return {**imported, "results": results, "knowledge_file": str(kb.knowledge_file)}


def main(root=None):
    try:
        url = read("夸克分享链接：")
        return update_from_share(url, root=root)
    except (EOFError, KeyboardInterrupt):
        print("\n已结束，已完成的记录会保留。")
    except (OSError, ValueError) as error:
        print(f"本次操作未完成：{error}")
    finally:
        flush_langfuse()


if __name__ == "__main__":
    main()
