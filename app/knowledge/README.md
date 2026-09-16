# 知识库维护

## 文档切分

在项目根目录执行以下命令，生成 `materials/index/chunks.json`：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m app.knowledge.chunking
```

原始资料仍保存在 `knowledge.json`，分块文件是可重建的检索副本；资料更新后需重新执行命令。
已实现切分与 BM25 关键词检索，尚未接入 Embedding 或客服检索。

- 默认 1000 字符以内保留全文；长资料按二级标题切分，过长章节再按三级标题切分。
- 可用 `--max-chars 800` 调整软阈值。无标题长文和完整三级章节不强行截断，分块允许超长。
- 父章节前言附在子块正文前，围栏代码块中的标题不参与切分。
- 每块包含稳定内容标识、游戏名、别名、章节、正文、整条资料来源、更新时间及检索文本。
- 二级标题包含“待确认、注意事项、免责声明、适用范围”的内容复制到每块 `notices`；后续回答时需与正文一起传入模型。其他散落限制仍需在整理资料时保留在所属章节内。
- 待核验标记传递至每个分块；存在来源链接不代表逐块核验或卖家确认。
- 只切分“已补充”的已保存正文，忽略空资料和未提交预览。

程序调用：`KnowledgeBase(root).chunks(max_chars=1000)`，只返回分块，不写文件。

## BM25 关键词检索

安装依赖后，在项目根目录查询：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -X utf8 -m app.knowledge.bm25 "回合制 策略" --top-k 5
.\.venv\Scripts\python.exe -X utf8 -m app.knowledge.bm25 "配置" --game "苏丹的游戏"
```

程序调用：

```python
from pathlib import Path
from app.knowledge import KnowledgeBase
from app.knowledge.bm25 import BM25Retriever

kb = KnowledgeBase(Path("materials"))
results = kb.search("配置", game_name="苏丹的游戏", top_k=5)

# 多次查询时复用内存索引；资料变动后重新创建。
retriever = BM25Retriever(kb.chunks())
results = retriever.search("回合制 策略", top_k=5)
```

- `KnowledgeBase.search` 每次读取当前原始资料并重新切分建索引，不依赖导出的 `chunks.json`，不修改知识文件。
- 中文采用 jieba 搜索模式，英文忽略大小写；保留错误码及带点、连字符的版本号，过滤少量常见语气词。只做关键词匹配，不做同义词或语义扩展。
- 采用正值 IDF 的 BM25，参数 `k1=1.2`、`b=0.75`；单条资料也能正常命中。
- 指定游戏时按名称或别名匹配（忽略空白、大小写和全半角差异），不删除版本信息。未知名称返回空列表，歧义名称报错，不回退全库。
- 未指定游戏时搜索全库，不自动从问题识别游戏；需要业务调用方传入当前游戏。
- 返回完整分块元数据，并附加 `bm25_score`、`matched_terms`、`rank`、`retrieval_method`，供后续向量结果融合使用。
- 空查询、仅语气词或完全无词命中返回空列表，不拿零分资料凑数。命中部分词不代表资料足以回答问题，分数也不代表事实可信度。
- 此入口未接入客服和发帖，尚未实现向量检索或 RRF 融合。使用检索结果回答时应保留 `notices`、来源及待核验标记。

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

扫描报告 quark-scan.json 保留原始网盘路径，是辅助报告而非分开的商品数据源。用户要求不做自动重试，文件写入失败不会自动重试。
当前仅支持单进程串行写入。

## 资料生成

名称匹配区分仓库原名与检索名。明确版本后缀（如次世代、豪华版）不参与作品匹配；
完整匹配优先，其次支持带作品编号的简称与副标题，例如“巫师3”与“巫师3：狂猎”。
完整查询无匹配时，用基础名称另查一次；这是不同查询，不是请求失败后的自动重试。
作品编号不同、双方副标题冲突、DLC 或多个同分候选不会直接合并。
没有编号的系列简称不自动绑定某一部，保留仓库原名和来源作品名。
匹配基础作品不代表已确认该版本的内容与配置。

main.py 调用 quark.py 导入，再把 research.py 的 research_game 交给 workflow.py。
顺序为 Steam → Wiki → DeepSeek 简要资料兜底。
Steam 或 Wiki 任一取得可用资料就直接保存；Wiki 成功后不会返回 Steam。
最后兜底复用项目 .env 中的 DeepSeek 配置，仅把游戏名称发给模型，每款最多调用一次。
模型直接返回不超过 600 字的简要资料；不猜测别名，不输出价格、版本、DLC、配置或售后信息。
DeepSeek 资料会明确标为“待核验”，没有伪造来源链接；需配置有效模型密钥，会产生模型调用用量。
配置无效、模型失败或无法识别作品，统一记录补充失败。模型资料仍可能不准确，不保证所有游戏都能补充。

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
