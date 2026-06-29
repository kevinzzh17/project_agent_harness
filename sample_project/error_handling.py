"""错误处理模块 —— 包含多种错误处理问题，供 Code Review Agent 检测。"""

import json
import sys


def parse_json_safe(data):
    """安全解析 JSON。

    BUG: 捕获了过于宽泛的异常，且吞掉了错误信息。
    """
    try:
        return json.loads(data)
    except:  # BUG: 裸 except，会捕获所有异常包括 KeyboardInterrupt
        pass  # BUG: 吞掉异常，不记录也不重新抛出


def divide_numbers(a, b):
    """除法运算。

    BUG: 捕获异常后返回 None，调用方难以区分"结果为 None"和"出错"。
    """
    try:
        return a / b
    except ZeroDivisionError:
        return None  # BUG: 返回 None 而非抛出异常或返回默认值


def read_config(filepath):
    """读取配置文件。

    BUG: 捕获 Exception 后打印错误但继续执行，返回了未定义的变量。
    """
    try:
        with open(filepath, "r") as f:
            config = json.load(f)
    except Exception as e:
        print(f"Error reading config: {e}")
        # BUG: 没有设置 config 的默认值，下面的 return 会抛出 NameError
    return config  # BUG: 如果异常发生，config 未定义


def process_items(items):
    """处理列表中的项目。

    BUG: 异常处理过于笼统，且在循环中捕获异常会跳过错误项但不会告知。
    """
    results = []
    for item in items:
        try:
            results.append(process_single(item))
        except Exception:
            pass  # BUG: 静默跳过失败项，不记录任何信息
    return results


def process_single(item):
    """处理单个项目（内部函数）。"""
    return item * 2


def retry_operation(func, max_retries=3):
    """重试操作。

    BUG: 重试逻辑没有指数退避，可能导致短时间内大量请求。
    BUG: 捕获了所有异常，包括不应该重试的异常。
    """
    for i in range(max_retries):
        try:
            return func()
        except:  # BUG: 裸 except
            if i == max_retries - 1:
                raise  # BUG: 这里 raise 的是最后一次的异常，但前面被裸 except 吞掉了类型信息
    return None  # BUG: 理论上不会执行到这里，但如果 func 返回 None 会混淆


def validate_input(value, expected_type):
    """验证输入类型。

    BUG: 使用 assert 做运行时校验，在 python -O 下会被移除。
    """
    assert isinstance(value, expected_type), f"Expected {expected_type}, got {type(value)}"
    assert value is not None  # BUG: assert 可能被优化掉
    return value


def safe_get(d, key, default=None):
    """安全获取字典值。

    BUG: 使用 == None 而非 is None。
    BUG: 逻辑错误：当 key 存在但值为 None 时，返回 default 而非 None。
    """
    if d.get(key) == None:  # PEP8 E711
        return default
    return d.get(key)


def main():
    # 演示各种 bug
    print(parse_json_safe("invalid json"))  # 返回 None（被吞掉的异常）

    print(divide_numbers(10, 0))  # 返回 None

    try:
        print(read_config("/nonexistent/config.json"))
    except NameError:
        print("NameError: config 未定义")

    print(safe_get({"a": 1, "b": None}, "b", "default"))  # 返回 "default" 而非 None


if __name__ == "__main__":
    main()
