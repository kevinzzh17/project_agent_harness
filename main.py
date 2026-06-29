"""
主入口 —— 运行 Agent Harness

使用方法：
  python main.py

会启动交互式对话，你可以给 Agent 下达任务，
它会自主使用工具完成（读文件、搜索、执行命令等）。
"""
import os
import sys
import json

# ============================================================
#  API 配置 —— 从环境变量读取 API Key（Q33: 安全修复，不再硬编码）
#  请在系统环境变量中设置:
#    set DEEPSEEK_API_KEY=sk-xxxx
#    set ZHIPUAI_API_KEY=xxxx
#    set OPENAI_API_KEY=sk-xxxx
# ============================================================
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")        # 从环境变量读取
ZHIPUAI_API_KEY  = os.environ.get("ZHIPUAI_API_KEY", "")         # 智谱 API Key
OPENAI_API_KEY   = os.environ.get("OPENAI_API_KEY", "")          # OpenAI API Key

# 选择使用的服务商: "deepseek" | "zhipu" | "openai"
PROVIDER = "deepseek"

# 各服务商默认配置
PROVIDER_CONFIGS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1/",
        "model": "deepseek-chat",
        "api_key": DEEPSEEK_API_KEY,
    },
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4/",
        "model": "glm-4-flash",
        "api_key": ZHIPUAI_API_KEY,
    },
    "openai": {
        "base_url": "https://api.openai.com/v1/",
        "model": "gpt-4o-mini",
        "api_key": OPENAI_API_KEY,
    },
}
# ============================================================

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import AgentHarness, SubagentConfig
from builtin_tools import create_default_registry


def create_agent() -> AgentHarness:
    """创建配置好的 Agent"""
    
    # 读取所选服务商的配置（环境变量可覆盖）
    cfg = PROVIDER_CONFIGS[PROVIDER]
    api_key  = os.environ.get("LLM_API_KEY",  cfg["api_key"])
    base_url = os.environ.get("LLM_BASE_URL", cfg["base_url"])
    model    = os.environ.get("LLM_MODEL",    cfg["model"])
    
    if not api_key:
        print("⚠️ 未设置 API Key!")
        print(f"   请设置环境变量 {PROVIDER.upper()}_API_KEY 或 LLM_API_KEY")
        sys.exit(1)
    
    # 创建 Agent
    agent = AgentHarness(
        api_key=api_key,
        base_url=base_url,
        model=model,
        system_prompt="""你是一个能自主完成编程任务的 AI Agent。

工作方式：
1. 理解用户请求，分析需要做什么
2. 使用工具收集信息（读文件、搜索代码、执行命令）
3. 执行操作（编辑文件、运行命令）
4. 验证结果（运行测试、检查输出）
5. 迭代直到任务完成

规则：
- 每次只调用必要的工具
- 工具调用后检查结果是否成功
- 如果遇到错误，分析原因并尝试修复
- 任务完成后给出清晰的总结
- 使用中文回复""",
        max_tokens=128000,
        max_iterations=15,
    )
    
    # 注册工具
    registry = create_default_registry()
    for tool in registry.list_tools():
        agent.register_tool(tool)
    
    # 注册子代理（探索代理）
    agent.register_subagent(SubagentConfig(
        name="explorer",
        description="用于代码库探索和搜索的只读子代理",
        system_prompt="你是一个代码探索专家。使用工具搜索和阅读代码，返回结构化的发现摘要。",
        tools=["read_file", "grep_search", "find_files", "list_directory"],
        model=model,
    ))
    
    return agent


def interactive_loop(agent: AgentHarness):
    """交互式对话循环"""
    print("=" * 60)
    print("🤖 Agent Harness 交互模式")
    print("=" * 60)
    print("命令:  /stats  查看统计  |  /context  查看上下文  |  /checkpoints  查看检查点")
    print("       /rewind <id>  回滚  |  /clear  清空上下文  |  /quit  退出")
    print("=" * 60)
    print()
    
    while True:
        try:
            user_input = input("👤 你: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        
        if not user_input:
            continue
        
        # 命令处理
        if user_input == "/quit":
            break
        elif user_input == "/stats":
            print(json.dumps(agent.get_stats(), ensure_ascii=False, indent=2))
            continue
        elif user_input == "/context":
            print(json.dumps(agent.get_context_usage(), ensure_ascii=False, indent=2))
            continue
        elif user_input == "/checkpoints":
            cps = agent.checkpoints.list_checkpoints()
            for cp in cps:
                print(f"  {cp['id']} | {cp['time']} | {cp['desc']}")
            continue
        elif user_input.startswith("/rewind"):
            parts = user_input.split()
            if len(parts) >= 2:
                cp_id = parts[1]
                if agent.rewind(cp_id):
                    print(f"✅ 已回滚到检查点 {cp_id}")
                else:
                    print(f"❌ 检查点 {cp_id} 不存在")
            continue
        elif user_input == "/clear":
            agent.context.messages = agent.context.messages[:1]  # 只保留system
            agent.context._token_estimate = sum(
                agent.context._estimate_tokens(m.content) 
                for m in agent.context.messages
            )
            print("✅ 上下文已清空")
            continue
        
        # 运行 Agent
        print("\n🤖 Agent: ", end="", flush=True)
        result = agent.run(user_input)
        print(result)
        print()


if __name__ == "__main__":
    agent = create_agent()
    interactive_loop(agent)
