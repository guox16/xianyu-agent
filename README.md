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
- [ ] 发帖生成。
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

本地资料位于 `materials/`，此目录被 Git 忽略。复制项目到另一台电脑时需要单独准备 UTF-8 商品资料；默认映射为 `materials/sultans-game.md`。增加游戏时，在 `app/material_tools.py` 的 `GAME_FILES` 中登记名称和文件名。

- 菜单输入 `1` 进入客服，输入 `0` 退出程序。
- 客服输入 `/exit` 返回菜单，重新进入会创建新会话。
- 客服输入 `/clear` 清空问答与工具结果；下次商品咨询重新查询。
- 菜单中的发帖生成暂未实现。

## 目录结构

```text
app/         业务代码：配置、模型、资料读取、查询工具、客服 Agent 和聊天入口
tests/       自动化测试
examples/    普通问答与直接传资料的学习示例
materials/   本地商品资料，不提交 Git
main.py      菜单入口
```

## 客服如何运行

```text
菜单进入客服 → 用户提问 → 模型决定是否查询
                         → 工具读取已登记的本地资料 → 模型回答
```

入口只提供当前商品名称。资料全文在工具查询成功后作为工具结果交给模型；后续可以复用会话中的查询结果。聊天历史保留用户消息、模型的工具调用、工具结果和最终回复，失败的轮次不写入历史。

资料查询工具只读取已登记文件，未知游戏或不可用文件会返回明确状态。资料虽不提交 Git，但工具返回的内容会发送给 DeepSeek。此阶段没有 MCP、向量检索、真实订单查询、发货或退款操作。

当前会话仅保存在内存中，关闭或退出后不保留。尚未实现长对话裁剪、自动资料刷新和持久化；资料更新后可清空会话再查询。模型可能回答错误，工具约束和提示词不等于事实正确性的保证。

## 验证与学习示例

```powershell
# 离线测试，不调用 DeepSeek。
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -v

# 检查本地配置，不调用 DeepSeek。
.\.venv\Scripts\python.exe -X utf8 -m app.config

# 普通问答学习示例，不自动查询商品资料。
.\.venv\Scripts\python.exe -X utf8 -m examples.model_call
```

客服基础阶段完成时，13 项离线测试通过，覆盖上下文、工具查询、失败处理、会话清空与隔离、菜单跳转；已通过真实 DeepSeek 请求验证菜单进入客服、查询资料回答及返回菜单。

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
