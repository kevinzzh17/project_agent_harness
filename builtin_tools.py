"""
内置工具注册 —— 创建并注册所有可用工具

对应 Claude Code 的工具系统设计原则：
1. 每个工具有清晰的 description（何时用、怎么用）
2. 参数用 JSON Schema 定义
3. 工具描述像写给初级开发者的文档
"""
import json
import os
import re
import subprocess

from harness import ToolCategory, ToolDefinition, ToolRegistry

# ============================================================
# 1. 文件操作工具 (File Operations)
# ============================================================

def _read_file(path: str) -> str:
    """读取文件内容"""
    if not os.path.exists(path):
        return f"Error: File not found: {path}"
    with open(path, encoding="utf-8") as f:
        content = f.read()
    # 截断过长文件
    if len(content) > 10000:
        content = content[:10000] + f"\n... [文件已截断，共{len(content)}字符]"
    return content


def _write_file(path: str, content: str) -> str:
    """写入文件"""
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"✅ 已写入文件: {path} ({len(content)} 字符)"


def _list_directory(path: str = ".") -> str:
    """列出目录内容"""
    if not os.path.exists(path):
        return f"Error: Directory not found: {path}"
    items = []
    for item in os.listdir(path):
        full_path = os.path.join(path, item)
        if os.path.isdir(full_path):
            items.append(f"📁 {item}/")
        else:
            size = os.path.getsize(full_path)
            items.append(f"📄 {item} ({size} bytes)")
    return "\n".join(items)


def _edit_file(path: str, old_text: str, new_text: str) -> str:
    """精确编辑文件（替换文本片段）"""
    if not os.path.exists(path):
        return f"Error: File not found: {path}"
    with open(path, encoding="utf-8") as f:
        content = f.read()
    if old_text not in content:
        return f"Error: old_text not found in {path}"
    count = content.count(old_text)
    if count > 1:
        return f"Error: old_text appears {count} times, need unique match"
    new_content = content.replace(old_text, new_text)
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    return f"✅ 已编辑文件: {path}"


# ============================================================
# 2. 搜索工具 (Search)
# ============================================================

def _grep_search(pattern: str, path: str = ".", is_regex: bool = False) -> str:
    """在文件中搜索文本/正则"""
    results = []
    for root, dirs, files in os.walk(path):
        # 跳过隐藏目录和常见忽略目录
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in
                   ('__pycache__', 'node_modules', '.git', 'venv')]
        for filename in files:
            filepath = os.path.join(root, filename)
            try:
                with open(filepath, encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, 1):
                        if is_regex:
                            if re.search(pattern, line):
                                results.append(f"{filepath}:{i}: {line.rstrip()}")
                        else:
                            if pattern in line:
                                results.append(f"{filepath}:{i}: {line.rstrip()}")
            except Exception:
                pass
            if len(results) >= 50:
                results.append("... [结果过多，只显示前50条]")
                break
        if len(results) >= 50:
            break
    return "\n".join(results) if results else "未找到匹配结果"


def _find_files(pattern: str, path: str = ".") -> str:
    """按文件名模式查找文件

    修复(Q45): 原实现用子串匹配，与描述语义不符
    现在使用 fnmatch 通配符匹配
    """
    import fnmatch
    results = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in
                   ('__pycache__', 'node_modules', '.git', 'venv')]
        for filename in files:
            # 修复(Q45): 使用 fnmatch 通配符匹配
            if fnmatch.fnmatch(filename.lower(), pattern.lower()):
                results.append(os.path.join(root, filename))
            if len(results) >= 50:
                break
        if len(results) >= 50:
            break
    return "\n".join(results) if results else "未找到匹配文件"


# ============================================================
# 3. 命令执行工具 (Execution)
# ============================================================

def _run_command(command: str, timeout: int = 30) -> str:
    """执行 shell 命令（含危险命令防护）"""
    # 安全检查：阻止危险命令模式
    import re as _re
    normalized = _re.sub(r'\s+', ' ', command.strip().lower())
    dangerous_patterns = [
        r'rm\s+.*-rf?\s+[/~]',
        r'del\s+.*[\\/][sc]:',
        r'format\s+',
        r'shutdown',
        r'mkfs',
        r':\(\)\s*\{\s*:.*\}\s*;',
        r'curl\s+.*\|\s*(bash|sh)',
        r'wget\s+.*\|\s*(bash|sh)',
        r'>\s*/dev/sd[a-z]',
        r'mv\s+.*\s+/dev/null',
    ]
    for pattern in dangerous_patterns:
        if _re.search(pattern, normalized):
            return f"⚠️ 安全限制：检测到危险命令模式，已阻止执行: {command}"

    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=timeout
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        # 截断过长输出
        if len(output) > 5000:
            output = output[:5000] + f"\n... [输出已截断，共{len(output)}字符]"
        return output.strip() or "(无输出)"
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout}s"
    except Exception as e:
        return f"Error: {str(e)}"


# ============================================================
# 4. 代码分析工具 (Code Intelligence)
# ============================================================

def _analyze_code(path: str) -> str:
    """分析 Python 文件的结构（类、函数、导入）"""
    if not os.path.exists(path):
        return f"Error: File not found: {path}"

    with open(path, encoding="utf-8") as f:
        content = f.read()

    structure = {"imports": [], "classes": [], "functions": []}

    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("import ") or line.startswith("from "):
            structure["imports"].append(line)
        elif line.startswith("class "):
            name = line.split("(")[0].replace("class ", "").replace(":", "")
            structure["classes"].append(name)
        elif line.startswith("def "):
            name = line.split("(")[0].replace("def ", "")
            structure["functions"].append(name)

    return json.dumps(structure, ensure_ascii=False, indent=2)


# ============================================================
# 5. 注册所有工具
# ============================================================

def create_default_registry() -> ToolRegistry:
    """创建包含所有默认工具的注册表"""
    registry = ToolRegistry()

    # 文件操作
    registry.register(ToolDefinition(
        name="read_file",
        description="读取指定路径的文件内容。当需要查看文件内容时使用。",
        category=ToolCategory.FILE_OPERATION,
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径（相对或绝对）"}
            },
            "required": ["path"]
        },
        handler=_read_file,
        cost_tokens=500,
    ))

    registry.register(ToolDefinition(
        name="write_file",
        description="将内容写入文件。如果目录不存在会自动创建。",
        category=ToolCategory.FILE_OPERATION,
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "要写入的内容"}
            },
            "required": ["path", "content"]
        },
        handler=_write_file,
        cost_tokens=100,
    ))

    registry.register(ToolDefinition(
        name="list_directory",
        description="列出指定目录下的文件和文件夹。",
        category=ToolCategory.FILE_OPERATION,
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目录路径，默认为当前目录"}
            }
        },
        handler=_list_directory,
        cost_tokens=200,
    ))

    registry.register(ToolDefinition(
        name="edit_file",
        description="精确编辑文件：将文件中的 old_text 替换为 new_text。old_text 必须在文件中唯一出现。",
        category=ToolCategory.FILE_OPERATION,
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "old_text": {"type": "string", "description": "要替换的原文（必须精确匹配）"},
                "new_text": {"type": "string", "description": "替换后的新文本"}
            },
            "required": ["path", "old_text", "new_text"]
        },
        handler=_edit_file,
        cost_tokens=100,
    ))

    # 搜索
    registry.register(ToolDefinition(
        name="grep_search",
        description="在指定目录的文件中搜索文本或正则表达式。返回匹配的文件名、行号和内容。",
        category=ToolCategory.SEARCH,
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "搜索模式"},
                "path": {"type": "string", "description": "搜索目录，默认当前目录"},
                "is_regex": {"type": "boolean", "description": "是否为正则表达式"}
            },
            "required": ["pattern"]
        },
        handler=_grep_search,
        cost_tokens=300,
    ))

    registry.register(ToolDefinition(
        name="find_files",
        description="按文件名模式查找文件。",
        category=ToolCategory.SEARCH,
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "文件名包含的模式"},
                "path": {"type": "string", "description": "搜索目录"}
            },
            "required": ["pattern"]
        },
        handler=_find_files,
        cost_tokens=200,
    ))

    # 命令执行
    registry.register(ToolDefinition(
        name="run_command",
        description="执行 shell 命令并返回输出。用于运行测试、构建、git 操作等。",
        category=ToolCategory.EXECUTION,
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的命令"},
                "timeout": {"type": "integer", "description": "超时秒数，默认30"}
            },
            "required": ["command"]
        },
        handler=_run_command,
        cost_tokens=500,
    ))

    # 代码分析
    registry.register(ToolDefinition(
        name="analyze_code",
        description="分析 Python 文件的代码结构，提取导入、类和函数列表。",
        category=ToolCategory.CODE_INTELLIGENCE,
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Python 文件路径"}
            },
            "required": ["path"]
        },
        handler=_analyze_code,
        cost_tokens=200,
    ))

    return registry
