# 知识库维护

在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m app.knowledge.main
```

也可以在编辑器里直接运行 `app/knowledge/main.py`，或运行项目 `main.py` 选择 3。
运行后直接粘贴夸克分享链接，不显示菜单，也不再询问数量或逐款确认。
程序自动导入目录并处理全部待补充、补充失败条目，完成后结束。
带提取码的链接可以使用 `?pwd=提取码`；函数调用也支持单独传 passcode。
不展示正文或要求审核；
处理时显示进度，结束后只汇总数量，详细结果保存在处理报告中。
已补充条目跳过；成功自动保存，搜不到或名称有歧义则记录原因并继续。

## 供后续接口调用

```python
from app.knowledge.main import update_from_share

result = update_from_share("https://pan.quark.cn/s/分享编号", passcode="")
```

函数不调用 input，返回 scanned、added、results、knowledge_file。
results 包含逐款成功/失败状态。分享访问或文件读写异常交给接口调用方处理。
目前是同步 Python 函数，尚未创建 HTTP 服务；接入接口时可放在后台任务中运行。

## 一个文件保存目录和资料

`materials/knowledge.json` 是游戏记录数组，同时保存：

- game_name、aliases：名称与已确认别名。
- status、reason、last_attempt_at：资料状态、原因、最近查询时间。
- content、sources、updated_at：正文、来源、资料更新时间。
- pending_preview：生成后尚未提交的内容，也放在同一记录中，提交成功即移除。
- material_file：旧接口兼容字段，已补充时指向 knowledge.json。

不再创建单独的 catalog.json、游戏 Markdown 或预览文件。
查询先匹配名称，只向 AI 返回这款游戏的正文；登记状态与正文是否存在仍分开判断。
导入时会合并仅空格、标点或明确版本后缀不同的名称；已由 Steam 或维基百科确认的中英文别名也会归入同一条记录。
当前客服入口仍未接入此查询接口。

首次启动会合并旧商品目录、总资料文件、关联的 Markdown 和有效旧预览。
迁移直接写入 `knowledge.json`，不再创建 `knowledge-before-merge.json` 备份。
迁移后只使用新文件，不再读取旧目录；可重复启动，不会恢复被删除的旧条目。

扫描报告 quark-scan.json 保留原始网盘路径，generation-report.json 保存最近一轮结果；
它们是辅助报告，不是分开的商品数据源。用户要求不做自动重试，文件写入失败不会自动重试。
当前仅支持单进程串行写入。

## 资料生成

名称匹配区分仓库原名与检索名。明确版本后缀（如次世代、豪华版）不参与作品匹配；
完整匹配优先，其次支持带作品编号的简称与副标题，例如“巫师3”与“巫师3：狂猎”。
完整查询无匹配时，用基础名称另查一次；这是不同查询，不是请求失败后的自动重试。
作品编号不同、双方副标题冲突、DLC 或多个同分候选不会直接合并。
没有编号的系列简称不自动绑定某一部，保留仓库原名和来源作品名。
匹配基础作品不代表已确认该版本的内容与配置。

main.py 调用 quark.py 导入，再把 research.py 的 research_game 交给 workflow.py。
顺序为 Steam → Wiki → MyMemory 翻译名称 → Steam 英文查询 → DeepSeek 候选名称兜底。
Steam 或 Wiki 任一取得可用资料就直接保存；Wiki 成功后不会返回 Steam。
只有前两步失败才向 MyMemory 发送基础游戏名，译出的英文名再交给 Steam 核对。
资料来源仍只有 Steam 和维基百科，MyMemory 不提供正文、不写入来源链接，
翻译结果只作为候选检索名，不自动登记为已确认别名。最终仍检查编号、副标题、
游戏类型与候选唯一性；翻译不能保证官方译名或正确身份，结果中保留翻译匹配说明。

MyMemory 不需要密钥，匿名额度通常为每天 5000 字符，单次名称不超过 500 字节。
官方说明：https://mymemory.translated.net/doc/usagelimits.php
只在前两层失败时调用，不发送资料正文；额度用完、请求失败或翻译无效会记录原因。
不自动重试。Steam 超时 20 秒，Wiki 和 MyMemory 超时 15 秒。
最后兜底复用项目 .env 中的 DeepSeek 配置，仅把游戏名称发给模型，每款最多调用一次。
模型最多提供两个候选作品名，再查 Steam/Wiki，必须有可读来源正文才成功。
模型不直接编写正式资料，不把模型候选自动登记为确认别名；需配置有效模型密钥，会产生模型调用用量。
配置无效、模型失败或候选无法取得资料，统一记录补充失败。模型建议仍可能不准确，不保证所有游戏都能补充。

游戏状态仅有待补充、已补充、补充失败；原名称待确认记录自动归入补充失败并保留原因。
运行报告只分已保存和补充失败，写入错误也归入失败，不自动重试。
若存储不可写，失败可能只能显示在运行结果/报告中，不能保证该失败状态写入知识文件。
卖家安装包版本、DLC、价格、交付和售后不会从官方商店资料中推断。

## 单独读取夸克

```powershell
.\.venv\Scripts\python.exe -X utf8 -m app.knowledge.quark "https://pan.quark.cn/s/分享编号" --import-catalog
```

没有 --import-catalog 时只生成扫描报告；有提取码则追加 --passcode "提取码"。
匿名分享读取使用网页接口，遇到登录或验证要求会报错，不下载或转存游戏。
支持合集、字母和数字分类结构；提取唯一《标题》，不明确则保留原名待确认。
导入去重并保留已有资料，不根据本次扫描删除旧商品。
