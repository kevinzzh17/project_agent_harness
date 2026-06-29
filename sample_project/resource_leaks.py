"""资源管理模块 —— 包含资源泄漏、上下文管理等问题，供 Code Review Agent 检测。"""

import os
import threading
import tempfile


class FileManager:
    """文件管理器。

    BUG: 打开的文件句柄没有正确关闭，存在资源泄漏。
    """

    def __init__(self, filepath):
        self.filepath = filepath
        # BUG: 打开文件但不使用 with 语句，没有 __exit__ 或 close 方法
        self.f = open(filepath, "r")  # 资源泄漏

    def read_line(self):
        """读取一行。"""
        return self.f.readline()

    def read_all(self):
        """读取全部内容。"""
        # BUG: 每次调用都重新读取，没有 seek(0)
        return self.f.read()


class ConnectionPool:
    """连接池（有问题的实现）。

    BUG: 线程不安全，可能导致竞态条件。
    BUG: 没有连接数量限制，可能导致资源耗尽。
    """

    def __init__(self):
        self._pool = []
        self._lock = threading.Lock()

    def get_connection(self):
        """获取连接。

        BUG: 获取锁后如果创建连接失败，锁不会被释放。
        """
        self._lock.acquire()  # BUG: 没有 try-finally，异常时锁不释放
        if self._pool:
            return self._pool.pop()
        # BUG: 没有连接数限制
        return self._create_connection()

    def return_connection(self, conn):
        """归还连接。"""
        self._pool.append(conn)

    def _create_connection(self):
        """创建新连接（模拟）。"""
        return {"id": id(self), "active": True}


def write_temp_data(data):
    """写入临时数据。

    BUG: 临时文件没有清理，会堆积在系统临时目录。
    """
    # BUG: 创建临时文件但不删除
    f = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".tmp")
    f.write(data)
    f.close()  # 关闭了但不删除，临时文件残留
    return f.name


def process_large_file(filepath):
    """处理大文件。

    BUG: 一次性读取整个文件到内存，可能导致内存溢出。
    """
    with open(filepath, "r") as f:
        content = f.read()  # BUG: 大文件应该逐行读取
    return [line.strip() for line in content.split("\n")]


class Cache:
    """简单的缓存实现。

    BUG: 缓存没有过期机制，可能导致内存持续增长。
    BUG: 没有线程安全保护。
    """

    def __init__(self, max_size=100):
        self.max_size = max_size
        self._data = {}

    def get(self, key):
        """获取缓存值。"""
        return self._data.get(key)

    def set(self, key, value):
        """设置缓存值。

        BUG: 超过 max_size 时直接报错而非淘汰旧数据。
        BUG: 使用可变默认参数。
        """
        if len(self._data) >= self.max_size:
            raise MemoryError("Cache full")  # BUG: 不应该是 MemoryError
        self._data[key] = value

    def clear(self):
        """清空缓存。"""
        self._data.clear()

    def get_stats(self, detailed=False):
        """获取缓存统计信息。

        BUG: 使用可变默认参数。
        """
        stats = {"size": len(self._data), "max_size": self.max_size}
        if detailed:
            stats["keys"] = list(self._data.keys())
        return stats


def batch_process(files, callback=[]):
    """批量处理文件。

    注意：参数 callback 使用可变默认参数（列表）。
    BUG: 可变默认参数在函数定义时只创建一次，多次调用会共享同一个列表。
    BUG: 没有处理文件不存在的情况。
    """
    results = callback  # BUG: 直接使用默认参数引用
    for f in files:
        try:
            with open(f, "r") as fh:
                results.append(callback and fh.read())
        except FileNotFoundError:
            pass  # BUG: 静默跳过
    return results


def main():
    # 演示资源泄漏
    import tempfile
    tmp = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt")
    tmp.write("hello\nworld\n")
    tmp.close()

    fm = FileManager(tmp.name)
    print(fm.read_line())
    # BUG: 没有 fm.close() 或 with 语句，文件句柄泄漏

    # 演示临时文件残留
    path = write_temp_data("temporary data")
    print(f"Temp file at: {path}")  # 不会被自动清理

    # 清理
    os.unlink(tmp.name)
    os.unlink(path)


if __name__ == "__main__":
    main()
