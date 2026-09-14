# 知识库维护

独立模块，当前尚未接入客服入口或联网搜索服务。不会自动扫描远程仓库。
调用方提供真实仓库游戏列表及 `research(game_name)` 检索函数。
检索函数负责逐款查询可靠网页、消除同名歧义，并返回有来源依据的
`ResearchResult(content=正文, sources=来源网址列表)`；不能仅靠网址存在
判断内容可信。无法核实时返回 `status="补充失败"` 或 `"名称待确认"` 及原因。

```python
from app.config import PROJECT_ROOT
from app.knowledge import KnowledgeBase, ResearchResult

kb = KnowledgeBase(PROJECT_ROOT / "materials")
kb.register(warehouse_game_names)
outcomes = kb.process(research)
# 展示 outcomes 中的 previews/<preview_id>.json 给用户审阅。
# 仅在用户明确确认对应预览后：
kb.confirm(confirmed_preview_id)
# 客服可通过这个接口先查登记状态、再读取资料：
result = kb.lookup("游戏名称")
```

`catalog.json` 是数组，每款记录 `game_name`、`aliases`、`material_file`、
`status`、`reason`、`last_attempt_at`。初始状态为待补充，别名由人工确认后
登记，时间使用带时区的 ISO 8601 字符串，尚未尝试时为 null。
此模块不会自动迁移现有资料或推断仓库商品。

默认处理待补充、补充失败、名称待确认的条目。失败也是本轮已处理，
记录原因和尝试时间后继续。成功查询只生成预览，确认后保存 Markdown
并关联文件。再次查询会使旧预览失效。可通过 `statuses` 参数筛选重试。
更新已有资料失败时保留此前确认的资料，并在 reason 记录失败原因。

`lookup` 返回 registered、content 和说明。文件丢失时仍保留登记状态；
目录未命中只表示未查到，不能断言没有该游戏。目录损坏会抛出异常，
调用方应提示查询失败，不能当成目录为空。当前仅支持单进程串行维护。
