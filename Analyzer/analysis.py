"""
Copyright (c) 2026, Chen Jie, Joungtao, Xuzheng Jiang
All rights reserved.
This source code is licensed under the BSD-2-Clause license found in the
LICENSE file in the root directory of this source tree.
"""

# analysis.py
import logging
import os
from typing import Any

from common_types import Event, CallStack, StackFrame

logger = logging.getLogger(__name__)

def impact_score(frag_ratio: float, free_ratio: float) -> float:
    """
    计算内存影响分数。
    Args:
        frag_ratio (float): 碎片率
        free_ratio (float): 空闲率
    Returns:
        float: 影响分数
    """
    return frag_ratio * (1 - free_ratio)
    # return frag_ratio

def merge_fragmentation_into_events(events: list[Event], frag_data: list[dict[str, Any]]) -> list[Event]:
    """
    将碎片率和空闲率数据合并到事件列表中。
    """
    frag_dict = {entry["timestamp"]: entry["fragmentation_ratio"] for entry in frag_data}
    free_dict = {entry["timestamp"]: entry["free_ratio"] for entry in frag_data}

    return [
        Event(
            time=event.time,
            operation=event.operation,
            range=event.range,
            size=event.size,
            callstack_path=event.callstack_path,
            alloc_at=event.alloc_at,
            free_at=event.free_at,
            fragmentation_ratio=(frag_ratio := frag_dict.get(event.time)),
            free_ratio=(free_ratio := free_dict.get(event.time)),
            impact_score=(
                round(impact_score(frag_ratio, free_ratio), 4)
                if frag_ratio is not None and free_ratio is not None
                else None
            )
        )
        for event in events
    ]

def find_peaks(frag_data: list[dict[str, Any]], window: int = 500) -> list[int]:
    """
    从 fragmentation_data 中找到局部极大值时间点列表。
    峰值是根据 impact_score = fragmentation_ratio * used_ratio 来确定的。
    如果数据点太少无法使用窗口检测，则返回全局最大值点的时间戳。
    Args:
        frag_data (list): 包含 'timestamp', 'fragmentation_ratio', 'free_ratio' 的字典列表。
        window (int): 局部极大值检测中左右各比较的数据点数量。
    Returns:
        list: 局部极大值的时间戳列表。
    """
    # 使用列表推导式和海象运算符，更紧凑地完成数据过滤和 impact_score 计算
    valid_data = [
        {**d, "impact_score": impact_score(frag_ratio, free_ratio)}
        for d in frag_data
        if (frag_ratio := d.get("fragmentation_ratio")) is not None
        and (free_ratio := d.get("free_ratio")) is not None
    ]

    if not valid_data:
        logger.warning("在 frag_data 中未找到有效的 fragmentation_ratio 和 free_ratio 数据，无法检测峰值。")
        return []

    n = len(valid_data)
    logger.info(f"使用 impact_score 指标进行峰值检测。有效数据点: {n}, 窗口大小: {window}")
    # 如果数据点太少无法使用窗口检测，则回退到查找全局最大值
    if n < 2 * window + 1:
        logger.warning(f"有效数据点 ({n}) 过少，无法使用窗口 ({window}) 检测局部峰值。将返回全局 impact_score 最高点。")
        return _get_global_max_timestamp(valid_data)

    # 如果数据足够，则执行局部极大值检测逻辑
    peaks = []
    # 使用 impact_score 进行比较
    scores = [entry["impact_score"] for entry in valid_data]
    times  = [entry["timestamp"] for entry in valid_data]
    
    # 检查所有可能的峰值点，包括开头和结尾的部分
    for i in range(n):
        curr = scores[i]
        # 确定左右窗口的边界
        left_start = max(0, i - window)
        left_end = i
        right_start = i + 1
        right_end = min(n, i + window + 1)
        
        # 检查当前点是否大于或等于其左右窗口内的所有点
        # 并且是窗口内第一个达到最大值的点（处理相同值的情况）
        left_max = max(scores[j] for j in range(left_start, left_end)) if left_start < left_end else float('-inf')
        right_max = max(scores[j] for j in range(right_start, right_end)) if right_start < right_end else float('-inf')
        
        # 当前点是峰值，如果它大于或等于左右窗口的最大值
        # 并且是窗口内第一个达到此值的点（避免重复记录相同的峰值）
        if curr >= left_max and curr >= right_max:
            # 检查是否是窗口内第一个达到此值的点
            is_first_in_left = all(curr > scores[j] for j in range(left_start, left_end))
            is_first_in_right = all(curr >= scores[j] for j in range(right_start, right_end))
            
            # 如果是窗口内第一个达到此值的点，或者是唯一达到此值的点
            if is_first_in_left or (left_start == i):
                peaks.append(times[i])
    
    if not peaks:
        logger.warning(f"使用窗口 ({window}) 未检测到局部峰值。将返回全局 impact_score 最高点。")
        return _get_global_max_timestamp(valid_data)
    return peaks

def _get_global_max_timestamp(valid_data):
    """
    获取全局 impact_score 最高点的时间戳。
    假设 valid_data 中的每个条目都已经计算了 'impact_score'。
    """
    if not valid_data:
        return []
    max_entry = max(valid_data, key=lambda entry: entry.get("impact_score", 0))
    return [max_entry["timestamp"]]
def build_flame_graph(events: list[Event], stack_frame_map: dict[int, StackFrame], total=1000):
    """
    根据内存事件构建火焰图数据结构。
    Args:
        events (list[Event]): 包含 'callstack_path' 信息的事件对象列表。
        stack_frame_map (dict[int, StackFrame]): 栈帧ID到StackFrame对象的映射
        total (int): 火焰图根节点的值，用于比例计算。
    Returns:
        dict: 火焰图的根节点数据结构。
    """
    root = {"name": "root", "id": 0, "count": 0, "children": [], "_name_map": {}}
    node_counter = 1

    for event in events:
        # 从事件中获取调用栈路径
        callstack_path = event.callstack_path
        if not callstack_path:
            continue

        # 将 frame_id 转换为 StackFrame 对象，并创建描述性名称
        stack = []
        for frame_id in callstack_path:
            frame = stack_frame_map.get(frame_id)
            if frame:
                # 创建描述性名称，包含函数名、文件名和行号
                func_name = f"{frame.func} ({os.path.basename(frame.file)}:{frame.line})"
                stack.append(func_name)
            else:
                # 如果找不到对应的 StackFrame，使用默认名称
                stack.append(f"<unknown_frame_{frame_id}>")
        if not stack:
            continue

        reversed_stack = list(reversed(stack)) # 火焰图通常从根开始显示最底层调用
        current_node = root
        current_node["count"] += 1

        for func_name in reversed_stack:
            if func_name not in current_node["_name_map"]:
                next_node = {
                    "name": func_name,
                    "id": node_counter,
                    "count": 0,
                    "value": -1, # 临时值，后续计算
                    "children": [],
                    "_name_map": {}, # 临时映射，用于快速查找子节点
                }
                node_counter += 1
                current_node["children"].append(next_node)
                current_node["_name_map"][func_name] = next_node
            current_node = current_node["_name_map"][func_name]
            current_node["count"] += 1

    def calculate_value(node, parent_value):
        """递归计算火焰图中每个节点的值（比例）。"""
        node["value"] = parent_value
        children = node.get("children", [])
        total_children_count = sum(child["count"] for child in children)

        for child in children:
            if total_children_count > 0:
                # 按照子节点计数占总子节点计数的比例分配父节点的值
                child_value = round(parent_value * (child["count"] / total_children_count), 2)
                calculate_value(child, child_value)
            else:
                calculate_value(child, 0) # 如果没有子节点，则分配0或其自身的值

        # 清理临时字段
        node.pop("count", None)
        node.pop("_name_map", None)

    # 从根节点开始计算值
    calculate_value(root, total)
    return root

def filter_events_by_memory_regions(
    events: list[Event],
    memory_regions: list[tuple[int, int]]
) -> list[Event]:
    """
    根据内存区域过滤事件，只保留对这些区域进行操作的事件。

    Args:
        events (list): 事件对象列表。
        memory_regions (list): 内存区域列表，每个区域是(start, end)元组。

    Returns:
        list: 过滤后的事件列表。
    """
    if not memory_regions or not events:
        return events

    return [
        event for event in events
        if (parsed_range := _parse_range(event.range))
        and any(
            # 检查事件范围与内存区域是否重叠
            max(parsed_range[0], region_start) < min(parsed_range[1], region_end)
            for region_start, region_end in memory_regions
        )
    ]

def _parse_range(range_str: str) -> tuple[int, int] | None:
    """
    解析 "start-end" 格式的字符串，支持十进制和十六进制。
    返回一个 (start, end) 的元组。
    """
    try:
        parts = range_str.split('-')
        if len(parts) != 2:
            return None
        
        start_str, end_str = parts
        
        # 自动判断是十六进制还是十进制
        base_start = 16 if start_str.startswith('0x') else 10
        base_end = 16 if end_str.startswith('0x') else 10
        
        start = int(start_str, base_start)
        end = int(end_str, base_end)
        
        return start, end
    except (ValueError, IndexError):
        logger.warning(f"无法解析内存范围字符串: '{range_str}'")
        return None

def calculate_focus_regions_from_events(
    recent_events: list[Event], 
    num_events: int, 
    context_size: int
) -> list[tuple[int, int]]:
    """
    根据最近的事件计算并合并感兴趣的内存区域（焦点区域）。

    Args:
        recent_events (list[Event]): 事件对象列表。
        num_events (int): 要关注的最后几个事件的数量。
        context_size (int): 在事件操作地址周围扩展的上下文大小（字节）。

    Returns:
        list[tuple[int, int]]: 合并后、排序过的焦点区域列表。
    """
    if not recent_events or num_events <= 0:
        return []

    # 使用列表推导式来生成感兴趣的内存区域
    events_to_check = recent_events[-num_events:]
    regions_of_interest = [
        (max(0, start - context_size), end + context_size)
        for event in events_to_check
        if (parsed_range := _parse_range(event.range))
        and (start := parsed_range[0]) is not None
        and (end := parsed_range[1]) is not None
    ]

    if not regions_of_interest:
        logger.warning("在最近的事件中未找到有效的内存范围，无法计算焦点区域。")
        return []

    # 合并重叠的感兴趣区域
    regions_of_interest.sort(key=lambda x: x[0])
    focus_regions: list[tuple[int, int]] = []
    if regions_of_interest:
        current_start, current_end = regions_of_interest[0]
        for next_start, next_end in regions_of_interest[1:]:
            if next_start < current_end:
                current_end = max(current_end, next_end)
            else:
                focus_regions.append((current_start, current_end))
                current_start, current_end = next_start, next_end
        focus_regions.append((current_start, current_end))
    
    logger.info(f"已确定关注的内存区域: {focus_regions}")
    return focus_regions

def filter_memory_by_regions(
    memory_layout_data: dict[str, Any], 
    focus_regions: list[tuple[int, int]]
) -> dict[str, Any]:
    """
    根据给定的焦点区域列表，过滤一个扁平化的内存布局。
    返回一个新的、分段式的内存布局数据。

    Args:
        memory_layout_data (dict): 包含 "memory_fragments" 扁平列表的原始内存布局。
        focus_regions (list[tuple[int, int]]): 要关注的内存区域列表。

    Returns:
        dict: 一个新的、被过滤后的内存布局数据字典，其格式为分段式。
    """
    if not focus_regions:
        return memory_layout_data

    # --- 过滤内存碎片并构建分段结构 ---
    full_fragments = memory_layout_data.get("memory_fragments", [])
    if not full_fragments or not isinstance(full_fragments[0], list):
        # 如果数据已经是分段格式或为空，则直接返回
        return memory_layout_data
        
    filtered_segments = []
    
    prev_end = 0
    last_added_frag_end = -1 # 用于检测内存段是否连续

    for frag_end, frag_status in full_fragments:
        frag_start = prev_end
        
        # 检查当前碎片是否与任何一个感兴趣的区域重叠
        is_relevant = False
        for region_start, region_end in focus_regions:
            if max(frag_start, region_start) < min(frag_end, region_end):
                is_relevant = True
                break
        
        if is_relevant:
            # 如果当前碎片与上一个添加的碎片不连续，则创建一个新段
            if not filtered_segments or frag_start != last_added_frag_end:
                filtered_segments.append({
                    "start_addr": frag_start,
                    "fragments": []
                })
            
            # 将当前碎片添加到最后一个（即当前）段中
            filtered_segments[-1]["fragments"].append([frag_end, frag_status])
            last_added_frag_end = frag_end
        
        prev_end = frag_end

    logger.info(f"内存布局从 {len(full_fragments)} 个条目简化为 {len(filtered_segments)} 个独立的内存段。")

    # 构建并返回新的数据结构和合并后的内存区域
    # 摘要信息保持不变，因为它反映的是全局状态
    return {
        "memory_fragments": filtered_segments,
        "summary": memory_layout_data.get("summary", {})
    }