"""
Copyright (c) 2026, Chen Jie, Joungtao, Xuzheng Jiang
All rights reserved.
This source code is licensed under the BSD-2-Clause license found in the
LICENSE file in the root directory of this source tree.
"""

# common_types.py
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, NamedTuple
if TYPE_CHECKING:
    from parser_core import ParserContext

class StackFrame(NamedTuple):
    """表示一个调用栈帧的结构体。"""
    file: str
    func: str
    line: int
    col: int

CallStack = tuple[StackFrame, ...]
"""表示一个完整的调用栈，是 StackFrame 的元组。"""

@dataclass
class Event:
    """
    表示单个内存操作事件的数据结构。
    """
    # --- 核心字段 (解析时直接生成) ---
    time: int # 事件发生的时间戳 (纳秒)
    operation: str # 操作类型, 如 'alloc', 'free', 'brk' 等
    range: str
    """
    内存操作的范围。
    - 对于 brk 管理的内存，格式为 "start_offset-end_offset" (相对brk_base)。
    - 对于其他内存，格式为 "0xstart_addr-0xend_addr" (绝对地址)。
    """

    size: int # 操作涉及的内存大小 (字节)
    callstack_path: list[int] = field(default_factory=list) # 调用栈路径，每个元素代表一个 StackFrame 的唯一ID
    
    # --- 关联信息字段 (可选) ---
    alloc_at: int | None = None
    """对于 free 事件，记录其对应分配事件的时间戳"""
    free_at: int | None = None
    """对于 alloc 事件，记录其对应释放事件的时间戳"""
    
    # --- 分析阶段添加的字段 (可选) ---
    fragmentation_ratio: float | None = None
    """事件发生时，brk 堆的碎片率"""
    free_ratio: float | None = None
    """事件发生时，brk 堆的空闲率"""
    impact_score: float | None = None
    """根据碎片率和空闲率计算的影响分数，计算参见analysis.py"""

    def to_dict(self) -> dict[str, Any]:
        """
        将 Event 对象转换为字典，以便进行序列化 (如写入 JSON)。
        可以选择性地过滤掉值为 None 的字段以优化输出。
        """
        result = {
            "time": self.time,
            "operation": self.operation,
            "range": self.range,
            "size": self.size,
            "callstack_path": self.callstack_path,
        }
        
        # 只添加非None的可选字段
        if self.alloc_at is not None:
            result["alloc_at"] = self.alloc_at
        if self.free_at is not None:
            result["free_at"] = self.free_at
        if self.fragmentation_ratio is not None:
            result["fragmentation_ratio"] = self.fragmentation_ratio
        if self.free_ratio is not None:
            result["free_ratio"] = self.free_ratio
        if self.impact_score is not None:
            result["impact_score"] = self.impact_score
            
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'Event':
        """
        从字典创建 Event 对象，用于反序列化 (如从缓存加载)。
        """
        return cls(
            time=data.get("time", 0),
            operation=data.get("operation", ""),
            range=data.get("range", ""),
            size=data.get("size", 0),
            callstack_path=data.get("callstack_path", []),
            alloc_at=data.get("alloc_at"),
            free_at=data.get("free_at"),
            fragmentation_ratio=data.get("fragmentation_ratio"),
            free_ratio=data.get("free_ratio"),
            impact_score=data.get("impact_score")
        )

@dataclass
class Snapshot:
    """内存分析快照数据结构"""
    timestamp: int | str
    events: list[Event] = field(default_factory=list)
    fragmentation_data: list[dict] = field(default_factory=list)
    brk_events: list[Event] = field(default_factory=list)
    memory_fragments: dict[str, Any] = field(default_factory=dict)
    ctx: 'ParserContext | None' = None  # 使用 TYPE_CHECKING 避免循环导入
    next_idx: int = 0
    
    def to_dict(self) -> dict:
        """将Snapshot对象转换为字典，用于序列化"""
        # 特殊处理 ctx 字段，确保 ParserContext 对象被正确序列化
        if self.ctx is None:
            ctx_dict = {}
        elif hasattr(self.ctx, '__dict__'):
            # 如果 ctx 是 ParserContext 对象，需要特殊处理
            ctx_dict = {}
            for key, value in self.ctx.__dict__.items():
                if key == "reverse_stack_frame_map":
                    # 将 StackFrame 对象转换为字典
                    reverse_map = {}
                    for frame, frame_id in value.items():
                        reverse_map[frame._asdict()] = frame_id
                    ctx_dict[key] = reverse_map
                elif key == "stack_frame_map":
                    # 将 StackFrame 对象转换为字典
                    stack_map = {}
                    for frame_id, frame in value.items():
                        stack_map[frame_id] = frame._asdict()
                    ctx_dict[key] = stack_map
                else:
                    ctx_dict[key] = value
        else:
            # 如果 ctx 已经是字典，直接使用
            ctx_dict = self.ctx
            
        return {
            "timestamp": self.timestamp,
            "events": self.events,
            "fragmentation_data": self.fragmentation_data,
            "brk_events": self.brk_events,
            "memory_fragments": self.memory_fragments,
            "ctx": ctx_dict,
            "next_idx": self.next_idx
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Snapshot':
        """从字典创建Snapshot对象，用于反序列化"""
        # 将字典列表转换为Event对象列表
        events = [Event.from_dict(event) if isinstance(event, dict) else event 
                 for event in data.get("events", [])]
        brk_events = [Event.from_dict(event) if isinstance(event, dict) else event 
                     for event in data.get("brk_events", [])]
        
        return cls(
            timestamp=data.get("timestamp"),
            events=events,
            fragmentation_data=data.get("fragmentation_data", []),
            brk_events=brk_events,
            memory_fragments=data.get("memory_fragments", {}),
            ctx=data.get("ctx") or None,
            next_idx=data.get("next_idx", 0)
        )