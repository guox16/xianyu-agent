"""按 Markdown 标题切分资料；长度是软阈值，不截断完整步骤或段落。"""

import argparse
import hashlib
import json
import re


def _sections(text, level):
    """忽略围栏代码块里的标题，返回前言及当前层级的章节。"""
    prefix, sections, lines = "", [], []
    title = None
    fence = None
    for line in text.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if marker:
            token, rest = marker.groups()
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not rest.strip():
                fence = None
            lines.append(line)
            continue
        heading = None if fence else re.match(r"^ {0,3}" + "#" * level + r"\s+(.+?)\s*$", line)
        if heading:
            body = "\n".join(lines).strip()
            if title is None:
                prefix = body
            else:
                sections.append((title, body))
            title = re.sub(r"\s+#+\s*$", "", heading.group(1))
            lines = []
        else:
            lines.append(line)
    body = "\n".join(lines).strip()
    if title is None:
        prefix = body
    else:
        sections.append((title, body))
    return prefix, sections


def _split(text, limit, level=2, path=()):
    if len(text) <= limit or level > 3:
        return [(path, text)] if text else []
    prefix, sections = _sections(text, level)
    if not sections:
        return _split(text, limit, level + 1, path)
    chunks = []
    for title, body in sections:
        # 父章节前言跟随子块，保留适用版本、条件和背景。
        for child_path, child_body in _split(body, limit, level + 1, (*path, title)):
            chunks.append((child_path, "\n\n".join(part for part in (prefix, child_body) if part)))
        if not body:
            chunks.append(((*path, title), prefix))
    return chunks


def chunk_entries(entries, *, max_chars=1000):
    """切分已保存的正文，返回可序列化分块；不读取未提交预览。

    max_chars 为正文字符数软阈值。无标题的长文本、完整三级章节及
    附带的前言允许超长；来源为整条资料的来源，不代表逐块核验。
    """
    if isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars <= 0:
        raise ValueError("切分长度必须是正整数。")
    chunks = []
    for entry in entries:
        content = (entry.get("content") or "").strip()
        if entry.get("status") != "已补充" or not content:
            continue
        name = entry["game_name"]
        sources = list(entry.get("sources") or [])
        pending = bool(entry.get("model_generated")) or "待核验" in content or not sources
        # 整条资料中的限制需随检索结果一起使用，避免切分丢失卖家信息提示。
        _, sections = _sections(content, 2)
        notices = [f"## {title}\n{body}" for title, body in sections
                   if any(word in title for word in ("待确认", "注意事项", "免责声明", "适用范围"))]
        for index, (path, body) in enumerate(_split(content, max_chars)):
            section = " / ".join(path) or "全文"
            identity = json.dumps([name, index, section, body], ensure_ascii=False)
            chunks.append({
                "chunk_id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
                "game_name": name,
                "aliases": list(entry.get("aliases") or []),
                "section": section,
                "content": body,
                "sources": sources.copy(),
                "source_scope": "整条资料，非逐块核验",
                "verification_status": "待核验" if pending else "有来源参考，未逐块核验",
                "notices": notices.copy(),
                "updated_at": entry.get("updated_at"),
                "search_text": "\n\n".join(part for part in (name, section, body) if part),
            })
    return chunks


def main():
    """显式导出可重建的分块文件，不修改原始知识库。"""
    from app.core.config import PROJECT_ROOT
    from app.knowledge.workflow import KnowledgeBase

    parser = argparse.ArgumentParser(description="按标题切分知识库，生成检索分块文件。")
    parser.add_argument("--max-chars", type=int, default=1000, help="切分字符数软阈值，默认 1000")
    args = parser.parse_args()
    kb = KnowledgeBase(PROJECT_ROOT / "materials")
    chunks = kb.chunks(max_chars=args.max_chars)
    target = kb.root / "index" / "chunks.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    kb._write(target, chunks)
    print(f"已生成 {len(chunks)} 个分块：{target}")


if __name__ == "__main__":
    main()
