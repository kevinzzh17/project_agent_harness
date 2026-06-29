"""计算器模块 —— 包含多个故意植入的问题。"""

import math
import os  # 未使用的导入


def divide(a, b):
    """除法运算。

    BUG: 没有处理除零异常。
    """
    return a / b


def calculate_average(numbers):
    """计算平均值。

    BUG: 没有处理空列表的情况。
    """
    total = sum(numbers)
    return total / len(numbers)


def factorial(n):
    """计算阶乘。

    BUG: 没有处理负数输入。
    """
    if n == 0:
        return 1
    result = 1
    for i in range(1, n + 1):
        result *= i
    return result


class Calculator:
    def __init__(self):
        self.history = []

    def add(self, x, Y):  # 参数名 Y 不符合 PEP8
        """加法。"""
        result = x + Y
        self.history.append(f"{x} + {Y} = {result}")
        return result

    def sqrt(self, x):
        """开平方。

        BUG: 没有处理负数输入，math.sqrt 会抛出 ValueError。
        """
        return math.sqrt(x)


def main():
    calc = Calculator()
    print(calc.add(1, 2))
    print(divide(10, 0))  # 会抛出 ZeroDivisionError
    print(calculate_average([]))  # 会抛出 ZeroDivisionError


if __name__ == "__main__":
    main()
