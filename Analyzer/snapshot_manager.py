# snapshot_manager.py
import os
import pickle
import logging
from typing import Any
import parser_core as Parser
from common_types import Event, Snapshot

logger = logging.getLogger(__name__)

def save_snapshot_cache(snapshot: Snapshot, ts: int | str, output_dir: str):
    """
    将完整的快照数据保存到 Pickle 文件中。
    文件名格式: cache_<timestamp>.pkl 或 cache_final.pkl
    Args:
        snapshot (Snapshot): 要缓存的快照数据。
        ts (int/str): 快照的时间戳，或"final"表示最终快照。
        output_dir (str): 缓存文件保存的目录。
    """
    ts_str = str(ts) if ts != "final" else "final"
    cache_file = os.path.join(output_dir, f"cache_{ts_str}.pkl")
    os.makedirs(output_dir, exist_ok=True)

    # 如果传入的是字典，转换为Snapshot对象
    if isinstance(snapshot, dict):
        snapshot = Snapshot.from_dict(snapshot)
    
    # 确保快照的时间戳与ts一致
    snapshot.timestamp = ts
    
    # 如果 ctx 是 ParserContext 对象，将其转换为字典以便序列化
    if isinstance(snapshot.ctx, Parser.ParserContext):
        ctx_obj = snapshot.ctx
        ctx_dict = {}
        for key, value in ctx_obj.__dict__.items():
            if key == "memory_manager" and hasattr(value, 'to_dict'):
                # 特殊处理 MemoryFragmentManager 对象
                ctx_dict[key] = value.to_dict()
            # 检查其他属性是否为可序列化的基本类型
            elif isinstance(value, (int, float, str, bool, list, dict, type(None))):
                ctx_dict[key] = value
        snapshot.ctx = ctx_dict
    
    # 序列化Snapshot对象
    with open(cache_file, "wb") as f:
        pickle.dump(snapshot.to_dict(), f)
    logger.info(f"快照状态已缓存至: {cache_file}")


def load_latest_cache(output_dir):
    """
    在缓存目录中查找最新的缓存文件并加载。
    返回一个元组 (snapshot, timestamp_str)，其中timestamp_str是时间戳字符串（如'12345'或'final'）。
    如果找不到或加载失败，返回 (None, None)。
    Args:
        output_dir (str): 缓存文件所在的目录。
    Returns:
        tuple: (加载的快照Snapshot对象, 对应的字符串时间戳) 或 (None, None)。
    """
    if not os.path.exists(output_dir):
        return (None, None)

    cache_files = [f for f in os.listdir(output_dir) if f.startswith("cache_") and f.endswith(".pkl")]
    if not cache_files:
        return (None, None)

    # 用于从文件名提取时间戳以便排序的辅助函数
    def extract_ts(filename):
        key = filename[len("cache_"):-4] # 提取 '12345' 或 'final'
        if key == 'final':
            return float('inf') # 确保 'final' 总是最新的
        try:
            return int(key)
        except (ValueError, IndexError):
            return -1 # 无效文件名

    # 找到时间戳最大的缓存文件
    latest_cache_filename = max(cache_files, key=extract_ts)
    # 从文件名提取原始时间戳字符串
    timestamp_str = latest_cache_filename[len("cache_"):-4]   # 去掉前缀和后缀

    cache_path = os.path.join(output_dir, latest_cache_filename)

    logger.info(f"发现最新缓存，正在加载: {cache_path} (时间戳: {timestamp_str})")
    try:
        with open(cache_path, "rb") as f:
            snapshot_data = pickle.load(f)
        
        # 将字典转换为Snapshot对象
        snapshot = Snapshot.from_dict(snapshot_data)
        return (snapshot, timestamp_str)  # 返回快照数据和时间戳
    except (pickle.UnpicklingError, EOFError) as e:
        logger.warning(f"加载缓存失败 {cache_path}: {e}。该缓存将被忽略。")
        # 可以在这里选择删除损坏的缓存文件，但为安全起见，暂时只忽略
        return (None, None)

def load_latest_cache_before(output_dir, timestamp_limit):
    """
    在缓存目录中查找指定时间戳之前的最新缓存文件并加载。
    返回 (snapshot, timestamp_str)。找不到则返回 (None, None)。
    Args:
        output_dir (str): 缓存文件所在的目录。
        timestamp_limit (int): 目标时间戳，函数将查找此时间戳之前的最新缓存。
    Returns:
        tuple: (加载的快照Snapshot对象, 对应的字符串时间戳) 或 (None, None)。
    """
    if not os.path.exists(output_dir):
        return (None, None)

    cache_files = [f for f in os.listdir(output_dir) if f.startswith("cache_") and f.endswith(".pkl")]
    if not cache_files:
        return (None, None)

    # 提取时间戳并过滤掉超过 limit 的文件
    valid_caches = []
    for f in cache_files:
        key = f[len("cache_"):-4]
        if key == 'final':
            continue # 'final' 被认为在所有时间戳之后，所以排除
        try:
            ts = int(key)
            if ts < timestamp_limit:
                valid_caches.append((ts, f))
        except (ValueError, IndexError):
            continue

    if not valid_caches:
        return (None, None)

    # 找到时间戳最大的缓存文件
    latest_ts, latest_cache_filename = max(valid_caches, key=lambda item: item[0])
    timestamp_str = str(latest_ts)

    cache_path = os.path.join(output_dir, latest_cache_filename)

    logger.info(f"为目标 {timestamp_limit} 找到最近的缓存: {cache_path}")
    try:
        with open(cache_path, "rb") as f:
            snapshot_data = pickle.load(f)
        
        # 将字典转换为Snapshot对象
        snapshot = Snapshot.from_dict(snapshot_data)
        return (snapshot, timestamp_str)
    except (pickle.UnpicklingError, EOFError) as e:
        logger.warning(f"加载缓存失败 {cache_path}: {e}。该缓存将被忽略。")
        return (None, None)
    
def clear_all_cache(output_dir):
    """
    删除输出文件夹中所有的缓存文件（cache_{timestamp}.pkl）。
    
    Args:
        output_dir (str): 缓存文件所在的目录。
        
    Returns:
        int: 成功删除的文件数量。
    """
    if not os.path.exists(output_dir):
        logger.warning(f"目录 {output_dir} 不存在。")
        return 0

    cache_files = [f for f in os.listdir(output_dir) if f.startswith("cache_") and f.endswith(".pkl")]
    
    deleted_count = 0
    for cache_file in cache_files:
        cache_path = os.path.join(output_dir, cache_file)
        try:
            os.remove(cache_path)
            # logger.info(f"已删除缓存文件: {cache_path}")
            deleted_count += 1
        except OSError as e:
            logger.warning(f"无法删除缓存文件 {cache_path}: {e}")
    
    return deleted_count