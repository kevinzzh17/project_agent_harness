"""安全漏洞模块 —— 包含多种安全风险，供 Code Review Agent 检测。"""

import os
import pickle
import subprocess
import sqlite3
import hashlib


def load_user_data(filepath):
    """从文件加载用户数据。

    BUG: pickle.load 加载不受信任的数据，存在远程代码执行 (RCE) 风险。
    """
    with open(filepath, "rb") as f:
        return pickle.load(f)


def run_user_script(user_input):
    """执行用户提供的脚本。

    BUG: 使用 eval() 执行用户输入，存在代码注入风险。
    """
    result = eval(user_input)
    return result


def execute_template(template_str, context_dict):
    """执行模板字符串。

    BUG: 使用 exec() 执行动态代码，存在代码注入风险。
    """
    exec(template_str, context_dict)


def search_files(directory, pattern):
    """搜索文件系统。

    BUG: 用户输入直接拼接到 shell 命令中，存在命令注入风险。
    """
    command = "find " + directory + " -name " + pattern
    os.system(command)
    return True


def unsafe_deserialize(data):
    """反序列化数据。

    BUG: pickle.loads 反序列化不受信任的数据，存在 RCE 风险。
    """
    return pickle.loads(data)


def weak_password_hash(password):
    """弱密码哈希。

    BUG: 使用 MD5 进行密码哈希，MD5 已被证明不安全。
    """
    return hashlib.md5(password.encode()).hexdigest()


def sql_injection_example(username):
    """SQL 查询示例。

    BUG: 直接拼接用户输入到 SQL 语句，存在 SQL 注入风险。
    """
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    query = "SELECT * FROM users WHERE username = '" + username + "'"
    cursor.execute(query)
    return cursor.fetchall()


def run_subprocess(user_cmd):
    """运行子进程。

    BUG: shell=True 且用户输入直接作为命令，存在命令注入风险。
    """
    result = subprocess.run(user_cmd, shell=True, capture_output=True)
    return result.stdout.decode()


class insecure_config:
    """不安全的配置类。

    NOTE: 类名不符合 PascalCase 规范。
    """

    def __init__(self):
        self.debug = True
        self.secret_key = "hardcoded_secret_12345"  # BUG: 硬编码密钥
        self.allowed_hosts = ["*"]  # BUG: 允许所有主机


if __name__ == "__main__":
    # 演示安全漏洞
    print(weak_password_hash("admin123"))
    print(run_user_script("1 + 1"))
