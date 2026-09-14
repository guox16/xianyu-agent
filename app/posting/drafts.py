"""把当前草稿和写作要求保存到本地，文件名不使用用户输入。"""

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.core.config import PROJECT_ROOT
from app.posting.schemas import PostingDraft, PostingRequest


DRAFT_DIR = PROJECT_ROOT / "drafts"

# 保存草稿
# request: 当前要求
# draft: 当前草稿
# revisions: 修订记录
def save_draft(request: PostingRequest, draft: PostingDraft, revisions: list[str]) -> Path:
    if draft.questions:
        raise ValueError("请先解决追问后保存草稿。")
    created = datetime.now(timezone.utc)
    record = {"created_at": created.isoformat(), "request": request.model_dump(),
              "draft": draft.model_dump(), "revisions": list(revisions)}
    DRAFT_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{created:%Y%m%dT%H%M%S}-{uuid4().hex}"
    temporary = DRAFT_DIR / f"{name}.tmp"
    target = DRAFT_DIR / f"{name}.json"
    # 完整写入后再改名，避免中断或磁盘错误留下看似完整的 JSON 草稿。
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temporary.rename(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target
