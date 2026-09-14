# 知识库维护

独立模块，当前尚未接入客服入口或联网搜索服务。支持通过夸克分享目录导入游戏名称。
调用方提供真实仓库游戏列表（或使用下方夸克导入命令）及 `research(game_name)` 检索函数。
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

## 读取夸克分享目录

在项目根目录运行（默认只生成扫描报告）：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m app.knowledge.quark "https://pan.quark.cn/s/分享编号"
# 读取并登记到 materials/catalog.json：
.\.venv\Scripts\python.exe -X utf8 -m app.knowledge.quark "https://pan.quark.cn/s/分享编号" --import-catalog
# 有提取码时追加 --passcode "提取码"；自定义输出目录时追加 --root "目录路径"。
```

`quark.py` 使用分享网页的 token/detail 接口，分页面读取目录，不下载或转存文件。
只支持允许匿名读取的分享；需要登录、验证、提取码错误或分享失效时报告错误。
这是网页接口，平台变动后可能需要调整。请求超时为 25 秒；失败不自动无限重试。

自动进入“游戏合集…”、大写字母分类及“数字开头游戏”目录，遇到游戏目录即停止，
不进入安装包子目录。跳过“游戏模拟器及其它软件”和常见说明文件。
其他分享的分类结构可能不同，首次导入应检查扫描报告，当前规则不是通用游戏识别器。

从唯一一对 `《》` 提取候选名称，去掉两端空格；不猜测别名，不核实版本宣传。
无唯一标题的条目保留原名并标记名称待确认。原目录名、路径、文件 ID、分享链接
及扫描时间保存在 `materials/quark-scan.json`，同名不同版本的来源记录仍保留。
每次成功扫描覆盖这个报告。凭证和提取码不写入报告。

完整扫描后才更新目录；同名条目保留原状态、别名和资料文件，不删除旧商品。
目录导入不算资料检索，`last_attempt_at` 仍为 null；真正查询资料时才更新。
未被本次分享列出的旧条目不代表已经下架。现有客服工具仍需后续接入 `lookup()`。

默认处理待补充、补充失败、名称待确认的条目。失败也是本轮已处理，
记录原因和尝试时间后继续。成功查询只生成预览，确认后保存 Markdown
并关联文件。再次查询会使旧预览失效。可通过 `statuses` 参数筛选重试。
更新已有资料失败时保留此前确认的资料，并在 reason 记录失败原因。

`lookup` 返回 registered、content 和说明。文件丢失时仍保留登记状态；
目录未命中只表示未查到，不能断言没有该游戏。目录损坏会抛出异常，
调用方应提示查询失败，不能当成目录为空。当前仅支持单进程串行维护。
