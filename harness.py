"""
Agent Harness 核心引擎 —— 迷你版 Claude Code 架构实现

这是整个 Agent 框架的核心，实现了：
1. Agentic Loop（代理循环）：gather context → take action → verify results
2. Context Management（上下文管理）：自动压缩、token 预算分配
3. Tool Registry（工具注册表）：统一管理所有可用工具
4. Subagent Spawning（子代理生成）：独立上下文的任务委派
5. Session Checkpointing（会话检查点）：可回滚的状态管理

学习重点：理解 harness 层如何将 LLM 变成一个能自主完成任务的 Agent。
"""
import copy
import json
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from openai import OpenAI

# ============================================================
# 第一部分：工具系统 (Tool System)
# ============================================================

class ToolCategory(Enum):
    """工具类别 —— 对应 Claude Code 的五大工具类型"""
    FILE_OPERATION = "file_operation"    # 文件操作
    SEARCH = "search"                    # 搜索
    EXECUTION = "execution"              # 命令执行
    WEB = "web"                          # 网络访问
    CODE_INTELLIGENCE = "code_intel"     # 代码智能
    AGENT = "agent"                      # 子代理生成


@dataclass
class ToolDefinition:
    """工具定义 —— 类似 Claude Code 的 tool schema

    面试关键点：工具定义的质量直接决定 Agent 的可靠性。
    Anthropic 的经验是："优化工具花的时间比优化 prompt 还多"
    """
    name: str
    description: str
    category: ToolCategory
    parameters: dict          # JSON Schema 格式的参数定义
    handler: Callable          # 实际执行的函数
    cost_tokens: int = 0      # 工具输出的预估 token 消耗（用于上下文预算）

    def to_openai_format(self) -> dict:
        """转换为 OpenAI function calling 格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }


class ToolRegistry:
    """工具注册表 —— 统一管理所有工具

    设计要点：
    1. 工具按类别分组，便于权限控制
    2. 每个工具有 cost_tokens 预估，用于上下文预算管理
    3. 支持动态注册和注销
    """

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition):
        """注册工具"""
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        """获取工具"""
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        """列出所有工具"""
        return list(self._tools.values())

    def list_by_category(self, category: ToolCategory) -> list[ToolDefinition]:
        """按类别列出工具"""
        return [t for t in self._tools.values() if t.category == category]

    def to_openai_tools(self) -> list[dict]:
        """转换为 OpenAI API 格式"""
        return [t.to_openai_format() for t in self._tools.values()]

    def execute(self, name: str, arguments: dict) -> str:
        """执行工具调用"""
        tool = self.get(name)
        if tool is None:
            return f"Error: Tool '{name}' not found"
        try:
            result = tool.handler(**arguments)
            return str(result) if result is not None else ""
        except Exception as e:
            return f"Error executing {name}: {str(e)}"


# ============================================================
# 第二部分：上下文管理 (Context Management)
# ============================================================

@dataclass
class ContextMessage:
    """上下文消息"""
    role: str           # system / user / assistant / tool
    content: str
    tool_call_id: str | None = None
    tool_calls: list | None = None
    timestamp: float = field(default_factory=time.time)


class ContextManager:
    """上下文管理器 —— Agent 的核心约束

    面试关键点：Claude Code 的最佳实践文档说 "context window 是最重要的资源"

    核心策略（直接对应 Claude Code 的实现）：
    1. Token 预算分配：系统提示 + 工具定义 + 对话历史 + 文件内容
    2. 自动压缩 (Auto-compact)：接近上限时自动总结
    3. 工具输出截断：大输出只保留摘要
    4. 子代理隔离：高消耗操作委派给子代理

    修复(Q47): 原压缩用截断前100字符，现改为调用 LLM 生成语义摘要
    修复(Q48): token 估算改进，可选使用 tiktoken 精确计算
    """

    def __init__(self, max_tokens: int = 128000, compact_threshold: float = 0.8,
                 llm_client=None, llm_model: str = ""):
        self.max_tokens = max_tokens
        self.compact_threshold = compact_threshold  # 80% 时触发压缩
        self.llm_client = llm_client  # 用于 LLM 摘要压缩（Q47）
        self.llm_model = llm_model    # 压缩时使用的模型名（Q67: 不再硬编码）
        self.messages: list[ContextMessage] = []
        self._token_estimate = 0
        # 尝试加载 tiktoken 做精确 token 计算（Q48）
        self._tokenizer = None
        try:
            import tiktoken
            self._tokenizer = tiktoken.get_encoding("cl100k_base")
        except (ImportError, Exception):
            pass  # tiktoken 不可用时回退到估算

    def add_message(self, msg: ContextMessage):
        """添加消息并更新 token 估计"""
        self.messages.append(msg)
        self._token_estimate += self._estimate_tokens(msg.content)

        # 检查是否需要压缩
        if self._token_estimate > self.max_tokens * self.compact_threshold:
            self._compact()

    def _estimate_tokens(self, text: str) -> int:
        """估算 token 数

        修复(Q48): 优先使用 tiktoken 精确计算，回退到字符估算
        """
        if self._tokenizer is not None:
            return len(self._tokenizer.encode(text))
        # 回退估算: 中文约1字=1.5token，英文约4字符=1token
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        return int(chinese_chars * 1.5 + other_chars / 4)

    def _compact(self):
        """上下文压缩 —— Claude Code 的核心机制

        修复(Q47): 原实现截取每条消息前80-100字符，丢失语义
        现改为: 有 LLM 时用 LLM 生成摘要；无 LLM 时回退到截断

        策略（对应 Claude Code 的 auto-compaction）：
        1. 保留系统消息和最近的几轮对话
        2. 将中间历史总结为摘要
        3. 保留关键的代码片段和决策
        """
        if len(self.messages) <= 6:
            return

        # 保留第一条 system 消息（初始系统提示）+ 最近6条消息
        # 修复(Q68): 原实现保留所有 system 消息，导致压缩摘要不断累积
        # 现在只保留第一条 system（初始提示），之前的压缩摘要纳入 old_msgs 重新压缩
        first_system = [self.messages[0]] if self.messages[0].role == "system" else []
        recent_msgs = self.messages[-6:]
        old_msgs = self.messages[len(first_system):-6]

        if not old_msgs:
            return

        # 尝试用 LLM 生成语义摘要（Q47），回退到截断式压缩
        summary = self._llm_compact(old_msgs) if self.llm_client is not None else self._truncate_compact(old_msgs)

        # 重建消息列表
        self.messages = first_system + [
            ContextMessage(role="system", content=summary)
        ] + recent_msgs

        # 重新计算 token
        self._token_estimate = sum(self._estimate_tokens(m.content) for m in self.messages)

    def _llm_compact(self, old_msgs: list[ContextMessage]) -> str:
        """用 LLM 生成语义摘要（Q47: 替代原截断式压缩）"""
        # 构建压缩 prompt
        history_text = []
        for msg in old_msgs:
            role_label = {"user": "用户", "assistant": "助手",
                         "tool": "工具结果", "system": "系统"}.get(msg.role, msg.role)
            # 工具输出截断到500字符，避免压缩prompt本身过长
            content = msg.content[:500] if len(msg.content) > 500 else msg.content
            history_text.append(f"[{role_label}] {content}")

        compact_prompt = f"""请将以下对话历史压缩为简洁的摘要。
重点保留：
1. 用户的原始请求和目标
2. 已做出的关键决策和修改
3. 修改过的文件列表
4. 遇到的问题和解决方案
5. 当前任务状态

丢弃：
1. 具体的文件内容（只保留文件名和修改摘要）
2. 详细的工具输出日志
3. 冗余的中间推理过程

对话历史：
{chr(10).join(history_text)}

摘要："""
        try:
            response = self.llm_client.chat.completions.create(
                model=self.llm_model or "deepseek-chat",
                messages=[{"role": "user", "content": compact_prompt}],
                max_tokens=1000,
                temperature=0.0,
            )
            summary = response.choices[0].message.content or ""
            return "=== 上下文压缩摘要 (LLM生成) ===\n" + summary
        except Exception as e:
            # LLM 压缩失败，回退到截断
            print(f"  ⚠️ LLM 压缩失败，回退到截断: {e}")
            return self._truncate_compact(old_msgs)

    def _truncate_compact(self, old_msgs: list[ContextMessage]) -> str:
        """截断式压缩（回退方案，Q47: 保留比原来更多的信息）"""
        summary_parts = []
        for msg in old_msgs:
            if msg.role == "user":
                summary_parts.append(f"[用户请求] {msg.content[:200]}")
            elif msg.role == "assistant":
                summary_parts.append(f"[助手响应] {msg.content[:200]}")
            elif msg.role == "tool":
                summary_parts.append(f"[工具结果] {msg.content[:150]}")
        return "=== 上下文压缩摘要 ===\n" + "\n".join(summary_parts)

    def to_openai_messages(self) -> list[dict]:
        """转换为 OpenAI API 格式"""
        result = []
        for msg in self.messages:
            entry = {"role": msg.role, "content": msg.content}
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            if msg.tool_calls:
                entry["tool_calls"] = msg.tool_calls
            result.append(entry)
        return result

    def get_usage(self) -> dict:
        """获取上下文使用情况"""
        return {
            "current_tokens": self._token_estimate,
            "max_tokens": self.max_tokens,
            "usage_pct": round(self._token_estimate / self.max_tokens * 100, 1),
            "message_count": len(self.messages),
        }


# ============================================================
# 第三部分：会话检查点 (Session Checkpointing)
# ============================================================

@dataclass
class Checkpoint:
    """检查点 —— 对应 Claude Code 的 rewind 功能

    面试关键点：Claude Code 在每次文件编辑前自动快照，
    用户可以 Esc+Esc 回滚到任意检查点。
    """
    checkpoint_id: str
    timestamp: float
    context_snapshot: list[ContextMessage]
    file_changes: dict[str, str]  # filepath -> 原始内容
    description: str = ""


class CheckpointManager:
    """检查点管理器"""

    def __init__(self):
        self._checkpoints: list[Checkpoint] = []
        self._file_snapshots: dict[str, str] = {}  # 文件编辑前的快照

    def save_checkpoint(self, context: ContextManager, description: str = ""):
        """保存检查点"""
        # 修复(Q58): 用 UUID4 替代 md5(time)，避免碰撞且语义清晰
        cp_id = uuid.uuid4().hex[:8]
        cp = Checkpoint(
            checkpoint_id=cp_id,
            timestamp=time.time(),
            context_snapshot=copy.deepcopy(context.messages),
            file_changes=copy.deepcopy(self._file_snapshots),
            description=description,
        )
        self._checkpoints.append(cp)
        return cp_id

    def snapshot_file(self, filepath: str):
        """在文件编辑前快照（用于回滚）"""
        if filepath not in self._file_snapshots:
            if os.path.exists(filepath):
                with open(filepath, encoding="utf-8") as f:
                    self._file_snapshots[filepath] = f.read()
            else:
                self._file_snapshots[filepath] = None  # 标记文件原本不存在

    def rewind(self, checkpoint_id: str, context: ContextManager) -> bool:
        """回滚到指定检查点"""
        for cp in self._checkpoints:
            if cp.checkpoint_id == checkpoint_id:
                # 恢复上下文
                context.messages = copy.deepcopy(cp.context_snapshot)
                context._token_estimate = sum(
                    context._estimate_tokens(m.content) for m in context.messages
                )
                # 恢复文件
                for filepath, original_content in cp.file_changes.items():
                    if original_content is None:
                        if os.path.exists(filepath):
                            os.remove(filepath)
                    else:
                        with open(filepath, "w", encoding="utf-8") as f:
                            f.write(original_content)
                return True
        return False

    def list_checkpoints(self) -> list[dict]:
        """列出所有检查点"""
        return [
            {
                "id": cp.checkpoint_id,
                "time": time.strftime("%H:%M:%S", time.localtime(cp.timestamp)),
                "desc": cp.description,
            }
            for cp in self._checkpoints
        ]


# ============================================================
# 第四部分：子代理系统 (Subagent System)
# ============================================================

@dataclass
class SubagentConfig:
    """子代理配置 —— 对应 Claude Code 的 subagent 定义

    面试关键点：子代理在独立上下文中运行，只返回摘要给主对话。
    这是管理上下文窗口最强大的工具之一。
    """
    name: str
    description: str        # 何时委派给此子代理
    system_prompt: str
    tools: list[str]        # 允许使用的工具名列表（空=继承全部）
    model: str = ""         # 模型选择（空=继承主会话）


class SubagentManager:
    """子代理管理器"""

    def __init__(self, registry: ToolRegistry, default_model: str = ""):
        self.registry = registry
        self.default_model = default_model  # Q67: 不再硬编码 fallback 模型
        self._subagent_configs: dict[str, SubagentConfig] = {}

    def register(self, config: SubagentConfig):
        """注册子代理类型"""
        self._subagent_configs[config.name] = config

    def spawn(self, config_name: str, task: str, llm_client,
              parent_context: ContextManager, max_iterations: int = 10) -> str:
        """生成子代理执行任务

        修复(Q52/Q55): 原实现只跑一轮 LLM 推理，工具调用未执行
        现在实现完整的 agentic loop，子代理可多次调用工具直到任务完成

        关键设计：
        1. 子代理有独立的 ContextManager（隔离上下文）
        2. 只能使用配置中允许的工具
        3. 执行完毕后只返回摘要给主会话
        4. 有独立的 max_iterations 防止死循环
        """
        config = self._subagent_configs.get(config_name)
        if config is None:
            return f"Error: Subagent '{config_name}' not found"

        # 创建子代理的独立上下文
        # 修复(Q53): 子代理上下文预算独立配置，不继承父的 max_tokens
        sub_max_tokens = min(parent_context.max_tokens, 64000)  # 子代理用更小的窗口
        sub_context = ContextManager(max_tokens=sub_max_tokens)
        sub_context.add_message(ContextMessage(
            role="system",
            content=config.system_prompt
        ))
        sub_context.add_message(ContextMessage(
            role="user",
            content=task
        ))

        # 创建受限工具注册表
        sub_registry = ToolRegistry()
        if config.tools:
            for tool_name in config.tools:
                tool = self.registry.get(tool_name)
                if tool:
                    sub_registry.register(tool)
        else:
            sub_registry = self.registry  # 继承全部

        # 运行子代理的 agentic loop（修复Q52: 完整循环，不再只跑一轮）
        tools = sub_registry.to_openai_tools()
        model_name = config.model or self.default_model

        for _iteration in range(max_iterations):
            try:
                response = llm_client.chat.completions.create(
                    model=model_name,
                    messages=sub_context.to_openai_messages(),
                    tools=tools if tools else None,
                    max_tokens=4096,
                )
            except Exception as e:
                return f"子代理 LLM 调用失败: {e}"

            msg = response.choices[0].message

            # 没有工具调用 → 任务完成，返回最终结果
            if not msg.tool_calls:
                return msg.content or ""

            # 有工具调用 → 执行工具并继续循环
            sub_context.add_message(ContextMessage(
                role="assistant",
                content=msg.content or "",
                tool_calls=[
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    }
                    for tc in msg.tool_calls
                ]
            ))

            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    arguments = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}

                # 执行工具
                result = sub_registry.execute(tool_name, arguments)

                # 工具输出截断
                if len(result) > 2000:
                    result = result[:2000] + f"\n... [输出已截断，共{len(result)}字符]"

                sub_context.add_message(ContextMessage(
                    role="tool",
                    content=result,
                    tool_call_id=tc.id
                ))

        return f"子代理达到最大迭代次数 ({max_iterations})，最终结果可能不完整。"

    def list_configs(self) -> list[SubagentConfig]:
        return list(self._subagent_configs.values())


# ============================================================
# 第五部分：Agent Harness 核心 (The Agentic Loop)
# ============================================================

class AgentHarness:
    """Agent Harness —— Claude Code 架构的核心

    这是将 LLM 变成 Agent 的"外壳"，它提供：
    1. Agentic Loop（代理循环）
    2. 工具系统
    3. 上下文管理
    4. 子代理委派
    5. 检查点回滚

    面试关键概念："Agent = Model + Harness"
    - Model 负责推理
    - Harness 负责工具、上下文、执行环境
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "",
        model: str = "gpt-4o-mini",
        system_prompt: str = "",
        max_tokens: int = 128000,
        max_iterations: int = 20,
    ):
        self.llm = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
        self.model = model
        self.max_iterations = max_iterations

        # 核心组件
        # 修复(Q47): 传入 llm_client 使 ContextManager 可用 LLM 压缩
        # 修复(Q67): 传入 model 名，避免硬编码 fallback
        self.tool_registry = ToolRegistry()
        self.context = ContextManager(
            max_tokens=max_tokens,
            llm_client=self.llm,
            llm_model=model,
        )
        self.checkpoints = CheckpointManager()
        self.subagents = SubagentManager(self.tool_registry, default_model=model)

        # 系统提示
        self.system_prompt = system_prompt or self._default_system_prompt()
        self.context.add_message(ContextMessage(
            role="system",
            content=self.system_prompt
        ))

        # 统计
        self.stats = {
            "iterations": 0,
            "tool_calls": 0,
            "tokens_used": 0,
        }

    def _default_system_prompt(self) -> str:
        """默认系统提示"""
        return """你是一个能自主完成任务的 AI Agent。

工作方式：
1. 理解用户请求
2. 使用可用工具收集信息和执行操作
3. 验证结果
4. 迭代直到任务完成

规则：
- 每次只调用必要的工具
- 工具调用后检查结果是否成功
- 如果遇到错误，分析原因并尝试修复
- 任务完成后给出清晰的总结"""

    def register_tool(self, tool: ToolDefinition):
        """注册工具"""
        self.tool_registry.register(tool)

    def register_subagent(self, config: SubagentConfig):
        """注册子代理"""
        self.subagents.register(config)

    def _llm_call_with_retry(self, max_retries: int = 3, **kwargs) -> Any | None:
        """LLM 调用 + 指数退避重试（Q66: 防止 429/500 导致 Agent 崩溃）

        重试策略:
        - 429 (rate limit): 等待后重试
        - 500/502/503 (服务器错误): 指数退避重试
        - 其他错误: 不重试，直接返回 None
        """
        for attempt in range(max_retries):
            try:
                response = self.llm.chat.completions.create(**kwargs)
                return response
            except Exception as e:
                error_str = str(e).lower()
                # 判断是否为可重试的错误（rate limit 或服务器错误）
                is_retryable = any(code in error_str for code in
                                   ["429", "500", "502", "503", "timeout", "connection"])
                if not is_retryable or attempt == max_retries - 1:
                    print(f"  ❌ LLM 调用失败 (不可重试或已达最大重试): {e}")
                    return None

                # 指数退避: 2^attempt 秒
                wait_time = 2 ** attempt
                print(f"  ⚠️ LLM 调用失败，{wait_time}秒后重试 ({attempt+1}/{max_retries}): {e}")
                time.sleep(wait_time)
        return None

    def run(self, user_input: str) -> str:
        """运行 Agentic Loop —— 核心方法

        流程（对应 Claude Code 的 agentic loop）：

        用户输入
           ↓
        ┌──────────────────────────┐
        │ 1. LLM 推理（决定下一步）  │ ←──┐
        │ 2. 如果有 tool_call:      │    │
        │    - 执行工具             │    │
        │    - 结果加入上下文        │    │
        │ 3. 如果没有 tool_call:    │    │
        │    - 任务完成，返回结果    │    │
        │ 4. 否则回到步骤1          │ ───┘
        └──────────────────────────┘
        """
        # 添加用户输入
        self.context.add_message(ContextMessage(
            role="user",
            content=user_input
        ))

        # 保存检查点
        cp_id = self.checkpoints.save_checkpoint(
            self.context,
            f"Before processing: {user_input[:50]}"
        )

        # Agentic Loop
        for _iteration in range(self.max_iterations):
            self.stats["iterations"] += 1

            # 1. LLM 推理（修复Q66: 添加指数退避重试）
            tools = self.tool_registry.to_openai_tools()
            response = self._llm_call_with_retry(
                model=self.model,
                messages=self.context.to_openai_messages(),
                tools=tools if tools else None,
                max_tokens=4096,
            )
            if response is None:
                return "⚠️ LLM 调用失败，已重试多次仍无法恢复。"

            msg = response.choices[0].message
            self.stats["tokens_used"] += response.usage.total_tokens

            # 2. 检查是否有工具调用
            if msg.tool_calls:
                # 添加助手消息（包含 tool_calls）
                self.context.add_message(ContextMessage(
                    role="assistant",
                    content=msg.content or "",
                    tool_calls=[
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            }
                        }
                        for tc in msg.tool_calls
                    ]
                ))

                # 3. 执行每个工具调用
                for tc in msg.tool_calls:
                    self.stats["tool_calls"] += 1
                    tool_name = tc.function.name
                    arguments = json.loads(tc.function.arguments)

                    print(f"  🔧 调用工具: {tool_name}({arguments})")

                    # 文件编辑前快照
                    if "file" in tool_name and "path" in arguments:
                        self.checkpoints.snapshot_file(arguments["path"])

                    # 执行工具
                    result = self.tool_registry.execute(tool_name, arguments)

                    # 截断过长的工具输出（上下文管理）
                    if len(result) > 2000:
                        result = result[:2000] + f"\n... [输出已截断，共{len(result)}字符]"

                    # 工具结果加入上下文
                    self.context.add_message(ContextMessage(
                        role="tool",
                        content=result,
                        tool_call_id=tc.id
                    ))

                # 继续循环
                continue

            # 4. 没有工具调用 → 任务完成
            self.context.add_message(ContextMessage(
                role="assistant",
                content=msg.content or ""
            ))

            print(f"\n📊 本次运行统计: {self.get_stats()}")
            print(f"📌 检查点已保存: {cp_id}")

            return msg.content or ""

        # 超过最大迭代次数
        return f"⚠️ 已达到最大迭代次数 ({self.max_iterations})，任务可能未完成。"

    def rewind(self, checkpoint_id: str) -> bool:
        """回滚到检查点"""
        return self.checkpoints.rewind(checkpoint_id, self.context)

    def get_stats(self) -> dict:
        """获取运行统计"""
        stats = self.stats.copy()
        stats["context_usage"] = self.context.get_usage()
        return stats

    def get_context_usage(self) -> dict:
        """获取上下文使用情况"""
        return self.context.get_usage()


# ============================================================
# 使用示例
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("🤖 Agent Harness —— 迷你版 Claude Code 架构")
    print("=" * 60)

    # 这里只是展示架构，实际使用需要配置 API
    print("""
架构组件：
1. ToolRegistry     - 工具注册表（统一管理所有工具）
2. ContextManager   - 上下文管理器（token预算 + 自动压缩）
3. CheckpointManager - 检查点管理器（可回滚的状态管理）
4. SubagentManager  - 子代理管理器（独立上下文的任务委派）
5. AgentHarness     - 核心 Harness（编排以上组件的 Agentic Loop）

运行方式：
  from harness import AgentHarness, ToolDefinition, ToolCategory

  agent = AgentHarness(api_key="your-key", base_url="your-url")
  agent.register_tool(my_tool)
  result = agent.run("帮我读取 config.py 并分析代码结构")
""")
