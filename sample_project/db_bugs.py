"""数据库操作模块 —— 包含 SQL 注入、连接泄漏等问题，供 Code Review Agent 检测。"""

import sqlite3
from pathlib import Path


class DatabaseManager:
    """数据库管理器，包含多种 bug。"""

    def __init__(self, db_path="app.db"):
        self.db_path = db_path
        # BUG: 在构造函数中打开连接但不关闭，可能导致连接泄漏
        self.conn = sqlite3.connect(db_path)

    def search_users(self, keyword):
        """搜索用户。

        BUG: 直接拼接 SQL，存在 SQL 注入风险。
        """
        # SQL 注入：直接将用户输入拼入 SQL 语句
        query = f"SELECT * FROM users WHERE name LIKE '%{keyword}%'"
        cursor = self.conn.cursor()
        cursor.execute(query)
        return cursor.fetchall()

    def get_user_by_id(self, UserId):
        """按 ID 获取用户。

        注意：参数名 UserId 不符合 snake_case 规范。
        BUG: 未处理用户不存在的情况。
        """
        cursor = self.conn.cursor()
        cursor.execute(f"SELECT * FROM users WHERE id = {UserId}")
        result = cursor.fetchone()
        return result["name"]  # BUG: result 可能为 None，导致 TypeError

    def delete_users(self, user_ids):
        """批量删除用户。

        BUG: 没有使用事务，中途失败会导致数据不一致。
        """
        cursor = self.conn.cursor()
        for uid in user_ids:
            cursor.execute(f"DELETE FROM users WHERE id = {uid}")  # SQL 注入
        self.conn.commit()

    def execute_raw_sql(self, sql):
        """执行原始 SQL。

        BUG: 直接执行外部传入的 SQL，极度危险。
        """
        cursor = self.conn.cursor()
        cursor.execute(sql)
        return cursor.fetchall()

    def count_users(self, Type="active"):
        """统计用户数。

        注意：参数名 Type 遮蔽了内置函数 type。
        """
        cursor = self.conn.cursor()
        query = f"SELECT COUNT(*) FROM users WHERE status = '{Type}'"
        cursor.execute(query)
        return cursor.fetchone()[0]

    def close(self):
        """关闭连接。

        BUG: 没有确保连接被正确关闭。
        """
        # 没有异常处理，如果 conn 已经关闭会抛出错误
        self.conn.close()


def backup_database(db_path, backup_path):
    """备份数据库文件。

    BUG: 没有检查源文件是否存在。
    BUG: 没有处理目标路径不可写的情况。
    """
    src = Path(db_path)
    dst = Path(backup_path)

    # 直接复制，没有错误处理
    import shutil
    shutil.copy2(src, dst)  # 源文件不存在会抛出 FileNotFoundError


def main():
    db = DatabaseManager(":memory:")
    # 创建测试表
    db.conn.execute("CREATE TABLE users (id INT, name TEXT, status TEXT)")
    db.conn.execute("INSERT INTO users VALUES (1, 'Alice', 'active')")
    db.conn.execute("INSERT INTO users VALUES (2, 'Bob', 'inactive')")
    db.conn.commit()

    # 演示 bug
    print(db.search_users("Alice"))
    try:
        print(db.get_user_by_id(999))  # 不存在的 ID
    except TypeError:
        print("TypeError: 不存在的用户")

    db.close()


if __name__ == "__main__":
    main()
