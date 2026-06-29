# Agent Harness — 贡献指南

感谢你对本项目的关注！欢迎提交 Issue 和 Pull Request。

## 开发环境

```bash
git clone <repo-url>
cd project4_agent_harness
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## 代码规范

- 使用 `ruff` 进行 lint：`ruff check .`
- 使用 `mypy` 进行类型检查：`mypy *.py`
- 行宽上限 120 字符
- 遵循 PEP 8 命名规范（snake_case 函数/变量，PascalCase 类）

## 提交前检查

```bash
ruff check .          # lint 无报错
mypy *.py             # 类型检查无报错
pytest tests/ -v      # 全部测试通过
```

## 提交 PR

1. Fork 仓库并创建 feature 分支
2. 确保通过上述检查
3. 提交 PR 并描述改动内容和动机
4. 等待 CI 通过和 review
