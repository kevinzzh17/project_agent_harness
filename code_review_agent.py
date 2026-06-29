"""
代码审查 Agent —— 多智能体协同的落地方案

场景：用户指定一个 Python 项目目录，多个 Agent 协同完成代码审查，
      最终生成一份真实的 Markdown 审查报告文件。

架构：Orchestrator-Worker 模式
  ┌─────────────────────────────────────────────┐
  │         Orchestrator（主编排器）              │
  │  解析用户指令 → 拆分任务 → 调度 → 汇总        │
  └───┬──────────┬──────────┬────────────────────┘
      ↓          ↓          ↓
  ┌────────┐ ┌────────┐ ┌──────────┐
  │Explorer│ │Bug     │ │Style     │  ← 独立上下文的 Subagent
  │Agent   │ │Detector│ │Checker   │
  │(AST)   │ │(LLM+规则)│ │(PEP8)  │
  └────────┘ └────────┘ └──────────┘
      ↓          ↓          ↓
  ┌─────────────────────────────────────────────┐
  │       Report Generator（报告生成器）          │
  │  合并所有发现 → 写入 .md 报告文件到磁盘        │
  └─────────────────────────────────────────────┘

LLM 后端选择（按优先级自动检测）：
  1. Ollama 本地模型（免费、无需 API Key）—— 默认
  2. DeepSeek API（需 DEEPSEEK_API_KEY 环境变量）
  3. 智谱 GLM API（需 ZHIPUAI_API_KEY 环境变量）

运行方式：
  python code_review_agent.py                    # 审查自带示例项目
  python code_review_agent.py /path/to/project   # 审查指定项目
"""
import ast
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# 修复 Windows 控制台编码问题（默认 GBK 无法输出 emoji/部分中文）
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False


# ============================================================
# LLM 后端 —— 统一接口，自动选择可用的免费模型
# ============================================================

class LLMBackend:
    """统一的 LLM 调用接口，自动选择可用的后端

    优先级：
    1. Ollama（本地，免费，无需 key）—— 首选
    2. DeepSeek API（需 key）
    3. 智谱 GLM API（需 key）
    4. 离线规则模式（完全不需要网络和 LLM）
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.backend_name = ""
        self.model_name = ""
        self._ollama_url = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self._ollama_model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")

        # 按优先级探测可用后端
        if self._check_ollama():
            self.backend_name = "ollama"
            self.model_name = self._ollama_model
        elif os.environ.get("DEEPSEEK_API_KEY"):
            self.backend_name = "deepseek"
            self.model_name = "deepseek-chat"
        elif os.environ.get("ZHIPUAI_API_KEY"):
            self.backend_name = "zhipu"
            self.model_name = "glm-4-flash"
        else:
            self.backend_name = "offline"
            self.model_name = "rule-based"

        if self.verbose:
            print(f"  [LLM] 后端: {self.backend_name} / 模型: {self.model_name}")

    def _check_ollama(self) -> bool:
        """检测 Ollama 是否在本地运行"""
        if not _REQUESTS_AVAILABLE:
            return False
        try:
            resp = requests.get(f"{self._ollama_url}/api/tags", timeout=3)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                if not models:
                    return False
                # 检查指定模型是否已安装
                installed = [m["name"] for m in models]
                # 模型名可能带 :latest 后缀
                for m in installed:
                    if m.startswith(self._ollama_model.split(":")[0]):
                        self._ollama_model = m
                        return True
                # 没有指定模型但有其他模型，用第一个
                self._ollama_model = installed[0]
                return True
        except Exception:
            pass
        return False

    def generate(self, prompt: str, system: str = "", temperature: float = 0.3) -> str:
        """调用 LLM 生成文本

        Args:
            prompt: 用户提示
            system: 系统提示（可选）
            temperature: 温度参数
        Returns:
            LLM 生成的文本
        """
        if self.backend_name == "ollama":
            return self._call_ollama(prompt, system, temperature)
        elif self.backend_name == "deepseek":
            return self._call_openai_compatible(
                prompt, system, temperature,
                base_url="https://api.deepseek.com/v1/",
                api_key=os.environ["DEEPSEEK_API_KEY"],
                model="deepseek-chat",
            )
        elif self.backend_name == "zhipu":
            return self._call_openai_compatible(
                prompt, system, temperature,
                base_url="https://open.bigmodel.cn/api/paas/v4/",
                api_key=os.environ["ZHIPUAI_API_KEY"],
                model="glm-4-flash",
            )
        else:
            # 离线模式：返回空，由调用方走规则逻辑
            return ""

    def _call_ollama(self, prompt: str, system: str, temperature: float) -> str:
        """调用 Ollama 本地 API"""
        try:
            resp = requests.post(
                f"{self._ollama_url}/api/chat",
                json={
                    "model": self._ollama_model,
                    "messages": [
                        {"role": "system", "content": system} if system else None,
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "options": {"temperature": temperature},
                },
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json().get("message", {}).get("content", "")
        except Exception as e:
            if self.verbose:
                print(f"  [LLM] Ollama 调用失败: {e}")
            return ""

    def _call_openai_compatible(
        self, prompt: str, system: str, temperature: float,
        base_url: str, api_key: str, model: str,
    ) -> str:
        """调用 OpenAI 兼容 API（DeepSeek / 智谱）"""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=base_url)
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            resp = client.chat.completions.create(
                model=model, messages=messages, temperature=temperature,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            if self.verbose:
                print(f"  [LLM] {self.backend_name} 调用失败: {e}")
            return ""


# ============================================================
# 数据结构
# ============================================================

@dataclass
class CodeFile:
    """被审查的代码文件"""
    path: str
    lines: int
    content: str
    tree: ast.AST | None = None
    parse_error: str | None = None


@dataclass
class Issue:
    """发现的问题"""
    severity: str       # "critical" / "warning" / "style" / "info"
    file: str
    line: int
    category: str       # "bug" / "security" / "style" / "complexity" / "maintainability"
    message: str
    suggestion: str = ""
    source: str = ""    # "rule" 或 "llm"


@dataclass
class ReviewResult:
    """单文件的审查结果"""
    file_path: str
    issues: list[Issue] = field(default_factory=list)
    summary: str = ""
    score: float = 0.0  # 0-100


@dataclass
class ReviewReport:
    """完整审查报告"""
    project_path: str
    files_reviewed: int
    total_issues: int
    results: list[ReviewResult] = field(default_factory=list)
    overall_score: float = 0.0
    timestamp: str = ""
    llm_backend: str = ""


# ============================================================
# Agent 1: Explorer Agent —— 代码探索（纯 AST，不需要 LLM）
# ============================================================

class ExplorerAgent:
    """代码探索 Agent

    职责：
    - 扫描项目目录，找出所有 Python 文件
    - 用 AST 解析每个文件，提取结构信息（类、函数、导入）
    - 为后续 Agent 提供结构化的代码数据

    面试要点：这个 Agent 用确定性工具（AST）而非 LLM，
    避免 LLM 产生幻觉，同时节省 token。
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    def explore(self, project_path: str) -> list[CodeFile]:
        """扫描项目，返回所有 Python 文件的结构化信息

        Args:
            project_path: 项目根目录
        Returns:
            CodeFile 列表
        """
        if self.verbose:
            print("\n📂 [Explorer Agent] 扫描项目结构...")

        project = Path(project_path).resolve()
        if not project.exists():
            raise FileNotFoundError(f"项目路径不存在: {project}")

        code_files: list[CodeFile] = []
        skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv",
                      "env", ".eggs", "build", "dist", ".mypy_cache", ".pytest_cache"}

        for py_file in sorted(project.rglob("*.py")):
            # 跳过忽略目录
            if any(part in skip_dirs for part in py_file.parts):
                continue

            try:
                content = py_file.read_text(encoding="utf-8")
            except Exception as e:
                if self.verbose:
                    print(f"  ⚠️ 无法读取 {py_file}: {e}")
                continue

            code_file = CodeFile(
                path=str(py_file.relative_to(project)),
                lines=len(content.splitlines()),
                content=content,
            )

            # AST 解析
            try:
                code_file.tree = ast.parse(content, filename=str(py_file))
            except SyntaxError as e:
                code_file.parse_error = f"SyntaxError: line {e.lineno}: {e.msg}"

            code_files.append(code_file)

            if self.verbose:
                status = "✅" if code_file.tree else f"❌ {code_file.parse_error}"
                print(f"  {status} {code_file.path} ({code_file.lines} 行)")

        if self.verbose:
            print(f"  📊 共发现 {len(code_files)} 个 Python 文件")

        return code_files

    def get_structure_summary(self, code_file: CodeFile) -> str:
        """提取文件的 AST 结构摘要（供 LLM Agent 使用）"""
        if code_file.parse_error:
            return f"解析失败: {code_file.parse_error}"

        lines = []
        for node in ast.walk(code_file.tree):
            if isinstance(node, ast.FunctionDef):
                args = [a.arg for a in node.args.args]
                lines.append(
                    f"  L{node.lineno}: def {node.name}({', '.join(args)})"
                )
            elif isinstance(node, ast.ClassDef):
                lines.append(f"  L{node.lineno}: class {node.name}")

        return "\n".join(lines) if lines else "  (无函数和类定义)"


# ============================================================
# Agent 2: Bug Detector Agent —— Bug 检测（规则 + LLM）
# ============================================================

class BugDetectorAgent:
    """Bug 检测 Agent

    职责：
    - 用 AST 规则检测确定性 Bug（未使用变量、裸 except、可变默认参数等）
    - 用 LLM 分析可疑代码段，检测逻辑 Bug

    混合策略：
    - 规则检测：快速、确定、零成本 → 适合确定性 Bug
    - LLM 检测：理解语义、发现隐蔽逻辑问题 → 适合需要推理的 Bug
    """

    def __init__(self, llm: LLMBackend, verbose: bool = True):
        self.llm = llm
        self.verbose = verbose

    def review(self, code_file: CodeFile, structure: str) -> ReviewResult:
        """审查单个文件"""
        result = ReviewResult(file_path=code_file.path)

        # 解析失败的文件只报告语法错误
        if code_file.parse_error:
            result.issues.append(Issue(
                severity="critical",
                file=code_file.path,
                line=1,
                category="bug",
                message=code_file.parse_error,
                suggestion="修复语法错误后才能进行进一步分析",
                source="rule",
            ))
            result.summary = "存在语法错误，无法进行深度分析"
            result.score = 0.0
            return result

        # Phase 1: AST 规则检测
        rule_issues = self._detect_by_rules(code_file)
        result.issues.extend(rule_issues)

        # Phase 2: LLM 语义分析
        llm_issues = self._detect_by_llm(code_file, structure)
        result.issues.extend(llm_issues)

        # 修复(Q65): 如果 LLM 不可用或调用失败，在摘要中明确告知用户
        if self.llm.backend_name == "offline":
            result.summary = (result.summary + " | ⚠️ LLM不可用，仅使用规则引擎"
                             if result.summary else "⚠️ LLM不可用，仅使用规则引擎检测")

        # 计算分数
        result.score = self._calculate_score(result.issues, code_file.lines)
        result.summary = self._generate_summary(result.issues)

        return result

    def _detect_by_rules(self, code_file: CodeFile) -> list[Issue]:
        """基于 AST 规则检测确定性 Bug"""
        issues = []
        tree = code_file.tree

        for node in ast.walk(tree):
            # 1. 裸 except（except: 而非 except Exception:）
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                issues.append(Issue(
                        severity="warning",
                        file=code_file.path,
                        line=node.lineno,
                        category="bug",
                        message="裸 except 会捕获所有异常（包括 KeyboardInterrupt、SystemExit）",
                        suggestion="改为 `except Exception:` 或指定具体异常类型",
                        source="rule",
                    ))

            # 2. 可变默认参数（列表/字典/集合作为默认值）
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for default in node.args.defaults + node.args.kw_defaults:
                    if default and isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        issues.append(Issue(
                            severity="warning",
                            file=code_file.path,
                            line=node.lineno,
                            category="bug",
                            message=f"函数 {node.name} 使用可变对象作为默认参数",
                            suggestion="可变默认参数在函数定义时只创建一次，会导致状态共享。改用 None 并在函数内初始化",
                            source="rule",
                        ))

            # 3. assert 用于生产代码（可能被 -O 优化掉）
            if isinstance(node, ast.Assert):
                issues.append(Issue(
                    severity="info",
                    file=code_file.path,
                    line=node.lineno,
                    category="maintainability",
                    message="assert 语句在 python -O 模式下会被移除，不应用于运行时校验",
                    suggestion="生产代码中改用 if + raise",
                    source="rule",
                    ))

            # 4. == None / != None / == True / == False（应该用 is / is not）
            if isinstance(node, ast.Compare):
                for comparator in node.comparators:
                    if isinstance(comparator, ast.Constant):
                        if comparator.value is None:
                            op = "==" if isinstance(node.ops[0], ast.Eq) else "!="
                            issues.append(Issue(
                                severity="warning",
                                file=code_file.path,
                                line=node.lineno,
                                category="bug",
                                message=f"使用 {op} None 比较，应该用 'is None' / 'is not None'（PEP8 E711）",
                                suggestion="改为 `is None` 或 `is not None`",
                                source="rule",
                            ))
                        elif isinstance(comparator.value, bool):
                            issues.append(Issue(
                                severity="style",
                                file=code_file.path,
                                line=node.lineno,
                                category="style",
                                message=f"避免使用 == {'True' if comparator.value else 'False'}",
                                suggestion=f"直接用 `if {'not ' if not comparator.value else ''}condition:`",
                                source="rule",
                            ))

            # 5. eval / exec 调用（安全风险）
            if isinstance(node, ast.Call):
                func_name = ""
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr

                if func_name in ("eval", "exec"):
                    issues.append(Issue(
                        severity="critical",
                        file=code_file.path,
                        line=node.lineno,
                        category="security",
                        message=f"使用 {func_name}() 存在代码注入风险",
                        suggestion="避免使用 eval/exec，考虑用 ast.literal_eval 或其他安全替代方案",
                        source="rule",
                    ))

                # 6. pickle.load / pickle.loads（安全风险）
                if (func_name in ("load", "loads")
                        and isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "pickle"):
                    issues.append(Issue(
                            severity="critical",
                            file=code_file.path,
                            line=node.lineno,
                            category="security",
                            message=f"使用 pickle.{func_name}() 存在远程代码执行风险",
                            suggestion="pickle 反序列化不受信任的数据可导致 RCE，建议改用 json.load",
                            source="rule",
                        ))

            # 7. 函数参数遮蔽内置名（id, type, list, dict 等）
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _BUILTINS = {"id", "type", "list", "dict", "set", "str", "int",
                             "float", "bool", "tuple", "range", "len", "sum", "map",
                             "filter", "print", "input", "open", "format"}
                for arg in node.args.args:
                    if arg.arg in _BUILTINS:
                        issues.append(Issue(
                            severity="warning",
                            file=code_file.path,
                            line=node.lineno,
                            category="bug",
                            message=f"参数 '{arg.arg}' 遮蔽了 Python 内置名称",
                            suggestion="重命名参数，避免与内置函数同名",
                            source="rule",
                        ))

        if self.verbose and issues:
            print(f"  🔍 [Bug Detector] {code_file.path}: 规则发现 {len(issues)} 个问题")

        return issues

    def _detect_by_llm(self, code_file: CodeFile, structure: str) -> list[Issue]:
        """用 LLM 分析代码逻辑，检测隐蔽 Bug

        面试要点：
        - LLM 检测和规则检测互补：规则抓确定性 Bug，LLM 抓逻辑 Bug
        - 只发送代码摘要 + 可疑片段，而非整个文件，节省 token
        - 要求 LLM 返回结构化 JSON，方便解析
        """
        # 如果 LLM 不可用（离线模式），跳过
        if self.llm.backend_name == "offline":
            if self.verbose:
                print(f"  🔍 [Bug Detector] {code_file.path}: 离线模式，跳过 LLM 分析")
            return []

        # 只发送代码内容（截断过长文件）
        code_to_analyze = code_file.content
        if len(code_to_analyze) > 8000:
            code_to_analyze = code_to_analyze[:8000] + "\n# ... (已截断)"

        prompt = f"""你是代码审查专家。请分析以下 Python 代码，找出潜在的 Bug 和安全问题。

文件: {code_file.path} ({code_file.lines} 行)
结构:
{structure}

代码:
```python
{code_to_analyze}
```

请以 JSON 数组格式输出发现的问题，每个问题包含：
- line: 行号（整数）
- severity: "critical" / "warning" / "info"
- category: "bug" / "security" / "maintainability"
- message: 问题描述
- suggestion: 修改建议

如果没有发现问题，返回空数组 []。
只返回 JSON，不要其他文字。

```json
[
  {{"line": 0, "severity": "warning", "category": "bug", "message": "描述", "suggestion": "建议"}}
]
```"""

        system = "你是一个专业的 Python 代码审查专家。只返回 JSON 格式的问题列表，不要包含 markdown 代码块标记。"

        response = self.llm.generate(prompt, system=system, temperature=0.1)

        if not response:
            return []

        issues = self._parse_llm_response(response, code_file.path)

        if self.verbose and issues:
            print(f"  🔍 [Bug Detector] {code_file.path}: LLM 发现 {len(issues)} 个问题")

        return issues

    def _parse_llm_response(self, response: str, file_path: str) -> list[Issue]:
        """解析 LLM 返回的 JSON 问题列表"""
        # 清理 markdown 代码块标记
        cleaned = response.strip()
        if cleaned.startswith("```"):
            # 去掉 ```json 或 ``` 标记
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            # 尝试提取 JSON 数组部分
            start = response.find("[")
            end = response.rfind("]")
            if start != -1 and end != -1:
                try:
                    data = json.loads(response[start:end + 1])
                except json.JSONDecodeError:
                    return []
            else:
                return []

        issues = []
        for item in data:
            if not isinstance(item, dict):
                continue
            issues.append(Issue(
                severity=item.get("severity", "info"),
                file=file_path,
                line=int(item.get("line", 0)),
                category=item.get("category", "bug"),
                message=item.get("message", ""),
                suggestion=item.get("suggestion", ""),
                source="llm",
            ))

        return issues

    def _calculate_score(self, issues: list[Issue], lines: int) -> float:
        """根据问题数量和严重程度计算代码质量分（0-100）"""
        penalty = 0
        weights = {"critical": 25, "warning": 10, "style": 3, "info": 1}
        for issue in issues:
            penalty += weights.get(issue.severity, 1)

        # 归一化（每 100 行代码的扣分）
        if lines > 0:
            penalty = penalty * 100 / lines

        score = max(0, 100 - penalty)
        return round(score, 1)

    def _generate_summary(self, issues: list[Issue]) -> str:
        """生成单文件审查摘要"""
        if not issues:
            return "未发现问题 ✅"

        counts = {}
        for issue in issues:
            counts[issue.severity] = counts.get(issue.severity, 0) + 1

        parts = []
        for sev in ["critical", "warning", "style", "info"]:
            if sev in counts:
                parts.append(f"{counts[sev]} 个 {sev}")

        return "发现 " + "，".join(parts)


# ============================================================
# Agent 3: Style Checker Agent —— 风格检查（纯规则）
# ============================================================

class StyleCheckerAgent:
    """代码风格检查 Agent

    职责：检查 PEP 8 风格规范
    - 命名规范（snake_case 函数/变量，PascalCase 类）
    - 行长度
    - 缩进一致性
    - 导入排序

    面试要点：风格检查用确定性规则即可，不需要 LLM，
    节省成本且结果可复现。
    """

    def __init__(self, verbose: bool = True, max_line_length: int = 120):
        self.verbose = verbose
        self.max_line_length = max_line_length

    def review(self, code_file: CodeFile) -> ReviewResult:
        """检查代码风格"""
        result = ReviewResult(file_path=code_file.path)

        if code_file.parse_error:
            result.summary = "解析失败，跳过风格检查"
            result.score = 0.0
            return result

        lines = code_file.content.splitlines()
        issues = []

        # 1. 行长度检查
        for i, line in enumerate(lines, 1):
            if len(line) > self.max_line_length:
                issues.append(Issue(
                    severity="style",
                    file=code_file.path,
                    line=i,
                    category="style",
                    message=f"行长度 {len(line)} 超过限制 {self.max_line_length}",
                    suggestion="将长行拆分为多行",
                    source="rule",
                ))

        # 2. 命名规范检查（基于 AST）
        if code_file.tree:
            for node in ast.walk(code_file.tree):
                if isinstance(node, ast.ClassDef):
                    # 类名应首字母大写
                    if not node.name[0].isupper():
                        issues.append(Issue(
                            severity="style",
                            file=code_file.path,
                            line=node.lineno,
                            category="style",
                            message=f"类名 '{node.name}' 不符合 PascalCase 规范",
                            suggestion="类名应使用 PascalCase（如 MyClass）",
                            source="rule",
                        ))
                    # 类名包含下划线不符合 PascalCase
                    elif "_" in node.name:
                        issues.append(Issue(
                            severity="style",
                            file=code_file.path,
                            line=node.lineno,
                            category="style",
                            message=f"类名 '{node.name}' 包含下划线，不符合 PascalCase 规范",
                            suggestion="类名不应包含下划线（如 UserManager 而非 User_Manager）",
                            source="rule",
                        ))

                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not _is_snake_case(node.name):
                        issues.append(Issue(
                            severity="style",
                            file=code_file.path,
                            line=node.lineno,
                            category="style",
                            message=f"函数名 '{node.name}' 不符合 snake_case 规范",
                            suggestion="函数名应使用 snake_case（如 my_function）",
                            source="rule",
                        ))
                    # 检查参数名是否符合 snake_case（排除 self/cls）
                    for arg in node.args.args:
                        if arg.arg in ("self", "cls"):
                            continue
                        if not _is_snake_case(arg.arg):
                            issues.append(Issue(
                                severity="style",
                                file=code_file.path,
                                line=node.lineno,
                                category="style",
                                message=f"参数名 '{arg.arg}' 不符合 snake_case 规范",
                                suggestion="参数名应使用小写（如 email 而非 Email）",
                                source="rule",
                            ))

        # 3. 尾随空格检查
        for i, line in enumerate(lines, 1):
            if line != line.rstrip() and line.strip():
                issues.append(Issue(
                    severity="info",
                    file=code_file.path,
                    line=i,
                    category="style",
                    message="行尾有多余空格",
                    suggestion="移除行尾空格",
                    source="rule",
                ))

        result.issues = issues
        result.score = self._calculate_style_score(issues, len(lines))
        result.summary = self._generate_summary(issues)

        return result

    def _calculate_style_score(self, issues: list[Issue], lines: int) -> float:
        penalty = sum(2 for i in issues if i.severity == "style") + \
                  sum(0.5 for i in issues if i.severity == "info")
        if lines > 0:
            penalty = penalty * 100 / lines
        return round(max(0, 100 - penalty), 1)

    def _generate_summary(self, issues: list[Issue]) -> str:
        if not issues:
            return "风格检查通过 ✅"
        return f"发现 {len(issues)} 个风格问题"


def _is_snake_case(name: str) -> bool:
    """检查是否为 snake_case"""
    if not name:
        return True
    # 允许下划线开头（如 _private）和全大写（如 __init__）
    if name.startswith("_"):
        name = name.lstrip("_")
    # 全大写常量允许
    if name.isupper():
        return True
    # 不应包含大写字母
    return not any(c.isupper() for c in name)


# ============================================================
# Agent 4: Report Generator —— 报告生成
# ============================================================

class ReportGeneratorAgent:
    """报告生成 Agent

    职责：将所有 Agent 的审查结果汇总为 Markdown 报告，写入磁盘

    面试要点：这是真正"落地"的体现——产出真实的文件，
    而非在终端 print 假装成功。
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    def generate(
        self,
        report: ReviewReport,
        output_path: str,
    ) -> str:
        """生成 Markdown 报告文件

        Args:
            report: 审查报告数据
            output_path: 输出文件路径
        Returns:
            实际写入的文件路径
        """
        md = self._build_markdown(report)

        # 确保输出目录存在
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        # 写入文件
        out.write_text(md, encoding="utf-8")

        if self.verbose:
            print(f"  📝 [Report Generator] 报告已写入: {out}")
            print(f"     文件大小: {out.stat().st_size} 字节")

        return str(out)

    def _build_markdown(self, report: ReviewReport) -> str:
        """构建 Markdown 报告内容"""
        lines = []

        # 标题
        lines.append("# 📋 代码审查报告")
        lines.append("")
        lines.append("| 项目 | 值 |")
        lines.append("|------|-----|")
        lines.append(f"| 审查路径 | `{report.project_path}` |")
        lines.append(f"| 审查时间 | {report.timestamp} |")
        lines.append(f"| LLM 后端 | {report.llm_backend} |")
        lines.append(f"| 审查文件数 | {report.files_reviewed} |")
        lines.append(f"| 问题总数 | {report.total_issues} |")
        lines.append(f"| 综合评分 | **{report.overall_score}/100** |")
        lines.append("")

        # 评分分布
        severity_counts = {"critical": 0, "warning": 0, "style": 0, "info": 0}
        for result in report.results:
            for issue in result.issues:
                severity_counts[issue.severity] = severity_counts.get(issue.severity, 0) + 1

        lines.append("## 📊 问题分布")
        lines.append("")
        lines.append("| 严重级别 | 数量 |")
        lines.append("|----------|------|")
        for sev in ["critical", "warning", "style", "info"]:
            emoji = {"critical": "🔴", "warning": "🟡", "style": "🔵", "info": "⚪"}[sev]
            lines.append(f"| {emoji} {sev} | {severity_counts[sev]} |")
        lines.append("")

        # 每个文件的详细报告
        lines.append("## 📁 文件详情")
        lines.append("")

        for result in report.results:
            lines.append(f"### `{result.file_path}`")
            lines.append("")
            lines.append(f"**评分**: {result.score}/100 | **问题数**: {len(result.issues)} | **摘要**: {result.summary}")
            lines.append("")

            if result.issues:
                lines.append("| 级别 | 行 | 类别 | 来源 | 描述 | 建议 |")
                lines.append("|------|-----|------|------|------|------|")
                for issue in sorted(result.issues, key=lambda i: (i.line, i.severity)):
                    lines.append(
                        f"| {issue.severity} | {issue.line} | {issue.category} | "
                        f"{issue.source} | {issue.message} | {issue.suggestion} |"
                    )
            else:
                lines.append("✅ 未发现问题")
            lines.append("")

        # 改进建议总结
        lines.append("## 💡 改进建议总结")
        lines.append("")

        all_critical = [i for r in report.results for i in r.issues if i.severity == "critical"]
        all_warnings = [i for r in report.results for i in r.issues if i.severity == "warning"]

        if all_critical:
            lines.append("### 🔴 必须修复（Critical）")
            lines.append("")
            for issue in all_critical[:20]:
                lines.append(f"- **{issue.file}:{issue.line}** — {issue.message}")
                if issue.suggestion:
                    lines.append(f"  - 建议: {issue.suggestion}")
            lines.append("")

        if all_warnings:
            lines.append("### 🟡 建议修复（Warning）")
            lines.append("")
            for issue in all_warnings[:30]:
                lines.append(f"- **{issue.file}:{issue.line}** — {issue.message}")
                if issue.suggestion:
                    lines.append(f"  - 建议: {issue.suggestion}")
            lines.append("")

        if not all_critical and not all_warnings:
            lines.append("代码质量良好，没有发现严重问题！🎉")
            lines.append("")

        lines.append("---")
        lines.append(f"*本报告由 Code Review Agent 自动生成 | {report.timestamp}*")

        return "\n".join(lines)


# ============================================================
# Orchestrator —— 多 Agent 编排器
# ============================================================

class CodeReviewOrchestrator:
    """代码审查主编排器

    负责：
    1. 初始化各 Agent（Explorer、Bug Detector、Style Checker、Report Generator）
    2. 协调各 Agent 的执行顺序
    3. 汇总各 Agent 的结果
    4. 驱动报告生成

    面试要点：Orchestrator 本身不做事，只负责"编排"。
    每个子 Agent 有独立职责，可独立测试和替换。
    """

    def __init__(self, llm: LLMBackend | None = None, verbose: bool = True):
        self.llm = llm or LLMBackend(verbose=verbose)
        self.verbose = verbose

        # 初始化各 Agent
        self.explorer = ExplorerAgent(verbose=verbose)
        self.bug_detector = BugDetectorAgent(self.llm, verbose=verbose)
        self.style_checker = StyleCheckerAgent(verbose=verbose)
        self.report_generator = ReportGeneratorAgent(verbose=verbose)

    def review_project(self, project_path: str, output_report: str = "") -> ReviewReport:
        """审查整个项目

        Args:
            project_path: 项目根目录
            output_report: 报告输出路径（空则自动生成）
        Returns:
            ReviewReport 对象
        """
        print("=" * 60)
        print("📋 代码审查 Agent 启动")
        print(f"   项目路径: {project_path}")
        print(f"   LLM 后端: {self.llm.backend_name} / {self.llm.model_name}")
        print("=" * 60)

        start_time = time.time()

        # ---- Stage 1: Explorer Agent 扫描项目 ----
        print("\n🤖 [Agent 1/4] Explorer Agent — 代码探索")
        code_files = self.explorer.explore(project_path)

        if not code_files:
            print("\n⚠️ 未找到任何 Python 文件")
            return ReviewReport(
                project_path=str(Path(project_path).resolve()),
                files_reviewed=0,
                total_issues=0,
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                llm_backend=self.llm.backend_name,
            )

        # ---- Stage 2: Bug Detector + Style Checker 并行审查 ----
        print("\n🤖 [Agent 2/4] Bug Detector Agent — Bug 检测")
        print("🤖 [Agent 3/4] Style Checker Agent — 风格检查")

        all_results: list[ReviewResult] = []

        for code_file in code_files:
            # Bug 检测
            structure = self.explorer.get_structure_summary(code_file)
            bug_result = self.bug_detector.review(code_file, structure)

            # 风格检查
            style_result = self.style_checker.review(code_file)

            # 合并结果
            combined = ReviewResult(
                file_path=code_file.path,
                issues=bug_result.issues + style_result.issues,
                summary=f"Bug: {bug_result.summary}; 风格: {style_result.summary}",
                score=round((bug_result.score + style_result.score) / 2, 1),
            )
            all_results.append(combined)

            print(f"  ✅ {code_file.path}: 评分 {combined.score}/100, "
                  f"问题 {len(combined.issues)} 个")

        # ---- Stage 3: 汇总报告 ----
        print("\n🤖 [Agent 4/4] Report Generator Agent — 生成报告")

        total_issues = sum(len(r.issues) for r in all_results)
        avg_score = round(sum(r.score for r in all_results) / len(all_results), 1) if all_results else 0

        report = ReviewReport(
            project_path=str(Path(project_path).resolve()),
            files_reviewed=len(code_files),
            total_issues=total_issues,
            results=all_results,
            overall_score=avg_score,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            llm_backend=f"{self.llm.backend_name}/{self.llm.model_name}",
        )

        # 确定输出路径
        if not output_report:
            output_dir = Path(project_path).resolve() / "output"
            output_report = str(output_dir / "code_review_report.md")

        # 生成报告文件
        written_path = self.report_generator.generate(report, output_report)

        elapsed = time.time() - start_time

        print("\n" + "=" * 60)
        print("📊 审查完成")
        print(f"   耗时: {elapsed:.1f}s")
        print(f"   文件数: {report.files_reviewed}")
        print(f"   问题总数: {report.total_issues}")
        print(f"   综合评分: {report.overall_score}/100")
        print(f"   报告文件: {written_path}")
        print("=" * 60)

        return report


# ============================================================
# 主入口
# ============================================================

def main():
    """主入口：审查指定项目目录

    用法：
      python code_review_agent.py                    # 审查自带示例项目
      python code_review_agent.py /path/to/project   # 审查指定项目
    """
    # 确定审查目标
    target = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).parent / "sample_project")

    if not Path(target).exists():
        print(f"❌ 路径不存在: {target}")
        sys.exit(1)

    # 创建编排器并运行
    orchestrator = CodeReviewOrchestrator()
    report = orchestrator.review_project(target)

    # 打印最终摘要
    print(f"\n📄 审查报告已生成，包含 {report.total_issues} 个问题。")
    print(f"   综合评分: {report.overall_score}/100")

    # 退出码：有 critical 问题则返回 1
    critical_count = sum(
        1 for r in report.results for i in r.issues if i.severity == "critical"
    )
    if critical_count > 0:
        print(f"\n⚠️ 发现 {critical_count} 个严重问题！")
        sys.exit(1)


if __name__ == "__main__":
    main()
