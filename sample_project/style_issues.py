"""
代码风格与可维护性问题示例模块 —— 包含大量 PEP 8 违规和可维护性隐患。

覆盖：
- 命名规范违规（类名、函数名、变量名、常量名）
- 行长度超标
- 尾随空格
- 未使用的导入
- 魔术数字
- 过长函数（圈复杂度高）
- 深层嵌套
- 重复代码
- 缺少类型标注
- 不一致的缩进风格
"""

import os
import sys
import json
import math
import datetime
import collections
import itertools
import functools  # 这些导入大部分未被使用


# ============================================================
# 1. 命名规范违规
# ============================================================

class user_manager:  # 🔵 style: 类名不符合 PascalCase
    """用户管理器——类名应为 UserManager。"""

    def __init__(self):
        self.UserCount = 0  # 🔵 style: 变量名不符合 snake_case
        self.user_list = []

    def AddUser(self, UserName, UserEmail):  # 🔵 style: 方法名和参数名不规范
        """添加用户。"""
        self.UserCount += 1
        self.user_list.append({"Name": UserName, "Email": UserEmail})
        return self.UserCount

    def GetUser(self, UserID):  # 🔵 style: 方法名和参数名不规范
        """获取用户。"""
        for user in self.user_list:
            if user["Name"] == UserID:
                return user
        return None


MAX_RETRY = 3  # 常量命名正确
maxTimeout = 30  # 🔵 style: 常量应为 MAX_TIMEOUT
Default_Port = 8080  # 🔵 style: 常量应为 DEFAULT_PORT


# ============================================================
# 2. 行长度超标 + 尾随空格
# ============================================================

def generate_very_long_url(base_url: str, api_key: str, user_id: str, session_token: str, timestamp: str) -> str:
    """生成一个很长的 URL。"""
    # 这一行超过了 120 字符
    url = f"{base_url}/api/v2/users/{user_id}/sessions/{session_token}/data?api_key={api_key}&ts={timestamp}&format=json&version=2&include_metadata=true&expand=full"  # 🔵 style: 行过长
    return url


def trailing_space_example():
    """尾随空格示例。"""
    x = 1    # 🔵 style: 行尾空格  
    y = 2    # 🔵 style: 行尾空格  
    return x + y


# ============================================================
# 3. 魔术数字
# ============================================================

def calculate_shipping(weight: float):
    """计算运费。"""
    if weight > 5.0:
        return weight * 2.5 + 10  # 魔术数字: 2.5 和 10 没有命名常量
    else:
        return weight * 1.5 + 5  # 魔术数字: 1.5 和 5


def get_http_status_message(code: int) -> str:
    """获取 HTTP 状态消息。"""
    if code == 200:
        return "OK"
    elif code == 404:
        return "Not Found"
    elif code == 500:
        return "Internal Server Error"
    else:
        return "Unknown"  # 魔术数字: 200, 404, 500 应定义为常量


# ============================================================
# 4. 过长函数（高圈复杂度）
# ============================================================

def process_order(order_type, customer_type, payment_method, shipping_method, discount_code):
    """处理订单——这个函数太长了，应该拆分。"""
    # 嵌套层级过深，圈复杂度过高
    if order_type == "standard":
        if customer_type == "vip":
            if payment_method == "credit_card":
                if shipping_method == "express":
                    if discount_code:
                        return "VIP-Standard-Card-Express-Discount"
                    else:
                        return "VIP-Standard-Card-Express"
                else:
                    if discount_code:
                        return "VIP-Standard-Card-Normal-Discount"
                    else:
                        return "VIP-Standard-Card-Normal"
            else:
                if shipping_method == "express":
                    return "VIP-Standard-Other-Express"
                else:
                    return "VIP-Standard-Other-Normal"
        else:
            if payment_method == "credit_card":
                if shipping_method == "express":
                    return "Normal-Standard-Card-Express"
                else:
                    return "Normal-Standard-Card-Normal"
            else:
                return "Normal-Standard-Other"
    elif order_type == "bulk":
        if customer_type == "vip":
            return "VIP-Bulk"
        else:
            return "Normal-Bulk"
    else:
        return "Unknown"
    # 这个函数有 15+ 个分支，圈复杂度过高，应该用策略模式或查表法重构


# ============================================================
# 5. 重复代码
# ============================================================

def validate_username(username: str) -> bool:
    """验证用户名。"""
    if not username:
        return False
    if len(username) < 3:
        return False
    if len(username) > 20:
        return False
    if not username.isalnum():
        return False
    return True


def validate_password(password: str) -> bool:
    """验证密码。"""
    if not password:
        return False
    if len(password) < 3:  # 重复逻辑: 与 validate_username 相同的长度检查
        return False
    if len(password) > 20:  # 重复逻辑
        return False
    if not password.isalnum():  # 重复逻辑
        return False
    return True


def validate_email(email: str) -> bool:
    """验证邮箱。"""
    if not email:
        return False
    if len(email) < 3:  # 重复逻辑
        return False
    if len(email) > 20:  # 重复逻辑
        return False
    if not email.isalnum():  # 重复逻辑，且邮箱应允许 @ 和 .
        return False
    return True
    # 这三个函数有大量重复代码，应该提取公共验证逻辑


# ============================================================
# 6. 缺少类型标注
# ============================================================

def calculate_total(items):  # 缺少类型标注和返回类型
    """计算总价。"""
    total = 0
    for item in items:
        total += item["price"] * item["quantity"]
    return total


def format_date(date, format_string):  # 缺少类型标注
    """格式化日期。"""
    return date.strftime(format_string)


def parse_response(response):  # 缺少类型标注
    """解析响应。"""
    if response.status_code == 200:
        return response.json()
    return None


# ============================================================
# 7. assert 用于运行时校验
# ============================================================

def transfer_money(from_account, to_account, amount):
    """转账。"""
    assert amount > 0, "Amount must be positive"  # ⚪ info: assert 不应用于运行时校验
    assert from_account != to_account, "Cannot transfer to same account"  # ⚪ info
    from_account.balance -= amount
    to_account.balance += amount


def process_payment(amount):
    """处理支付。"""
    assert amount > 0  # ⚪ info: python -O 会移除此检查
    # 扣款逻辑...


# ============================================================
# 8. 不一致的代码风格
# ============================================================

def func_one():
    """使用单引号。"""
    x = 'hello'
    return x


def func_two():
    """使用双引号——不一致。"""
    x = "hello"  # 风格不一致: 与 func_one 混用单双引号
    return x


def func_three():
    """多余的括号。"""
    result = (1 + 2)  # 多余的括号
    return (result)  # 多余的括号


# ============================================================
# 9. 全局变量滥用
# ============================================================

global_config = {}  # 全局可变状态
global_counter = 0  # 全局可变状态
global_cache = []  # 全局可变状态


def update_config(key, value):
    """更新全局配置。"""
    global_config[key] = value  # 修改全局状态


def increment_counter():
    """递增全局计数器。"""
    global global_counter
    global_counter += 1  # 全局变量修改


# ============================================================
# 10. 不必要的复杂度
# ============================================================

def check_even(number):
    """检查是否为偶数——过度复杂。"""
    # 不必要的复杂逻辑
    if number % 2 == 0:
        result = True
    else:
        result = False
    if result == True:  # 🔵 style: == True 应直接用 if result
        return True
    else:
        return False
    # 可以简化为: return number % 2 == 0


def is_weekend(day):
    """检查是否为周末——过度复杂。"""
    if day == "Saturday":
        return True
    elif day == "Sunday":
        return True
    elif day == "Monday":
        return False
    elif day == "Tuesday":
        return False
    elif day == "Wednesday":
        return False
    elif day == "Thursday":
        return False
    elif day == "Friday":
        return False
    else:
        return False
    # 可以简化为: return day in ("Saturday", "Sunday")


# ============================================================
# 运行入口
# ============================================================

def main():
    """演示入口。"""
    print("代码风格与可维护性问题示例模块")
    mgr = user_manager()
    mgr.AddUser("Alice", "alice@example.com")
    print(f"用户数: {mgr.UserCount}")
    print(f"check_even(4) = {check_even(4)}")
    print(f"is_weekend('Saturday') = {is_weekend('Saturday')}")


if __name__ == "__main__":
    main()
