"""
网络与数据处理 Bug 示例模块 —— 模拟真实 Web 后端场景中的常见问题。

覆盖：
- 无超时的网络请求
- 响应未校验
- JSON 解析无异常处理
- 数据库连接泄漏
- 无限重试
- 编码问题
- 时区处理错误
- 竞态条件（TOCTOU）
"""

import json
import sqlite3
import requests
import time
from datetime import datetime


# ============================================================
# 1. 无超时的网络请求
# ============================================================

def fetch_api_data(url: str):
    """从 API 获取数据。

    Bug: requests.get 没有设置 timeout，如果服务器无响应会永久阻塞。
    """
    response = requests.get(url)  # Bug: 无 timeout
    return response.json()


def download_file(url: str, filepath: str):
    """下载文件。

    Bug: 无 timeout + 无大小限制，可能下载超大文件导致内存耗尽。
    """
    response = requests.get(url)  # Bug: 无 timeout
    with open(filepath, "wb") as f:
        f.write(response.content)  # Bug: 全部读入内存


# ============================================================
# 2. 响应未校验
# ============================================================

def get_user_info(api_url: str, user_id: str):
    """获取用户信息。

    Bug: 没有检查 HTTP 状态码，500 错误时 .json() 会抛异常或返回错误数据。
    """
    response = requests.get(f"{api_url}/users/{user_id}")
    # Bug: 没有检查 response.status_code == 200
    return response.json()  # 可能返回错误页面 HTML 而非 JSON


def search_api(query: str, api_key: str):
    """调用搜索 API。

    Bug: 没有校验返回的 JSON 结构，直接访问可能抛出 KeyError。
    """
    response = requests.post(
        "https://api.example.com/search",
        json={"query": query},
        headers={"Authorization": api_key},
    )
    data = response.json()
    return data["results"]  # Bug: 没有检查 "results" 是否存在


# ============================================================
# 3. JSON 解析无异常处理
# ============================================================

def parse_json_safely(json_string: str):
    """安全解析 JSON 字符串。

    Bug: 没有 try-except，无效 JSON 会抛出未捕获的 JSONDecodeError。
    """
    return json.loads(json_string)  # Bug: 无异常处理


def load_config_file(filepath: str):
    """加载 JSON 配置文件。

    Bug: 文件读取和 JSON 解析都没有异常处理。
    """
    with open(filepath, "r") as f:
        config = json.load(f)  # Bug: 无异常处理
    return config["settings"]["database_url"]  # Bug: 直接深层访问，可能 KeyError


# ============================================================
# 4. 数据库连接泄漏
# ============================================================

def query_database(db_path: str, sql: str):
    """查询数据库。

    Bug: 连接没有用 with 或 try-finally 关闭，异常时连接泄漏。
    """
    conn = sqlite3.connect(db_path)  # Bug: 无 with / 无 close
    cursor = conn.cursor()
    cursor.execute(sql)
    results = cursor.fetchall()
    # Bug: 忘记 conn.close()，如果 execute 抛异常则连接泄漏
    return results


def insert_user(db_path: str, username: str, email: str):
    """插入用户到数据库。

    Bug: 连接未关闭 + 未提交事务。
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (username, email) VALUES (?, ?)",
        (username, email)
    )
    # Bug: 忘记 conn.commit()，数据不会持久化
    # Bug: 忘记 conn.close()


# ============================================================
# 5. 无限重试 / 不当重试
# ============================================================

def fetch_with_retry(url: str, max_retries: int = 3):
    """带重试的 fetch。

    Bug: retry_count 永远递增但 max_retries 是 3，逻辑看起来对，
    但没有指数退避，所有重试会在毫秒内完成，对服务器造成冲击。
    """
    retry_count = 0
    while True:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                return response.json()
        except requests.RequestException:
            pass
        retry_count += 1
        if retry_count >= max_retries:
            break
        # Bug: 没有等待/退避，立即重试
    return None


def call_external_api(endpoint: str):
    """调用外部 API——无限重试。

    Bug: 没有最大重试次数限制，可能无限循环。
    """
    while True:
        try:
            response = requests.get(endpoint, timeout=5)
            return response.json()
        except requests.RequestException:
            continue  # Bug: 无限重试，没有最大次数限制


# ============================================================
# 6. 编码问题
# ============================================================

def read_text_file(filepath: str):
    """读取文本文件。

    Bug: 没有指定 encoding，在不同操作系统上可能用不同编码（Windows GBK, Linux UTF-8）。
    """
    with open(filepath, "r") as f:  # Bug: 无 encoding 参数
        return f.read()


def write_text_file(filepath: str, content: str):
    """写入文本文件。

    Bug: 没有指定 encoding。
    """
    with open(filepath, "w") as f:  # Bug: 无 encoding 参数
        f.write(content)


# ============================================================
# 7. 时区处理错误
# ============================================================

def get_current_timestamp():
    """获取当前时间戳。

    Bug: datetime.now() 返回本地时间（无时区信息），
    在不同时区的服务器上结果不同，应使用 datetime.utcnow() 或带时区的 datetime。
    """
    return datetime.now()  # Bug: 无时区信息


def calculate_expiry(created_at: datetime, hours: int):
    """计算过期时间。

    Bug: 假设 created_at 有时区信息，但如果传入 naive datetime 则计算错误。
    """
    return created_at.timestamp() + hours * 3600  # Bug: 时区假设不安全


def format_log_timestamp():
    """格式化日志时间戳。

    Bug: 使用本地时间，日志在不同服务器上时间不一致。
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Bug: 本地时间无时区


# ============================================================
# 8. 竞态条件（TOCTOU）
# ============================================================

def read_and_update_file(filepath: str):
    """读取文件内容，修改后写回。

    Bug: 检查时间到使用时间（TOCTOU）竞态条件。
    两个进程同时执行此函数会丢失更新。
    """
    # Time-of-check
    with open(filepath, "r") as f:
        content = f.read()
    count = int(content.strip())
    count += 1
    # Time-of-use（在此期间另一个进程可能已经修改了文件）
    with open(filepath, "w") as f:
        f.write(str(count))
    # 应使用文件锁 fcntl.flock 或原子操作


class BankAccount:
    """银行账户——非线程安全。

    Bug: transfer 方法中先读后写余额，多线程下会丢失更新。
    """

    def __init__(self, balance: float = 0):
        self.balance = balance

    def transfer(self, amount: float, to_account: "BankAccount"):
        """转账。

        Bug: 非原子操作，多线程下可能超额转账。
        """
        if self.balance >= amount:  # Time-of-check
            self.balance -= amount  # Time-of-use
            to_account.balance += amount
            return True
        return False


# ============================================================
# 9. 日志中的敏感信息
# ============================================================

def log_user_login(username: str, password: str):
    """记录用户登录。

    Bug: 将密码写入日志，敏感信息泄漏。
    """
    print(f"User {username} logged in with password: {password}")  # Bug: 敏感信息入日志


def log_api_call(api_key: str, endpoint: str):
    """记录 API 调用。

    Bug: 将 API Key 完整写入日志。
    """
    print(f"API call to {endpoint} with key: {api_key}")  # Bug: 敏感信息入日志


# ============================================================
# 10. 正则表达式问题
# ============================================================

def validate_phone(phone: str) -> bool:
    """验证手机号。

    Bug: 正则表达式没有使用锚点 ^ 和 $，"abc13812345678def" 也会匹配。
    """
    import re
    # Bug: 缺少 ^ 和 $ 锚点
    pattern = r"1[3-9]\d{9}"
    return bool(re.search(pattern, phone))  # 应该用 re.match 或加 ^ $


def extract_emails(text: str):
    """提取邮箱地址。

    Bug: 正则表达式过于简单，会匹配无效邮箱（如 "a@b"）。
    且没有处理大小写和复杂域名。
    """
    import re
    # Bug: 过于简单的邮箱正则
    pattern = r"\S+@\S+\.\S+"
    return re.findall(pattern, text)


# ============================================================
# 运行入口
# ============================================================

def main():
    """演示入口。"""
    print("网络与数据处理 Bug 示例模块")
    print(f"当前时间戳: {get_current_timestamp()}")
    print(f"validate_phone('abc13812345678def') = {validate_phone('abc13812345678def')}")


if __name__ == "__main__":
    main()
