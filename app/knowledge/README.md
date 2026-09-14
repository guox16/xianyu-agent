# 知识库维护

在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m app.knowledge.main
```

也可以在编辑器里直接运行 `app/knowledge/main.py`，或运行项目 `main.py` 选择 3。
运行后直接粘贴夸克分享链接，不显示菜单，也不再询问数量或逐款确认。
程序自动导入目录并处理全部待补充、补充失败、名称待确认条目，完成后结束。
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
当前客服入口仍未接入此查询接口。

首次启动会合并旧商品目录、总资料文件、关联的 Markdown 和有效旧预览。
旧文件保留为备份，旧 knowledge.json 另备份到 knowledge-before-merge.json。
迁移后只使用新文件，不再读取旧目录；可重复启动，不会恢复被删除的旧条目。

扫描报告 quark-scan.json 保留原始网盘路径，generation-report.json 保存最近一轮结果；
它们是辅助报告，不是分开的商品数据源。用户要求不做自动重试，文件写入失败不会自动重试。
当前仅支持单进程串行写入。

## 资料生成

main.py 调用 quark.py 导入，再把 research.py 的 research_game 交给 workflow.py。
目前使用 Steam 商店搜索和详情接口，只有唯一完整名称匹配才生成参考资料。
不需要模型密钥，不调用 DeepSeek；名称或译名不匹配不代表仓库没有该游戏。
卖家安装包版本、DLC、价格、交付和售后不会从官方商店资料中推断。

## 单独读取夸克

```powershell
.\.venv\Scripts\python.exe -X utf8 -m app.knowledge.quark "https://pan.quark.cn/s/分享编号" --import-catalog
```

没有 --import-catalog 时只生成扫描报告；有提取码则追加 --passcode "提取码"。
匿名分享读取使用网页接口，遇到登录或验证要求会报错，不下载或转存游戏。
支持合集、字母和数字分类结构；提取唯一《标题》，不明确则保留原名待确认。
导入去重并保留已有资料，不根据本次扫描删除旧商品。
