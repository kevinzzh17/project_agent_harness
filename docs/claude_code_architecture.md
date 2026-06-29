# Claude Code 架构分析

> 本文基于 Claude Code 官方文档和源码泄露信息整理，分析其 Harness 层架构设计。

## 一、整体架构

Claude Code 是 Anthropic 推出的 AI 编程助手，其核心是一个包裹在 LLM 外层的 **Harness（驾驭框架）**，将"只会生成文本"的模型变成"能自主完成编程任务的智能体"。

```
┌─────────────────────────────────────────────────────────┐
│                  Claude Code 整体架构                      │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  用户终端输入                                              │
│       ↓                                                 │
│  ┌──────────────────────────────────────────────────┐  │
│  │            Agentic Loop（核心循环）                │  │
│  │  Gather → Think → Act → Verify → (循环)           │  │
│  └──────────────────────────────────────────────────┘  │
│       ↓                                                 │
│  ┌──────────────────────────────────────────────────┐  │
│  │              支撑层 (Supporting Layer)             │  │
│  │  Tool System | Context Management | Subagent      │  │
│  │  Skill System | Checkpoint | Permission | MCP     │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## 二、核心组件详解

### 2.1 Agentic Loop

Claude Code 的核心是一个 `while True` 循环：

1. **Gather**：收集当前上下文（对话历史 + 工具结果 + 系统提示）
2. **Think**：LLM 推理，决定下一步操作（调用工具 or 回复用户）
3. **Act**：执行工具调用（读文件、写文件、运行命令等）
4. **Verify**：检查工具执行结果，决定是否继续循环

**终止条件**：
- LLM 主动停止（认为任务完成）
- 达到最大迭代次数
- 用户手动中断（Esc）
- 超时

### 2.2 Tool System（工具系统）

Claude Code 的五大工具类别：

| 类别 | 代表工具 | 说明 |
|------|----------|------|
| 文件操作 | read_file, write_file, edit_file | 读写编辑文件 |
| 搜索 | grep_search, find_files | 代码/文件搜索 |
| 执行 | run_command | 执行 shell 命令 |
| Web | web_search, fetch_url | 网络访问 |
| 代码智能 | analyze_code | AST 分析、结构提取 |

**ACI（Agent-Computer Interface）设计原则**：
- 工具描述要像写给初级开发者的文档
- 参数用 JSON Schema 精确定义
- 工具输出要有截断机制（防止上下文爆炸）
- Anthropic 经验：优化工具花的时间比优化 prompt 还多

### 2.3 Context Management（上下文管理）

**核心原则**：上下文窗口是最重要的资源。

**Compaction（压缩）策略**：
- 当 token 使用量达到 80% 阈值时自动触发
- 保留：系统指令、最近 N 轮对话、关键决策、修改的文件列表
- 丢弃：具体文件内容、详细工具日志、冗余推理
- 用 LLM 对早期对话生成摘要

**Token 预算分配**：
```
128K 总预算
├── 系统提示 + CLAUDE.md     ~5K
├── 工具定义                  ~3K
├── 对话历史                  ~80K（会压缩）
├── 文件内容（工具输出）       ~30K
└── 预留空间                  ~10K
```

### 2.4 Subagent（子代理）

**核心思想**：独立 context window，只回传摘要。

```
主对话 Context（精简）
├── 用户请求 + 关键决策
├── → Subagent A（独立 context，读了 50 个文件）
│      └── 返回摘要："发现 3 个相关模块"
├── → Subagent B（独立 context，运行了测试）
│      └── 返回摘要："3 个测试失败"
└── 主对话继续，context 未被污染
```

**使用场景**：
- 代码库探索（会产生大量文件内容输出）
- 测试运行（会产生大量日志输出）
- 大规模搜索（结果可能很长）

### 2.5 Skill System（技能系统）

**Skill vs RAG vs CLAUDE.md**：

| 机制 | 加载时机 | 上下文成本 | 适用场景 |
|------|----------|-----------|----------|
| CLAUDE.md | 每次会话 | 固定消耗 | 通用项目规则 |
| RAG | 查询时检索 | 按需但不精确 | 大型知识库问答 |
| Skill | LLM 判断相关时 | 按需精确控制 | 特定工作流 |

**Skill 的工作方式**：
1. 平时只加载 Skill 的描述（"有一个叫 code-review 的技能"）
2. LLM 判断需要时，调用 `load_skill` 工具加载完整内容
3. Skill 内容注入上下文，指导 LLM 执行特定工作流

### 2.6 Checkpoint（检查点）

- 每次文件编辑前自动创建快照
- 用户可通过 `Esc+Esc` 回滚到任意检查点
- 与 git 的区别：Checkpoint 是对话级别的状态快照（包含上下文），git 是文件级别的版本控制

### 2.7 Permission System（权限系统）

分层权限控制：

| 模式 | 说明 |
|------|------|
| default | 每个危险操作都需要用户确认 |
| auto-edit | 文件编辑自动允许，命令执行仍需确认 |
| plan | 只读模式，不执行任何修改 |
| bypass | 全部自动允许（危险，不推荐） |

## 三、与本项目的关系

本项目的 `harness.py` 实现了上述架构的迷你版本：
- `AgentHarness` 类 = Agentic Loop
- `ToolRegistry` = Tool System
- `ContextManager` = Context Management（含压缩）
- `SubagentManager` = Subagent
- `CheckpointManager` = Checkpoint

`code_review_agent.py` 则是落地方案，展示了多 Agent 协同的 Orchestrator-Worker 模式。

## 四、参考资料

- [Claude Code Best Practices](https://code.claude.com/docs/en/best-practices)
- [How Claude Code Works](https://code.claude.com/docs/en/how-claude-code-works)
- [Claude Code Subagents](https://code.claude.com/docs/en/sub-agents)
- [Anthropic: Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)
