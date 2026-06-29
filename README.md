# Agent Harness — Mini Claude Code 架构实现 & 多 Agent 代码审查系统

[![CI](https://github.com/your-username/agent-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/your-username/agent-harness/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

从零实现一个迷你版 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 的 **Agent Harness** 架构，包含 Agentic Loop、上下文压缩、Subagent 隔离、检查点回滚，并落地一个 **Orchestrator-Worker 多 Agent 协同的代码审查系统**，产出真实的 Markdown 审查报告。

> **这不是 demo 脚本**——规则引擎用 Python `ast` 模块做真实的静态分析，Report Generator 真实写入 `.md` 文件到磁盘。即使没有任何 LLM（离线模式），规则引擎仍然能检测 `== None`、`pickle.load` RCE、命名违规等真实问题。

---

## 目录

- [快速开始](#快速开始)
- [项目架构](#项目架构)
- [核心模块](#核心模块)
- [代码审查 Agent](#代码审查-agent)
- [工具系统](#工具系统)
- [LLM 后端配置](#llm-后端配置)
- [测试](#测试)
- [项目结构](#项目结构)
- [设计文档](#设计文档)
- [常见问题](#常见问题)
- [贡献](#贡献)
- [许可证](#许可证)

---

## 快速开始

### 环境要求

- Python ≥ 3.10
- 无需 GPU、无需 API Key 即可运行（离线规则模式）

### 安装

```bash
git clone <repo-url>
cd project4_agent_harness
pip install -r requirements.txt          # 最小依赖
# 或安装完整开发环境：
pip install -e ".[dev]"                   # 含 pytest, ruff, mypy
```

### 运行代码审查（零配置）

```bash
python code_review_agent.py sample_project/
```

输出：

```
📋 代码审查 Agent 启动
   LLM 后端: offline / rule-based

🤖 [Agent 1/4] Explorer Agent — 代码探索
  ✅ calculator.py (63 行)
  ✅ data_processor.py (63 行)
  ✅ user_manager.py (61 行)

🤖 [Agent 2/4] Bug Detector Agent — Bug 检测
🤖 [Agent 3/4] Style Checker Agent — 风格检查
  ✅ data_processor.py: 评分 80.2/100, 问题 1 个
  ✅ user_manager.py: 评分 90.2/100, 问题 2 个

🤖 [Agent 4/4] Report Generator Agent — 生成报告
  📝 报告已写入: sample_project/output/code_review_report.md

📊 综合评分: 90.1/100 | 问题总数: 3
```

审查报告 `output/code_review_report.md` 包含结构化的问题表格（行号、严重级别、类别、描述、修复建议）。

### 运行交互式 Agent（需 LLM API）

```bash
# 设置 API Key（任选其一）
set DEEPSEEK_API_KEY=sk-xxxx      # DeepSeek
set ZHIPUAI_API_KEY=xxxx          # 智谱 GLM
set OPENAI_API_KEY=sk-xxxx        # OpenAI

python main.py
```

交互模式支持命令：`/stats`（运行统计）、`/context`（上下文用量）、`/checkpoints`（检查点列表）、`/rewind <id>`（回滚）、`/clear`（清空上下文）、`/quit`（退出）。

---

## 项目架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent Harness 架构                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  用户输入                                                    │
│       ↓                                                     │
│  ┌──────────────────────────────────────────────────────┐  │
│  │            Agentic Loop（核心循环）                    │  │
│  │                                                      │  │
│  │  ┌──────────┐    ┌──────────┐    ┌──────────┐       │  │
│  │  │ 收集上下文 │ → │  LLM 推理 │ → │  执行工具 │       │  │
│  │  └──────────┘    └──────────┘    └────┬─────┘       │  │
│  │       ↑                             │              │  │
│  │       │       ┌──────────┐          │              │  │
│  │       └───────│ 验证结果  │←─────────┘              │  │
│  │               └──────────┘                         │  │
│  │                  (循环直到任务完成或终止)              │  │
│  └──────────────────────────────────────────────────────┘  │
│       ↓                                                     │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                 支撑层                                 │  │
│  │  ToolRegistry │ ContextManager │ CheckpointManager    │  │
│  │  SubagentManager (独立上下文子代理)                     │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**核心设计理念**：上下文窗口是最重要的资源。所有组件——压缩、子代理、工具输出截断——都围绕"高效利用上下文"展开。

---

## 核心模块

### `harness.py` — Agent Harness 引擎

| 类 | 职责 |
|---|---|
| `ToolRegistry` | 工具注册表，统一管理工具注册、按类别筛选、OpenAI 格式转换 |
| `ContextManager` | 上下文管理器：token 预算估算、自动压缩（LLM 摘要 / 截断回退） |
| `CheckpointManager` | 会话检查点：文件编辑前快照、上下文回滚 |
| `SubagentManager` | 子代理管理器：独立上下文的任务委派，结果隔离 |
| `AgentHarness` | 核心 Harness：编排以上组件的 Agentic Loop |

#### Agentic Loop

```
用户输入
   ↓
┌──────────────────────────┐
│ 1. LLM 推理（决定下一步）  │ ←──┐
│ 2. 有 tool_call:          │    │
│    - 执行工具              │    │
│    - 结果加入上下文         │    │
│ 3. 无 tool_call:          │    │
│    - 任务完成，返回结果     │    │
│ 4. 回到步骤 1             │ ───┘
└──────────────────────────┘
```

终止条件：LLM 主动停止 / 达到 `max_iterations` / LLM 调用失败。

#### 上下文压缩

当 token 使用量超过阈值（默认 80%）时自动触发压缩：

- **保留**：第一条 system 消息（初始系统提示）、最近 6 条对话
- **压缩**：将中间历史用 LLM 生成语义摘要（无 LLM 时回退到截断式摘要）
- **关键修复**：只保留第一条 system 消息，避免压缩摘要消息不断累积

```python
from harness import ContextManager, ContextMessage

cm = ContextManager(max_tokens=128000, llm_client=client, llm_model="deepseek-chat")
cm.add_message(ContextMessage(role="user", content="..."))
# token 超过 80% 时自动压缩
```

#### 检查点回滚

每次用户输入前自动保存上下文快照，文件编辑前自动快照文件内容：

```python
agent = AgentHarness(api_key="...", model="...")
result = agent.run("帮我修改 config.py")
# 回滚到之前的检查点
agent.rewind("checkpoint_id")
```

### `builtin_tools.py` — 内置工具注册

注册文件操作、搜索、命令执行、代码分析等工具。每个工具有 JSON Schema 参数定义和 token 消耗预估。

### `main.py` — 交互式入口

创建配置好的 `AgentHarness` 实例，注册内置工具和探索子代理，启动交互式对话循环。

---

## 代码审查 Agent

`code_review_agent.py` 是本项目的核心落地方案——采用 **Orchestrator-Worker** 多 Agent 架构审查 Python 代码。

### 架构

```
用户输入: python code_review_agent.py sample_project/
     ↓
┌──────────────────────────────────────────┐
│       CodeReviewOrchestrator              │
│  扫描项目 → 调度 Agent → 汇总报告          │
└──────┬──────────┬──────────┬─────────────┘
       ↓          ↓          ↓
┌──────────┐ ┌──────────┐ ┌──────────┐
│Explorer  │ │Bug       │ │Style     │
│Agent     │ │Detector  │ │Checker   │
│(AST)     │ │(规则+LLM)│ │(PEP8)    │
└──────────┘ └──────────┘ └──────────┘
       ↓          ↓          ↓
┌──────────────────────────────────────────┐
│       Report Generator Agent              │
│  合并所有 Issue → 写入 .md 报告到磁盘      │
└──────────────────────────────────────────┘
```

### 4 个 Agent 的职责

| Agent | 检测手段 | 依赖 LLM | 说明 |
|-------|---------|---------|------|
| **Explorer** | Python `ast` 模块 | ❌ | 扫描 `.py` 文件，提取类/函数/导入结构 |
| **Bug Detector** | AST 规则 + LLM 语义分析 | 可选 | 规则抓确定性 Bug（`==None`、`pickle.load`、`eval`），LLM 抓逻辑 Bug |
| **Style Checker** | 纯规则 | ❌ | PEP 8 命名规范、行长度、尾随空格 |
| **Report Generator** | 模板渲染 | ❌ | 汇总所有 Issue，写入 Markdown 报告文件 |

### 规则引擎检测项

| 检测项 | 严重级别 | 类别 |
|--------|---------|------|
| `pickle.load` / `pickle.loads`（RCE 风险） | 🔴 critical | security |
| `eval()` / `exec()`（代码注入） | 🔴 critical | security |
| 裸 `except:`（捕获所有异常） | 🟡 warning | bug |
| `== None` / `!= None`（PEP 8 E711） | 🟡 warning | bug |
| 可变默认参数（`def f(x=[])`） | 🟡 warning | bug |
| `assert` 用于运行时校验 | ⚪ info | maintainability |
| 参数遮蔽内置名（`id`、`type`、`list`…） | 🟡 warning | bug |
| 类名不符合 PascalCase | 🔵 style | style |
| 函数/参数名不符合 snake_case | 🔵 style | style |
| 行长度超过 120 字符 | 🔵 style | style |
| 行尾多余空格 | ⚪ info | style |

### 混合策略的优势

| 维度 | 纯规则 | 纯 LLM | 混合策略（本项目） |
|------|--------|--------|-------------------|
| 确定性 Bug | ✅ 准确 | ✅ 能发现 | ✅ 规则优先 |
| 语义级 Bug | ❌ 无法发现 | ✅ 能发现 | ✅ LLM 补充 |
| 成本 | 零 | 高 | 低（规则免费，LLM 按需） |
| 可离线 | ✅ | ❌ | ✅ 离线仍可用规则 |

---

## 工具系统

`builtin_tools.py` 注册了以下工具：

| 工具名 | 类别 | 功能 |
|--------|------|------|
| `read_file` | FILE_OPERATION | 读取文件内容（自动截断过长文件） |
| `write_file` | FILE_OPERATION | 写入文件（自动创建目录） |
| `list_directory` | FILE_OPERATION | 列出目录内容 |
| `edit_file` | FILE_OPERATION | 精确文本替换（要求 old_text 唯一匹配） |
| `grep_search` | SEARCH | 在文件中搜索文本/正则 |
| `find_files` | SEARCH | 按通配符查找文件 |
| `run_command` | EXECUTION | 执行 shell 命令（含危险命令拦截） |
| `analyze_code` | CODE_INTELLIGENCE | 提取 Python 文件的类/函数/导入结构 |

### 安全机制

`run_command` 工具内置危险命令拦截，通过正则模式匹配 `rm -rf /`、`format`、`mkfs`、fork bomb、`curl | bash` 等危险操作。

> ⚠️ **注意**：黑名单方式无法覆盖所有攻击向量。生产环境中建议使用沙箱（如 Docker 容器）隔离命令执行，而非依赖黑名单。

---

## LLM 后端配置

`code_review_agent.py` 的 `LLMBackend` 按优先级自动检测可用后端：

| 优先级 | 后端 | 环境变量 | 说明 |
|--------|------|---------|------|
| 1 | Ollama | `OLLAMA_HOST`, `OLLAMA_MODEL` | 本地模型，完全免费 |
| 2 | DeepSeek | `DEEPSEEK_API_KEY` | OpenAI 兼容 API |
| 3 | 智谱 GLM | `ZHIPUAI_API_KEY` | OpenAI 兼容 API |
| 4 | 离线规则 | 无需配置 | 规则引擎仍正常运行 |

`main.py` 的交互式 Agent 使用 `PROVIDER` 变量选择后端，支持 `deepseek` / `zhipu` / `openai`，也可通过环境变量 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL` 覆盖。

---

## 测试

```bash
pytest tests/ -v
```

测试覆盖：

- **ToolRegistry**：注册、获取、按类别筛选、执行、异常处理、OpenAI 格式转换
- **ContextManager**：消息管理、token 估算、压缩触发
- **CheckpointManager**：保存、列表、回滚
- **builtin_tools**：文件读写、目录列表、编辑
- **ExplorerAgent**：项目扫描、AST 结构提取
- **BugDetectorAgent**：pickle 检测、`== None` 检测
- **StyleCheckerAgent**：命名规范检测、合规代码验证

---

## 项目结构

```
project4_agent_harness/
├── harness.py                   # Agent Harness 核心引擎
├── builtin_tools.py             # 内置工具注册
├── main.py                      # 交互式 Agent 入口
├── code_review_agent.py         # 多 Agent 代码审查系统
├── requirements.txt             # 最小依赖
├── pyproject.toml               # 项目配置（含 dev 依赖、ruff 配置）
├── LICENSE                      # MIT 许可证
├── CONTRIBUTING.md              # 贡献指南
├── .gitignore
├── .github/workflows/ci.yml     # GitHub Actions CI
├── tests/
│   └── test_harness.py          # 单元测试（26 个）
├── sample_project/              # 代码审查示例（含故意植入的 Bug，11 个文件）
│   ├── __init__.py              #   包描述文件
│   ├── calculator.py            #   除零、空列表、命名问题
│   ├── data_processor.py        #   pickle 安全风险、未处理异常
│   ├── user_manager.py          #   == None、参数遮蔽内置名
│   ├── security_issues.py       #   eval/exec/pickle RCE、弱哈希、命令注入、路径遍历
│   ├── logic_bugs.py            #   运算符优先级、浅拷贝、off-by-one、条件反转
│   ├── style_issues.py          #   命名规范、行长超限、尾随空格、== True
│   ├── network_bugs.py          #   无超时、无 SSL 验证、未关闭响应、异常吞没
│   ├── db_bugs.py               #   SQL 注入、连接泄漏、无事务、参数遮蔽
│   ├── error_handling.py        #   裸 except、异常吞没、assert 校验、== None
│   └── resource_leaks.py        #   文件句柄泄漏、锁未释放、可变默认参数
├── output/                      # 审查报告输出目录
│   └── .gitkeep
└── docs/
    ├── claude_code_architecture.md  # Claude Code 架构分析
    └── interview_qa.md              # 面试问答
```

---

## 设计文档

- [`docs/claude_code_architecture.md`](docs/claude_code_architecture.md) — Claude Code Harness 层架构分析（Agentic Loop、上下文管理、Subagent、Skill 系统、检查点、权限）
- [`docs/interview_qa.md`](docs/interview_qa.md) — Agent Harness 相关面试问答

---

## 常见问题

### 为什么没有 LLM 也能用？

代码审查的 Explorer Agent 和 Style Checker Agent 完全基于 Python `ast` 模块和规则引擎，不依赖 LLM。Bug Detector Agent 的规则检测部分也不依赖 LLM。只有 LLM 语义分析部分在离线模式下自动跳过。因此即使没有任何 API Key，运行 `python code_review_agent.py` 仍能得到真实的审查报告。

### 如何接入真实 LLM？

设置对应的环境变量即可。`code_review_agent.py` 会自动检测；`main.py` 通过 `PROVIDER` 变量选择后端。

### 上下文压缩是怎么工作的？

当 token 估算超过 `max_tokens` 的 80% 时触发：保留第一条 system 消息和最近 6 条对话，将中间历史用 LLM 生成语义摘要（无 LLM 时回退到截断式摘要）。压缩后重新计算 token 估计。

### Subagent 和普通函数调用有什么区别？

Subagent 在独立的 `ContextManager` 中运行，有自己的工具集和迭代限制，执行完毕后只返回最终结果给主对话——中间的工具调用和输出不会"污染"主对话的上下文窗口。

---

## 贡献

欢迎提交 Issue 和 Pull Request。请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

提交 PR 前请确保：

```bash
ruff check .          # lint 通过
pytest tests/ -v      # 测试通过
```

---

## 许可证

[MIT License](LICENSE)
