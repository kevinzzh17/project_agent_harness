"""sample_project — 用于测试 Code Review Agent 的示例代码集合。

每个文件包含不同类型的故意植入的 bug：
- calculator.py        — 除零、空列表、未使用导入、命名问题
- data_processor.py    — pickle 安全风险、未处理异常、命名问题
- user_manager.py      — == None、参数遮蔽内置名、KeyError 未处理
- security_issues.py   — eval/exec、pickle、弱哈希、命令注入、路径遍历
- logic_bugs.py        — 运算符优先级、浅拷贝、可变默认参数、off-by-one
- style_issues.py      — 命名规范、行长、尾随空格、导入未使用
- network_bugs.py      — 无超时、无 SSL 验证、未关闭响应、异常吞没
- db_bugs.py           — SQL 注入、连接泄漏、无事务、参数遮蔽
- error_handling.py    — 裸 except、异常吞没、assert 校验、== None
- resource_leaks.py    — 文件句柄泄漏、锁未释放、无过期缓存、可变默认参数
"""
