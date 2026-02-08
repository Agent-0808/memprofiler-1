# output_handler.py
import os
import shutil
import json
from typing import Any
from common_types import Event

# 全局配置：默认启用美观输出
PRETTY_PRINT = True

def set_pretty_print(enable: bool):
    """设置JSON输出格式
    Args:
        enable: True=美观输出(带缩进), False=紧凑输出(无缩进)
    """
    global PRETTY_PRINT
    PRETTY_PRINT = enable

def _status_code(status: str | int) -> int:
    """辅助函数：将内存状态字符串转换为整数表示。"""
    if status == "free":
        return 0
    if status == "used":
        return 1
    if status == "remove":
        return 2
    # 如果已经是整数或其他值，直接返回
    if isinstance(status, int):
        return status
    return -1

def remove_output_dir(output_dir: str = "output"):
    """
    删除指定的输出文件夹及其所有内容。

    Args:
        output_dir (str): 要删除的文件夹路径，默认为 "output"。
    """
    if os.path.exists(output_dir) and os.path.isdir(output_dir):
        shutil.rmtree(output_dir)
        print(f"已删除文件夹: {output_dir}")
    else:
        print(f"文件夹不存在: {output_dir}")

def write_events(events: list[Event], output_path: str):
    """将事件列表写入JSON文件。"""
    if output_path:
        # 将Event对象转换为字典
        events_dict = [event.to_dict() for event in events]
        with open(output_path, "w") as f:
            indent = 2 if PRETTY_PRINT else None
            json.dump(events_dict, f, indent=indent)

def write_flamegraph(flame_graph, output_path):
    """将火焰图数据写入JSON文件。"""
    if output_path:
        with open(output_path, "w") as f:
            indent = 2 if PRETTY_PRINT else None
            json.dump(flame_graph, f, indent=indent)

def write_fragmentation(fragmentation_data: list[dict[str, Any]], output_path: str):
    """将碎片率数据写入JSON文件，并去重。"""
    if output_path:
        # 使用字典来去重，保留每个时间戳最后一次出现的数据，同时保持顺序
        # (Python 3.7+ 的字典会保持插入顺序)
        unique_data = list({
            entry["timestamp"]: entry for entry in fragmentation_data
        }.values())

        with open(output_path, "w") as f:
            indent = 2 if PRETTY_PRINT else None
            json.dump(unique_data, f, indent=indent)

def write_brk_events(brk_events: list[Event], output_path: str):
    """将 brk 事件列表写入JSON文件。"""
    if output_path:
        # 将Event对象转换为字典
        events_dict = [event.to_dict() for event in brk_events]
        with open(output_path, "w") as f:
            indent = 2 if PRETTY_PRINT else None
            json.dump(events_dict, f, indent=indent)

def write_stack_frame_map(stack_frame_map: dict[int, Any], output_path: str):
    """将栈帧映射表写入JSON文件。"""
    if output_path:
        # 将 StackFrame 对象转换为字典
        stack_frame_dict = {}
        for frame_id, frame in stack_frame_map.items():
            # 检查 frame 是否是 StackFrame 对象
            if hasattr(frame, '_asdict'):
                stack_frame_dict[frame_id] = frame._asdict()
            else:
                # 如果已经是字典，直接使用
                stack_frame_dict[frame_id] = frame
        
        with open(output_path, "w") as f:
            indent = 2 if PRETTY_PRINT else None
            json.dump(stack_frame_dict, f, indent=indent)

def write_memory_fragments(
    snapshot_data: dict[str, Any], 
    output_path: str, 
    timestamp: int | str | None = None, 
    focus_regions: list[tuple[int, int]] | None = None):
    """
    根据输入数据的结构，处理并写入内存布局快照。
    整合了对扁平化和分段式两种格式的处理，以遵循DRY原则。
    """
    if not output_path or not snapshot_data:
        return

    input_data = snapshot_data.get("memory_fragments", [])
    output_segments = []

    if input_data:
        # 通过检查第一个元素的结构来判断格式
        # 分段格式的元素是一个包含 "start_addr" 键的字典
        is_segmented_format = isinstance(input_data[0], dict) and "start_addr" in input_data[0]

        if is_segmented_format:
            # --- 处理分段格式 ---
            for segment in input_data:
                processed_fragments = [
                    [item[0], _status_code(item[1])]
                    for item in segment.get("fragments", [])
                ]
                output_segments.append({
                    "start_addr": segment["start_addr"],
                    "fragments": processed_fragments
                })
        else:
            # --- 处理扁平格式 ---
            simplified_fragments = []
            # 统一处理两种可能的扁平子格式
            if isinstance(input_data[0], dict):
                # 格式: [{"end": ..., "status": ...}, ...]
                simplified_fragments = [
                    [item["end"], _status_code(item["status"])]
                    for item in input_data
                ]
            else:
                # 格式: [[end, status_int_or_str], ...]
                simplified_fragments = [
                    [item[0], _status_code(item[1])]
                    for item in input_data
                ]
            
            # 将扁平列表包装成一个从地址 0 开始的单一内存段
            output_segments.append({
                "start_addr": 0,
                "fragments": simplified_fragments
            })

    # --- 构造通用的输出结构并写入文件 ---
    output_data: dict[str, Any] = {
        "timestamp": timestamp or None,
        "summary": snapshot_data.get("summary", {}),
        "focus_regions": focus_regions or [],
        "memory_segments": output_segments,
    }

    with open(output_path, "w") as f:
        indent = 2 if PRETTY_PRINT else None
        json.dump(output_data, f, indent=indent, separators=(',', ':') if not PRETTY_PRINT else None)