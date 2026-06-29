"""用户管理模块 —— 包含多个故意植入的代码问题，供 Code Review Agent 发现。"""


class Usermanager:
    """用户管理器，负责用户的增删改查。

    注意：类名 Usermanager 不符合 PEP8（应为大驼峰 UserManager）。
    """

    def __init__(self):
        self.users = {}
        self.user_count = 0

    def add_user(self, name, Email):
        """添加用户。

        注意：参数名 Email 不符合 PEP8（应为小写 email）。
        """
        if name == None:  # BUG: 应该用 is None
            raise ValueError("name cannot be None")
        self.user_count = self.user_count + 1
        user_id = self.user_count
        self.users[user_id] = {"name": name, "email": Email}
        return user_id

    def get_user(self, user_id):
        """获取用户信息。"""
        return self.users[user_id]  # BUG: 未处理 KeyError

    def delete_user(self, user_id):
        """删除用户。"""
        del self.users[user_id]  # BUG: 未处理 KeyError
        self.user_count -= 1

    def search_users(self, keyword):
        """搜索用户。"""
        results = []
        for id in self.users:  # 变量名 id 遮蔽了内置函数
            user = self.users[id]
            if keyword in user["name"] or keyword in user["email"]:
                results.append(user)
        return results

    def update_email(self, user_id, new_email):
        """更新用户邮箱。"""
        # BUG: 没有校验 email 格式
        self.users[user_id]["email"] = new_email


def main():
    manager = Usermanager()
    manager.add_user("Alice", "alice@example.com")
    manager.add_user("Bob", "bob@example.com")

    # 演示 bug：获取不存在的用户会抛出未捕获的 KeyError
    user = manager.get_user(999)
    print(user)


if __name__ == "__main__":
    main()
