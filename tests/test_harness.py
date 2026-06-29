"""
Agent Harness 单元测试

覆盖：
- ToolRegistry 注册 / 执行 / 按类别筛选
- ContextManager 消息管理 / token 估算 / 压缩
- CheckpointManager 快照 / 回滚
- builtin_tools 文件读写 / 搜索
- code_review_agent Explorer / BugDetector 规则检测
"""
import os
import sys
import tempfile
import pytest

# 确保能导入项目模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import (
    ToolRegistry, ToolDefinition, ToolCategory,
    ContextManager, ContextMessage,
    CheckpointManager,
    SubagentConfig, SubagentManager,
)
from builtin_tools import create_default_registry
from code_review_agent import (
    ExplorerAgent, BugDetectorAgent, StyleCheckerAgent,
    CodeFile, LLMBackend,
)


# ============================================================
# ToolRegistry 测试
# ============================================================

class TestToolRegistry:
    def test_register_and_get(self):
        reg = ToolRegistry()
        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            category=ToolCategory.FILE_OPERATION,
            parameters={"type": "object", "properties": {}},
            handler=lambda: "ok",
        )
        reg.register(tool)
        assert reg.get("test_tool") is tool
        assert reg.get("nonexistent") is None

    def test_list_tools(self):
        reg = ToolRegistry()
        assert reg.list_tools() == []
        reg.register(ToolDefinition(
            name="t1", description="d", category=ToolCategory.SEARCH,
            parameters={}, handler=lambda: "",
        ))
        assert len(reg.list_tools()) == 1

    def test_list_by_category(self):
        reg = ToolRegistry()
        reg.register(ToolDefinition(
            name="t1", description="d", category=ToolCategory.SEARCH,
            parameters={}, handler=lambda: "",
        ))
        reg.register(ToolDefinition(
            name="t2", description="d", category=ToolCategory.EXECUTION,
            parameters={}, handler=lambda: "",
        ))
        assert len(reg.list_by_category(ToolCategory.SEARCH)) == 1
        assert len(reg.list_by_category(ToolCategory.EXECUTION)) == 1

    def test_execute(self):
        reg = ToolRegistry()
        reg.register(ToolDefinition(
            name="echo", description="d", category=ToolCategory.FILE_OPERATION,
            parameters={}, handler=lambda msg: f"echo:{msg}",
        ))
        assert reg.execute("echo", {"msg": "hello"}) == "echo:hello"

    def test_execute_not_found(self):
        reg = ToolRegistry()
        assert "not found" in reg.execute("nonexistent", {})

    def test_execute_exception(self):
        reg = ToolRegistry()
        def bad_handler(**kwargs):
            raise ValueError("boom")
        reg.register(ToolDefinition(
            name="bad", description="d", category=ToolCategory.FILE_OPERATION,
            parameters={}, handler=bad_handler,
        ))
        result = reg.execute("bad", {})
        assert "Error" in result

    def test_to_openai_format(self):
        reg = create_default_registry()
        tools = reg.to_openai_tools()
        assert isinstance(tools, list)
        assert all(t["type"] == "function" for t in tools)
        names = {t["function"]["name"] for t in tools}
        assert "read_file" in names
        assert "write_file" in names


# ============================================================
# ContextManager 测试
# ============================================================

class TestContextManager:
    def test_add_message(self):
        cm = ContextManager(max_tokens=10000)
        cm.add_message(ContextMessage(role="user", content="hello"))
        assert len(cm.messages) == 1
        assert cm._token_estimate > 0

    def test_token_estimate(self):
        cm = ContextManager(max_tokens=10000)
        assert cm._estimate_tokens("hello") > 0
        assert cm._estimate_tokens("你好世界") > 0

    def test_get_usage(self):
        cm = ContextManager(max_tokens=10000)
        cm.add_message(ContextMessage(role="user", content="test"))
        usage = cm.get_usage()
        assert "current_tokens" in usage
        assert "max_tokens" in usage
        assert "usage_pct" in usage
        assert usage["max_tokens"] == 10000

    def test_to_openai_messages(self):
        cm = ContextManager(max_tokens=10000)
        cm.add_message(ContextMessage(role="system", content="sys"))
        cm.add_message(ContextMessage(role="user", content="hi"))
        msgs = cm.to_openai_messages()
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"

    def test_compact_triggers(self):
        """当 token 超过阈值时应触发压缩"""
        cm = ContextManager(max_tokens=100, compact_threshold=0.5)
        # 添加足够多的消息触发压缩
        for i in range(20):
            cm.add_message(ContextMessage(role="user", content=f"message {i} " * 20))
        # 压缩后消息数应减少
        assert len(cm.messages) < 20


# ============================================================
# CheckpointManager 测试
# ============================================================

class TestCheckpointManager:
    def test_save_and_list(self):
        cm = ContextManager(max_tokens=10000)
        cm.add_message(ContextMessage(role="user", content="test"))
        mgr = CheckpointManager()
        cp_id = mgr.save_checkpoint(cm, "test checkpoint")
        assert cp_id is not None
        cps = mgr.list_checkpoints()
        assert len(cps) == 1
        assert cps[0]["id"] == cp_id

    def test_rewind(self):
        cm = ContextManager(max_tokens=10000)
        cm.add_message(ContextMessage(role="user", content="original"))
        mgr = CheckpointManager()
        cp_id = mgr.save_checkpoint(cm, "before change")
        cm.add_message(ContextMessage(role="user", content="added later"))
        assert len(cm.messages) == 2
        assert mgr.rewind(cp_id, cm) is True
        assert len(cm.messages) == 1

    def test_rewind_nonexistent(self):
        cm = ContextManager(max_tokens=10000)
        mgr = CheckpointManager()
        assert mgr.rewind("nonexistent", cm) is False


# ============================================================
# builtin_tools 测试
# ============================================================

class TestBuiltinTools:
    def test_read_file(self):
        reg = create_default_registry()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("hello world")
            f.flush()
            result = reg.execute("read_file", {"path": f.name})
        os.unlink(f.name)
        assert "hello world" in result

    def test_read_file_not_found(self):
        reg = create_default_registry()
        result = reg.execute("read_file", {"path": "/nonexistent/file.txt"})
        assert "Error" in result or "not found" in result

    def test_write_and_read(self):
        reg = create_default_registry()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "test.txt")
            reg.execute("write_file", {"path": path, "content": "test content"})
            result = reg.execute("read_file", {"path": path})
            assert "test content" in result

    def test_list_directory(self):
        reg = create_default_registry()
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "subdir"))
            with open(os.path.join(d, "file.txt"), "w") as f:
                f.write("x")
            result = reg.execute("list_directory", {"path": d})
            assert "subdir" in result
            assert "file.txt" in result

    def test_edit_file(self):
        reg = create_default_registry()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("line one\nline two\nline three")
            f.flush()
            path = f.name
        try:
            reg.execute("edit_file", {"path": path, "old_text": "line two", "new_text": "LINE TWO"})
            result = reg.execute("read_file", {"path": path})
            assert "LINE TWO" in result
        finally:
            os.unlink(path)


# ============================================================
# code_review_agent 测试
# ============================================================

class TestExplorerAgent:
    def test_explore_sample_project(self):
        explorer = ExplorerAgent(verbose=False)
        sample = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sample_project")
        files = explorer.explore(sample)
        assert len(files) >= 3
        names = {f.path for f in files}
        assert "calculator.py" in names
        assert "data_processor.py" in names
        assert "user_manager.py" in names

    def test_structure_summary(self):
        explorer = ExplorerAgent(verbose=False)
        cf = CodeFile(path="test.py", lines=5, content="def foo(a):\n    return a\n")
        import ast as _ast
        cf.tree = _ast.parse(cf.content)
        summary = explorer.get_structure_summary(cf)
        assert "foo" in summary


class TestBugDetectorAgent:
    def test_detect_pickle_load(self):
        """BugDetector 应检测出 pickle.load 安全风险"""
        import ast as _ast
        llm = LLMBackend(verbose=False)
        detector = BugDetectorAgent(llm, verbose=False)
        content = 'import pickle\npickle.load(open("x", "rb"))\n'
        cf = CodeFile(path="test.py", lines=2, content=content)
        cf.tree = _ast.parse(content)
        result = detector.review(cf, "")
        has_pickle_issue = any("pickle" in i.message.lower() for i in result.issues)
        assert has_pickle_issue

    def test_detect_eq_none(self):
        """BugDetector 应检测出 == None"""
        import ast as _ast
        llm = LLMBackend(verbose=False)
        detector = BugDetectorAgent(llm, verbose=False)
        content = 'x = 1\nif x == None:\n    pass\n'
        cf = CodeFile(path="test.py", lines=3, content=content)
        cf.tree = _ast.parse(content)
        result = detector.review(cf, "")
        has_none_issue = any("none" in i.message.lower() for i in result.issues)
        assert has_none_issue


class TestStyleCheckerAgent:
    def test_detect_bad_class_name(self):
        """StyleChecker 应检测出不合规类名"""
        import ast as _ast
        checker = StyleCheckerAgent(verbose=False)
        content = "class myClass:\n    pass\n"
        cf = CodeFile(path="test.py", lines=2, content=content)
        cf.tree = _ast.parse(content)
        result = checker.review(cf)
        assert len(result.issues) > 0

    def test_clean_code_passes(self):
        """规范代码不应有问题"""
        import ast as _ast
        checker = StyleCheckerAgent(verbose=False)
        content = "def my_func(a, b):\n    return a + b\n"
        cf = CodeFile(path="test.py", lines=2, content=content)
        cf.tree = _ast.parse(content)
        result = checker.review(cf)
        assert len(result.issues) == 0
