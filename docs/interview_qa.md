# 面试问答

> 针对 Agent Harness 架构设计的高频面试题整理，含本项目代码参考。

---

## Q1: Claude Code 的 Harness 层架构是怎样的？

**答**：Claude Code 的 Harness 层是一个围绕 LLM 构建的工程系统，核心是 **Agentic Loop**（Gather→Think→Act→Verify 循环）。支持层包括：

1. **工具系统**：5 类工具（文件操作、搜索、执行、Web、代码智能）
2. **上下文管理**：自动压缩（compaction），保留关键信息丢弃冗余
3. **Subagent**：独立 context window，隔离大量输出，只回传摘要
4. **Skill 系统**：按需加载的领域知识，类似"插件"
5. **Checkpoint**：每次编辑前快照，支持回滚
6. **权限系统**：分层权限（default/auto/plan/bypass）

关键设计理念：**上下文窗口是最重要的资源**，所有设计都围绕"高效利用上下文"展开。

> 📁 **本项目参考**：`harness.py` 中的 `AgentHarness` 类实现了 Agentic Loop，`ToolRegistry` 实现了工具系统，`ContextManager` 实现了上下文管理。

---

## Q2: 上下文压缩怎么实现？保留什么丢弃什么？

**答**：

**保留**：
- 系统指令（CLAUDE.md 中的规则）
- 最近 N 轮对话原文（近期上下文最重要）
- 关键决策记录（用户请求、核心修改、任务状态）
- 修改过的文件列表

**丢弃**：
- 具体文件内容（只保留文件名和修改摘要）
- 详细的工具输出日志（只保留关键结论）
- 冗余的中间推理过程

**实现方式**：用 LLM 对早期对话生成摘要，注入为 system message，保留近期对话原文。当 token 使用量达到阈值（如 80%）时自动触发。

> 📁 **本项目参考**：`harness.py` 中的 `ContextManager._compact()` 方法实现了自动压缩策略。

---

## Q3: Subagent 和普通函数调用有什么区别？

| 维度 | 普通函数调用 | Subagent |
|------|-------------|----------|
| 上下文 | 共享主对话上下文 | 独立 context window |
| 输出 | 全部返回到主对话 | 只返回摘要 |
| 工具 | 使用主对话的工具集 | 有自己的工具集 |
| 模型 | 使用主对话的模型 | 可以用不同模型（如便宜模型） |
| 适用 | 简单、快速的单一操作 | 产生大量输出的复杂任务 |

**核心价值**：上下文隔离，防止大量输出"污染"主对话的上下文窗口。

> 📁 **本项目参考**：`harness.py` 中的 `SubagentManager` 实现了子代理管理；`code_review_agent.py` 中的 Explorer/BugDetector/StyleChecker 各自独立运行，只输出结构化结果。

---

## Q4: 设计一个代码审查多 Agent 系统，你的架构方案？

**答**：采用 **Orchestrator-Worker** 多 Agent 架构：

```
用户输入: python code_review_agent.py sample_project/
     → Orchestrator（主编排器）
          ├── Explorer Agent（AST 解析，提取类/函数/导入）
          ├── Bug Detector Agent（规则引擎 + LLM 推理）
          ├── Style Checker Agent（PEP8 命名/行长度/尾随空格）
          └── Report Generator Agent（汇总 → 写入 .md 报告文件）
```

**编排流程**：
1. **探索**：Explorer 用 AST 扫描代码库，提取结构化 FileInfo
2. **Bug 检测**：Bug Detector 先跑规则引擎（确定性），再用 LLM 分析语义级 Bug
3. **风格检查**：Style Checker 纯规则检查 PEP8
4. **报告生成**：Report Generator 合并所有 Issue，写入真实 .md 文件到磁盘

**关键设计点**：
- Explorer 和 Style Checker 用确定性工具（AST/规则），不依赖 LLM
- Bug Detector 用混合策略：规则抓确定性 Bug，LLM 抓语义级 Bug
- 每个 Agent 有独立上下文，只输出结构化数据（Issue 列表）
- LLM 后端自动降级：Ollama → DeepSeek → 智谱 → 离线规则模式
- 即使没有任何 LLM，规则引擎仍能发现 `== None`、`pickle.load`、命名违规等真实问题
- 最终产出是真实的 `.md` 报告文件，不是 `print` 假装成功

> 📁 **本项目参考**：`code_review_agent.py` 是完整的可运行实现，`sample_project/` 是含故意植入 Bug 的测试代码。

---

## Q5: Skill 系统和 RAG 有什么区别？

| 维度 | Skill | RAG |
|------|-------|-----|
| 触发方式 | LLM 主动判断 + 手动调用 | 查询时自动检索 |
| 内容类型 | 工作流、操作指南、领域规则 | 事实性知识、文档 |
| 精确度 | 高（人工编写，精确定义） | 依赖检索质量 |
| 上下文 | 整体注入（完整加载） | 只注入相关片段 |
| 适用 | "怎么做"类任务（操作流程） | "是什么"类查询（知识检索） |

**Skill 的优势**：可以定义完整的工作流（如"修复 GitHub issue 的 8 步流程"），RAG 只能提供信息片段。

---

## Q6: 如何防止 Agent 无限循环？

1. **最大迭代次数**：设置 `max_iterations` 硬限制
2. **终止条件**：检测特定关键词（如 "APPROVE"、"DONE"）
3. **超时机制**：设置最大运行时间
4. **重复检测**：检测是否重复执行相同操作
5. **成本限制**：设置最大 token 消耗
6. **人类介入**：Human-in-the-loop 检查点

> 📁 **本项目参考**：`harness.py` 中的 `AgentHarness.run()` 方法通过 `max_iterations` 参数控制循环次数。

---

## Q7: Claude Code 源码泄露事件说明了什么？

2026 年 4 月，Claude Code 的源码泄露，暴露了其内部实现细节。从中可以学到：

1. **Harness 本质很简单**：核心就是 `while True: LLM → tools → check` 循环
2. **复杂度在工具定义**：好的工具描述（ACI）比复杂的 prompt 更重要
3. **上下文管理是核心**：compaction、subagent、skill 都是为了管理上下文
4. **系统提示工程**：大量精心设计的系统提示控制 Agent 行为

---

## Q8: 为什么你的代码审查 Agent 用混合策略（规则 + LLM）而不是纯 LLM？

**答**：

| 维度 | 纯规则 | 纯 LLM | 混合策略（本项目） |
|------|--------|--------|-------------------|
| 确定性 Bug（== None） | ✅ 准确 | ✅ 能发现 | ✅ 规则优先 |
| 语义级 Bug（逻辑错误） | ❌ 无法发现 | ✅ 能发现 | ✅ LLM 补充 |
| 成本 | 零 | 高 | 低（规则免费，LLM 按需） |
| 速度 | 极快 | 慢 | 快（规则秒级，LLM 按需） |
| 可离线 | ✅ | ❌ | ✅ 离线仍可用规则 |
| 误报率 | 低 | 中 | 低 |

**设计哲学**：规则引擎处理"确定能确定的"，LLM 处理"需要推理的"。这样即使没有 LLM（离线模式），Agent 仍然能发现大量真实问题。

> 📁 **本项目参考**：`code_review_agent.py` 中 `BugDetectorAgent.review()` 方法先调 `_detect_by_rules()` 再调 `_detect_by_llm()`。

---

## Q9: 你的 Agent 系统如何做到"真实可运行"而不是"假装成功"？

**答**：三个关键设计：

1. **确定性工具产出真实数据**：Explorer Agent 用 Python 标准库 `ast` 解析代码，产出真实的类/函数/导入列表，不是模拟的。

2. **规则引擎发现真实 Bug**：Bug Detector 的规则引擎能真实检测 `== None`、`pickle.load`、命名违规等问题——你可以打开 `sample_project/` 验证这些问题确实存在。

3. **报告真实写入磁盘**：Report Generator 调用 `Path.write_text()` 将 Markdown 报告写入 `output/code_review_report.md`——你可以打开这个文件看到结构化的问题表格。

**验证方式**：
```bash
python code_review_agent.py sample_project/
# 检查 output/code_review_report.md 是否真实生成
# 检查报告中的问题是否对应 sample_project/ 中的真实代码
```
