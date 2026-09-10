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
