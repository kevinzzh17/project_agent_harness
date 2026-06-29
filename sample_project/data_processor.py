"""数据处理模块。"""

import json
import pickle  # 不安全：pickle 反序列化存在安全风险


def load_data(filepath):
    """从文件加载数据。

    BUG: 直接使用 pickle.load 加载不受信任的数据，存在远程代码执行风险。
    """
    with open(filepath, "rb") as f:
        return pickle.load(f)


def save_data(data, filepath):
    """保存数据到文件。"""
    with open(filepath, "wb") as f:
        pickle.dump(data, f)


def parse_config(config_str):
    """解析 JSON 配置字符串。

    BUG: 没有 try-except，无效 JSON 会抛出未捕获的 JSONDecodeError。
    """
    return json.loads(config_str)


def find_max(numbers):
    """找出最大值。

    BUG: 空列表会抛出 ValueError。
    """
    return max(numbers)


class DataProcessor:
    def __init__(self):
        self.data = None
        self.Processed = False  # 变量名不符合 PEP8

    def process(self, input_data):
        """处理数据。"""
        self.data = input_data
        # TODO: 实现实际的处理逻辑
        self.Processed = True
        return self.data

    def export_json(self):
        """导出为 JSON。"""
        # BUG: 没有处理 self.data 为 None 的情况
        return json.dumps(self.data)


def main():
    processor = DataProcessor()
    result = processor.export_json()  # self.data 是 None
    print(result)


if __name__ == "__main__":
    main()
