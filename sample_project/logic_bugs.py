"""
复杂业务逻辑 Bug 示例模块 —— 包含隐蔽的逻辑错误和边界条件问题。

这些 Bug 不会被简单的规则引擎检测出来，但 LLM 语义分析可以发现：
- 离一错误（off-by-one）
- 浮点数精度问题
- 类型混淆
- 逻辑条件反转
- 未处理的边界情况
- 并发安全问题
- 幂等性缺失
"""

from typing import Optional


# ============================================================
# 1. 离一错误（Off-by-one）
# ============================================================

def get_range(start: int, end: int):
    """生成从 start 到 end 的整数列表（含两端）。

    Bug: 应该是 range(start, end + 1)，但写成了 range(start, end)，
    导致 end 不包含在结果中。用户期望 [1,2,3,4,5]，实际得到 [1,2,3,4]。
    """
    return list(range(start, end))  # 逻辑 Bug: 少了一个元素


def paginate(items: list, page: int, per_page: int = 10):
    """分页获取数据。

    Bug: 起始索引计算错误。应该是 (page - 1) * per_page，
    但写成了 page * per_page，导致第一页被跳过。
    """
    start = page * per_page  # 逻辑 Bug: 应该是 (page - 1) * per_page
    end = start + per_page
    return items[start:end]


# ============================================================
# 2. 浮点数精度问题
# ============================================================

def calculate_discount(price: float, discount_percent: float) -> float:
    """计算折扣价。

    Bug: 浮点数直接比较，0.1 + 0.2 != 0.3 在浮点数中不成立。
    应使用 Decimal 或 round。
    """
    discounted = price * (1 - discount_percent / 100)
    # Bug: 浮点数精度问题，例如 100 * 0.9 可能得到 89.99999999999999
    return discounted


def compare_floats(a: float, b: float) -> bool:
    """比较两个浮点数是否相等。

    Bug: 直接用 == 比较浮点数，由于精度问题可能产生错误结果。
    """
    return a == b  # 逻辑 Bug: 浮点数不应直接比较


# ============================================================
# 3. 类型混淆
# ============================================================

def add_values(a, b):
    """将两个值相加。

    Bug: 没有类型检查。如果 a 是 int, b 是 str 会抛出 TypeError。
    用户可能期望自动转换或抛出明确的错误信息。
    """
    return a + b  # 潜在 TypeError


def process_ids(id_list):
    """处理 ID 列表，返回字符串。

    Bug: 如果列表中有 None 或非 int 类型，join 会失败。
    """
    str_ids = [str(i) for i in id_list]
    return "-".join(str_ids)  # 如果 id_list 中有 None，str(None) = "None"


# ============================================================
# 4. 逻辑条件反转
# ============================================================

def is_adult(age: int) -> bool:
    """判断是否成年（>= 18 岁）。

    Bug: 条件写反了，应该是 age >= 18，但写成了 age <= 18。
    """
    return age <= 18  # 逻辑 Bug: 条件反转


def is_valid_email(email: str) -> bool:
    """简单检查邮箱是否有效。

    Bug: 逻辑反转，应该是 '@' in email，但写成了 '@' not in email。
    """
    return "@" not in email  # 逻辑 Bug: 条件反转


def should_grant_access(user_role: str, resource_level: str) -> bool:
    """判断用户是否有权限访问资源。

    Bug: 逻辑错误。admin 应该有权限，但条件导致 admin 被拒绝。
    """
    if user_role == "admin":
        return False  # 逻辑 Bug: admin 应该返回 True
    return resource_level == "public"


# ============================================================
# 5. 未处理的边界情况
# ============================================================

def find_max(numbers: list):
    """找出列表中的最大值。

    Bug: 空列表会抛出 ValueError。
    """
    return max(numbers)  # 边界 Bug: 空列表崩溃


def binary_search(arr: list, target):
    """二分查找。

    Bug: 没有检查数组是否为空，且没有处理 target 不存在的情况。
    """
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1  # 没问题，但如果 arr 为空，right = -1，循环不会执行，返回 -1（正确）
    # 真正的 Bug: 没有检查 arr 是否排序，二分查找要求有序数组


def merge_sorted_lists(list1: list, list2: list) -> list:
    """合并两个已排序列表。

    Bug: 没有验证输入列表确实已排序。如果传入未排序列表，结果错误但不报错。
    """
    result = []
    i = j = 0
    while i < len(list1) and j < len(list2):
        if list1[i] <= list2[j]:
            result.append(list1[i])
            i += 1
        else:
            result.append(list2[j])
            j += 1
    result.extend(list1[i:])
    result.extend(list2[j:])
    return result


# ============================================================
# 6. 并发安全问题
# ============================================================

class Counter:
    """线程不安全的计数器。

    Bug: self.count += 1 不是原子操作，多线程下会丢失更新。
    应使用 threading.Lock 或 itertools.count。
    """

    def __init__(self):
        self.count = 0

    def increment(self):
        """递增计数器。"""
        self.count += 1  # 并发 Bug: 非原子操作

    def get_value(self):
        """获取当前值。"""
        return self.count


class Cache:
    """简单的字典缓存。

    Bug: 多线程读写 dict 不是线程安全的，可能数据损坏。
    """

    def __init__(self):
        self._store = {}

    def get(self, key):
        """获取缓存值。"""
        return self._store.get(key)

    def set(self, key, value):
        """设置缓存值。"""
        self._store[key] = value  # 并发 Bug: 非线程安全


# ============================================================
# 7. 幂等性缺失
# ============================================================

class OrderProcessor:
    """订单处理器。

    Bug: process_order 没有幂等性检查，重复调用会重复扣款。
    """

    def __init__(self):
        self.processed_orders = set()

    def process_order(self, order_id: str, amount: float):
        """处理订单付款。

        Bug: 没有检查 order_id 是否已处理，重复调用会重复执行。
        """
        # 应该先检查: if order_id in self.processed_orders: return
        print(f"Processing order {order_id}, amount: {amount}")
        # 扣款逻辑...
        self.processed_orders.add(order_id)
        return "success"


# ============================================================
# 8. 错误的异常处理
# ============================================================

def read_config_file(filepath: str) -> dict:
    """读取 JSON 配置文件。

    Bug: 捕获了过于宽泛的 Exception，且返回了不一致的类型
    （成功返回 dict，失败返回 None），调用方需要额外处理。
    """
    import json
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except Exception:  # Bug: 过于宽泛的异常捕获
        return None  # Bug: 返回类型不一致


def convert_to_int(value):
    """将值转为整数。

    Bug: 捕获了所有异常但只是打印，没有处理，程序继续以错误状态运行。
    """
    try:
        return int(value)
    except Exception as e:
        print(f"Error: {e}")  # Bug: 只打印不处理，返回 None
        # 调用方不知道返回了 None


# ============================================================
# 9. 资源管理问题
# ============================================================

class FileHandler:
    """文件处理器。

    Bug: open 后没有在 finally 中 close，如果处理过程抛异常则文件泄漏。
    """

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.file = None

    def open(self):
        """打开文件。"""
        self.file = open(self.filepath, "r")  # Bug: 没有异常保护

    def read_all(self):
        """读取全部内容。"""
        return self.file.read()

    def close(self):
        """关闭文件。"""
        if self.file:
            self.file.close()


# ============================================================
# 10. 状态管理 Bug
# ============================================================

class Stack:
    """栈数据结构。

    Bug: pop 和 peek 没有检查栈是否为空，空栈操作会抛出 IndexError。
    """

    def __init__(self):
        self._items = []

    def push(self, item):
        """入栈。"""
        self._items.append(item)

    def pop(self):
        """出栈。

        Bug: 空栈没有处理，会抛出 IndexError。
        """
        return self._items.pop()  # Bug: 空栈崩溃

    def peek(self):
        """查看栈顶元素。

        Bug: 空栈没有处理。
        """
        return self._items[-1]  # Bug: 空栈崩溃

    def is_empty(self) -> bool:
        """检查是否为空。"""
        return len(self._items) == 0


# ============================================================
# 运行入口
# ============================================================

def main():
    """演示入口。"""
    print("复杂业务逻辑 Bug 示例模块")

    # 离一错误演示
    print(f"get_range(1, 5) = {get_range(1, 5)}")  # 期望 [1,2,3,4,5]，实际 [1,2,3,4]

    # 条件反转演示
    print(f"is_adult(25) = {is_adult(25)}")  # 期望 True，实际 False

    # 边界情况
    try:
        print(f"find_max([]) = {find_max([])}")  # 崩溃
    except ValueError as e:
        print(f"find_max([]) 崩溃: {e}")


if __name__ == "__main__":
    main()
