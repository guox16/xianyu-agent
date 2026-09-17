# 我的 Agent 学习项目

## 项目目标

1. 智能客服：根据商品资料回答问题，支持多轮对话。
2. 发帖生成：根据要求生成商品标题和正文，支持继续修改。

## 开发方式

使用 Python，先独立开发和测试，后续通过接口连接闲鱼系统。

## 第一版范围

- 使用文字交互。
- 使用本地商品资料。
- 生成发帖草稿。

## 学习进度

- [x] 创建项目目录和说明文件。
- [x] 检查 Python 环境，创建项目专用的虚拟环境。
- [x] 客服基础流程：模型调用、本地资料、上下文、工具查询、菜单入口。
- [x] 发帖生成：资料查询、结构化草稿、多轮修改、本地保存与菜单入口。
- [ ] 对接闲鱼系统。

## 启动项目

在项目根目录运行以下命令（Windows PowerShell）：

```powershell
# 在其他电脑首次使用时创建环境并安装依赖；本机已准备好可跳过。
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 启动菜单。
.\.venv\Scripts\python.exe -X utf8 main.py
```

运行前准备根目录的 `.env`，字段参考 `.env.example`，填写自己的 DeepSeek API Key、模型名称和接口地址。已有环境变量优先于 `.env`。不要覆盖已有私密配置或把密钥提交到 Git。

## Langfuse 调用链追踪（可选）

项目已通过 Langfuse 的 LangChain 回调接入客服、质检、改写、发帖以及知识库的 DeepSeek 兜底调用。它会记录模型输入输出、工具调用、耗时、token 与错误；客服和发帖的同一轮会话会按独立 `session_id` 聚合。

在 `.env` 中同时填写 `LANGFUSE_PUBLIC_KEY` 和 `LANGFUSE_SECRET_KEY` 后自动启用；留空或只填写其中一项都会禁用追踪，原业务流程不受影响。云端 EU 区域使用 `LANGFUSE_BASE_URL=https://cloud.langfuse.com`，自托管或其他区域请替换为对应地址。短生命周期命令行会话退出时会主动 flush 已积累事件。

**数据提示：** Langfuse 会收到发送给模型的用户问题、本地商品资料、提示词、工具结果和模型输出。请仅在符合你的数据处理要求的 Langfuse 项目或自托管实例中启用，且不要把 Langfuse 密钥提交到 Git。

本地资料位于 `materials/knowledge.json`，此目录被 Git 忽略。客服和发帖只读取状态为“已补充”的知识库记录；游戏名称可使用已确认别名。请先从菜单 `3` 导入并维护知识库，再进入客服或发帖。

- 菜单输入 `1` 进入客服，先输入当前游戏名称或已确认别名，输入 `0` 退出程序。
- 客服输入 `/exit` 返回菜单，重新进入会创建新会话。
- 客服输入 `/clear` 清空问答与工具结果；下次商品咨询重新查询。
- 菜单输入 `2` 进入发帖生成，依次输入知识库中的当前游戏、语气、长度和重点。
- 发帖生成后直接输入“简短一点”“突出安装指导”等要求继续修改。
- `/save` 保存当前草稿，`/retry` 重试上次生成或修改，`/new` 输入新的要求并重新查询资料，`/exit` 返回菜单。
- 退出前请保存。重新进入不会恢复内存中的修改上下文；保存的 JSON 文件仍可直接打开查看。

## 目录结构

```text
app/
  core/                 通用基础，供两个业务模块复用
    config.py           配置读取与项目根目录
    context.py          长会话的安全压缩
    model.py            模型创建
    materials.py        本地资料读取
    material_tools.py   商品资料查询工具
  customer/             客服业务
    agent.py            客服规则与多轮问答
    cli.py              客服命令行入口
  posting/              发帖业务
    agent.py            发帖规则、生成与连续修改
    schemas.py          输入要求与输出草稿的数据结构
    drafts.py           本地草稿保存
    cli.py              发帖命令行入口
tests/       自动化测试
examples/    普通问答与直接传资料的学习示例
materials/   本地商品资料，不提交 Git
drafts/      本地 JSON 草稿，不提交 Git
main.py      菜单入口
```

`main.py` 负责菜单分发，分别进入 `customer/cli.py` 和 `posting/cli.py`。客服与发帖各自管理会话，共同依赖 `core/`；`core/` 不依赖具体业务模块。包内的 `__init__.py` 仅标记 Python 包，不创建模型或会话。测试继续集中放在 `tests/test_app.py`。

## 对接 Plus 客服

安装依赖后，在项目根目录运行 `uvicorn app.customer.http:app --host 127.0.0.1 --port 12500`。Plus 开启 `AGENT_CUSTOMER_ENABLED=true` 后会调用 `POST /customer/reply`，并传入当前商品资料、会话标识和已聚合的买家消息。Agent 只返回 `answered` 加候选回复，或 `needs_human`；黑名单、人工接管、开关、最终发送和记录仍由 Plus 执行。

若通过 `xianyu-Plus/compose.yaml` 部署，Compose 会直接构建本项目的 `Dockerfile`，并从本项目根目录 `.env` 读取模型配置；`materials/` 会以只读卷挂载进容器。无需向宿主机暴露 12500 端口，Plus 在 Compose 网络中通过 `http://agent:12500` 调用。

## 客服如何运行

```text
菜单进入客服 → 用户提问 → 客服 Agent 决定是否查询
                         → 工具读取已登记的本地资料 → 生成候选回复
                         → 质检 Agent 审核 → 通过后回答买家
                                           → 不通过时改写一次再审核
```

入口只提供当前商品名称。资料全文在工具查询成功后作为工具结果交给模型；后续可以复用会话中的查询结果。质检 Agent 只接收用户问题、成功的工具结果和候选回复，并结构化返回通过/不通过及改写要求，不直接回复买家。工作流最多改写一次；第二次仍不通过时返回安全兜底，不发送未通过的候选回复。聊天历史保留用户消息、模型的工具调用、工具结果和最终回复，失败的轮次不写入历史。

资料查询工具只读取知识库内“已补充”的记录，未知游戏、歧义别名或没有确认资料的游戏会返回明确状态。资料虽不提交 Git，但工具返回的内容会发送给 DeepSeek。此阶段没有 MCP、真实订单查询、发货或退款操作。

客服、质检子 Agent 和工作流统一定义在 `app/customer/agent.py`。质检由独立的 `create_agent` 子 Agent 执行，父工作流的 `review` 节点负责调用它。子 Agent 有自己的系统规则和每次独立的消息状态，不提供业务查询或操作工具；通过 `ToolStrategy(ReviewDecision)` 提交审核结果，格式错误时可在内部纠正。内部执行上限为 12 个图步骤，与外层“最多改写一次”的限制分别生效。审核异常或未返回有效结果时，本轮不发送候选回复、不保存历史，由命令行提示重试。

当前会话仅保存在内存中，关闭或退出后不保留。长会话会自动压缩：保留最近三轮对话与最新成功的完整资料工具调用链，较早普通问答由模型生成不超过 240 字符的非事实摘要；摘要不能作为商品事实，商品事实仍只能来自工具结果。资料更新后可清空会话再查询。模型可能回答错误，工具约束和提示词不等于事实正确性的保证。

## 发帖如何运行

```text
菜单进入发帖 → 输入游戏、语气、长度、重点 → query_game_material 查询本地事实
            → 发帖 Agent 返回结构化草稿或追问 → 连续修改 → /save 保存 JSON
```

`app/posting/agent.py` 单独定义发帖规则，复用 `create_model()` 的模型、密钥和接口配置，发帖输出上限为 2048 tokens。程序强制先调用知识库资料查询工具，查询失败时直接提示补充资料，不请求模型编造文案。查询成功后保留成对的工具消息，修改时继续携带原始资料、写作要求和历次修改结果。

`app/posting/schemas.py` 定义输入 `current_game`、`tone`、`length`、`focus`，以及输出 `title`（标题）、`body`（正文）、`missing_information`（待补充信息）、`questions`（关键追问）。LangChain 的 `ToolStrategy` 按结构返回结果，并校验字段；格式不合要求时提示模型纠正，整个调用有循环上限。截断、接口错误或无法完成的结果不覆盖旧稿。

未确认的信息不能成为宣传承诺，文案示例和用户补充断言也不能代替商品资料。若要求依赖未确认的 DLC、永久链接等关键信息，先追问，标题正文为空；普通草稿只写已确认内容，其余列入待补充信息。可以继续要求“不写 DLC 了”，也可以更新本地资料后用 `/new` 重新查询。连续修改超过三次时会裁剪较早修改记录，但始终保留初始要求、完整资料查询链和最近三次修改。修改过程中出现追问时保留旧稿，但暂不允许保存，防止把旧稿误认为修改已完成。

`/save` 将当前输入、标题、正文、待补充信息、修改要求及 UTC 保存时间写入 `drafts/` 下独立的 UTF-8 JSON 文件，多次保存不会覆盖旧文件。该目录加入 Git 忽略，文件名不采用用户输入。程序退出后可用文本编辑器查看文件；目前不支持从文件恢复多轮会话，也不自动发布到闲鱼。

示例要求和预期草稿见 `examples/posting-request.md`。模型生成的措辞并非固定模板，事实遵循仍需人工核对；本阶段未实现逐项语义事实校验或长会话裁剪。

## 验证与学习示例

```powershell
# 离线测试，不调用 DeepSeek。
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -v

# 检查本地配置，不调用 DeepSeek。
.\.venv\Scripts\python.exe -X utf8 -m app.core.config

# 普通问答学习示例，不自动查询商品资料。
.\.venv\Scripts\python.exe -X utf8 -m examples.model_call
```

测试统一放在 `tests/test_app.py`。当前 24 项离线测试通过，覆盖客服原有流程，以及发帖字段约定、资料查询、结构化格式纠正、关键追问、连续修改、失败保留旧稿、文件保存和菜单流程。离线测试模拟模型决策，工具执行与 Agent 编排使用真实代码，不能代替真实模型的文案质量验收。

已用真实 DeepSeek 请求验证知识库游戏的生成、连续两次修改、保存、返回菜单与退出，修改后保留资料中的价格限定、交付、安装指导及服务限制。另已验证要求宣传未确认 DLC 和永久链接时先追问，撤销这些要求后可继续生成。

## 使用虚拟环境

在项目目录下，可以直接使用虚拟环境中的 Python，无需先激活：

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip --version
```

也可以在 PowerShell 中激活当前终端的虚拟环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

激活后可以直接使用 `python` 和 `python -m pip`；使用 `deactivate` 退出。
如果激活脚本被执行策略阻止，可使用上面的完整路径命令。

`.venv` 用于保存运行环境和依赖，不存放项目代码，也不提交到 Git。
