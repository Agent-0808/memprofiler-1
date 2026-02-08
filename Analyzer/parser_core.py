# parser_core.py
import struct
import zstandard as zstd
import bisect
from typing import Any, Callable

from common_types import Event, CallStack, StackFrame

import config
import logging
logger = logging.getLogger(__name__)

# 用于解析内存分析数据的常量
TRACE_HEADER_FORMAT = "<B I Q Q q H"
FRAME_FORMAT = "<I I i i"
OPERATION_TYPE_LIST = [
    ("UNKNOWN", 2, 1),
    ("BRK", 1, 1),
    ("SBRK", 1, 1),
    ("MMAP", 2, 1),
    ("MUNMAP", 2, 1),
    ("CLONE", 1, 1),
    ("CLONE3", 2, 1),
    ("FORK", 0, 1),
    ("VFORK", 0, 1),
    ("EXECVE", 1, 1),
    ("FREE", 1, 0),
    ("MALLOC", 1, 1),
    ("CALLOC", 2, 1),
    ("REALLOC", 2, 1),
    ("VALLOC", 1, 1),
    ("POSIX_MEMALIGN", 2, 1),
    ("ALIGNED_ALLOC", 2, 1),
    ("NEW", 1, 1),
    ("NEW[]", 1, 1),
    ("DELETE_LEGACY", 1, 0),
    ("DELETE", 2, 0),
    ("DELETE[]", 1, 0),
]
ALLOC_TYPES = {"MALLOC", "CALLOC", "VALLOC", "REALLOC", "NEW", "NEW[]"}
FREE_TYPES = {"FREE", "DELETE_LEGACY", "DELETE", "DELETE[]"}
CPP_OP_TYPES = {"NEW", "NEW[]", "DELETE_LEGACY", "DELETE", "DELETE[]"}

def decompress_zst(path):
    """解压一个 zstd 格式的压缩文件。"""
    dctx = zstd.ZstdDecompressor()
    with open(path, "rb") as f:
        reader = dctx.stream_reader(f) # 返回的是一个流式读取器
        return reader.read() # 但这里立刻调用了 .read()，将所有数据一次性读入内存


def get_op_info(code):
    """根据操作码获取操作信息。"""
    if 0 <= code < len(OPERATION_TYPE_LIST):
        name, argc, need_ret = OPERATION_TYPE_LIST[code]
        return name, bool(need_ret)
    return "UNKNOWN", False

def create_event(
    event_type: str, ts: int, addr: int, size: int,
    callstack_path: list[int] | None,
    brk_base: int | None = None,
    alloc_at: int | None = None,
    free_at: int | None = None
    ) -> Event:
    """创建一个Event对象，使用相对地址。"""
    range_str = f"{hex(addr)}-{hex(addr + size)}" # 默认使用绝对地址
    # 如果 brk_base 已设定且地址在 brk 管理范围内，则使用相对偏移
    if brk_base is not None and addr >= brk_base:
        start_offset = addr - brk_base
        end_offset = start_offset + size
        range_str = f"{start_offset}-{end_offset}"

    return Event(
        time=ts,
        operation=event_type,
        range=range_str,
        size=size,
        callstack_path=callstack_path if callstack_path is not None else [],
        alloc_at=alloc_at,
        free_at=free_at
    )


class MemoryFragmentManager:
    """管理内存碎片的状态，包括更新和分析。"""

    def __init__(self):
        """初始化内存碎片管理器。"""
        # self.fragments 始终保持按起始地址排序
        # 每个元素是 (start_addr, end_addr, status)
        self.fragments = []
        self.total_used = 0
        self.total_free = 0
        self.largest_free = 0
        self.free_blocks_count = 0
        self.used_blocks_count = 0

    def to_dict(self) -> dict[str, Any]:
        """将管理器状态序列化为字典。"""
        return {
            "fragments": self.fragments,
            "total_used": self.total_used,
            "total_free": self.total_free,
            "largest_free": self.largest_free,
            "free_blocks_count": self.free_blocks_count,
            "used_blocks_count": self.used_blocks_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'MemoryFragmentManager':
        """从字典反序列化，创建管理器实例。"""
        manager = cls()
        manager.fragments = data.get("fragments", [])
        manager.total_used = data.get("total_used", 0)
        manager.total_free = data.get("total_free", 0)
        manager.largest_free = data.get("largest_free", 0)
        manager.free_blocks_count = data.get("free_blocks_count", 0)
        manager.used_blocks_count = data.get("used_blocks_count", 0)
        return manager

    def _update_stats(self, size: int, status: str, add: bool):
        """辅助函数，用于增量更新统计数据。"""
        delta = size if add else -size
        if status == "free":
            self.total_free += delta
            self.free_blocks_count += 1 if add else -1
        elif status == "alloc":
            self.total_used += delta
            self.used_blocks_count += 1 if add else -1

    def _recalculate_largest_free(self):
        """
        重新计算并更新最大的空闲内存片段大小
        
        该函数遍历所有内存片段，找出状态为"free"的片段中大小最大的一个，
        并将结果保存到实例变量largest_free中
        """
        # 使用生成器表达式和 max() 函数，更简洁高效
        # default=0 可以在没有 free 块时避免 ValueError
        self.largest_free = max(
            (end - start for start, end, status in self.fragments if status == "free"),
            default=0
        )

    def update(self, addr: int, size: int, status: str):
        """更新内存映射表，处理内存碎片合并并维护实时统计信息。

        参数:
            addr (int): 要更新的内存区域起始地址。
            size (int): 要更新的内存区域大小。
            status (str): 内存区域的状态，例如 "alloc" 或 "free"。

        返回值:
            无返回值。
        """
        if size <= 0:
            return
        
        # 每次调用 update 时，我们都乐观地假设不需要重新计算
        needs_recalc_largest_free = False
        addr_start = addr
        addr_end = addr + size

        # 1. 使用二分查找快速定位与当前更新区域相关的碎片范围
        # bisect_left 找到第一个 end > addr_start 的位置
        # 我们需要检查前一个，因为它可能与 addr_start 重叠
        start_idx = bisect.bisect_left(self.fragments, (addr_start, 0, ''))
        if start_idx > 0:
            # 检查前一个碎片是否与我们的区域重叠
            prev_end = self.fragments[start_idx - 1][1]
            if prev_end > addr_start:
                start_idx -= 1
        
        # bisect_right 找到第一个 start >= addr_end 的位置
        end_idx = bisect.bisect_right(self.fragments, (addr_end, 0, ''))

        # 2. 准备要插入的新碎片列表
        new_frags = []
        
        # 从受影响的旧碎片中减去统计数据
        # 在移除旧碎片统计时，检查是否移除了最大的空闲块
        for i in range(start_idx, end_idx):
            frag_start, frag_end, frag_status = self.fragments[i]
            frag_size = frag_end - frag_start
            self._update_stats(frag_size, frag_status, add=False)
            # 如果被覆盖的碎片是空闲的，并且它的大小等于当前记录的最大值
            if frag_status == "free" and frag_size == self.largest_free:
                needs_recalc_largest_free = True

        # 3. 处理与更新区域重叠的碎片
        
        # 处理左边界：可能需要保留被切断的左侧部分
        if start_idx < len(self.fragments):
            frag_start, frag_end, frag_status = self.fragments[start_idx]
            if frag_start < addr_start:
                new_frags.append((frag_start, addr_start, frag_status))

        # 添加代表当前操作的新碎片
        if status in ("alloc", "free"):
            new_frags.append((addr_start, addr_end, status))
        
        # 处理右边界：可能需要保留被切断的右侧部分
        if end_idx > 0:
            frag_start, frag_end, frag_status = self.fragments[end_idx - 1]
            if frag_end > addr_end:
                new_frags.append((addr_end, frag_end, frag_status))

        # 4. 合并相邻的同类（仅free）碎片
        merged_frags = []
        if new_frags:
            # 与左侧外部邻居合并
            if start_idx > 0:
                left_neighbor = self.fragments[start_idx - 1]
                # 如果新区域的第一个碎片可以和左邻居合并
                if left_neighbor[1] == new_frags[0][0] and left_neighbor[2] == new_frags[0][2] and new_frags[0][2] == "free":
                    # 从统计中移除左邻居，因为它将被合并
                    self._update_stats(left_neighbor[1] - left_neighbor[0], left_neighbor[2], add=False)
                    # 合并
                    new_frags[0] = (left_neighbor[0], new_frags[0][1], new_frags[0][2])
                    start_idx -= 1 # 替换范围向左扩展

            # 内部合并
            current_start, current_end, current_status = new_frags[0]
            for next_start, next_end, next_status in new_frags[1:]:
                if next_start == current_end and next_status == current_status and current_status == "free":
                    current_end = next_end # 合并
                else:
                    merged_frags.append((current_start, current_end, current_status))
                    current_start, current_end, current_status = next_start, next_end, next_status
            merged_frags.append((current_start, current_end, current_status))

            # 与右侧外部邻居合并
            if end_idx < len(self.fragments):
                right_neighbor = self.fragments[end_idx]
                if merged_frags[-1][1] == right_neighbor[0] and merged_frags[-1][2] == right_neighbor[2] and right_neighbor[2] == "free":
                    # 从统计中移除右邻居
                    self._update_stats(right_neighbor[1] - right_neighbor[0], right_neighbor[2], add=False)
                    # 合并
                    merged_frags[-1] = (merged_frags[-1][0], right_neighbor[1], right_neighbor[2])
                    end_idx += 1 # 替换范围向右扩展
        
        # 5. 将新的碎片列表替换回主列表
        self.fragments[start_idx:end_idx] = merged_frags

        # 为新生成的碎片添加统计数据
        # 在添加新碎片统计时，增量更新 largest_free
        for frag_start, frag_end, frag_status in merged_frags:
            frag_size = frag_end - frag_start
            self._update_stats(frag_size, frag_status, add=True)
            # 如果新生成的碎片是空闲的，尝试更新最大值
            if frag_status == "free":
                if frag_size > self.largest_free:
                    self.largest_free = frag_size
                    # 如果我们通过这个新块找到了一个更大的值，就不需要重新扫描了
                    needs_recalc_largest_free = False

        # 仅在必要时重新计算最大空闲块
        if needs_recalc_largest_free:
            self._recalculate_largest_free()
    def get_fragmentation_ratios(self, timestamp: int, brk_base: int | None = None):
        """
        计算当前内存状态的碎片率和空闲率，仅针对 brk 管理范围内的内存。
        """
        if brk_base is None or (self.total_used + self.total_free == 0):
            return {
                "timestamp": timestamp,
                "fragmentation_ratio": 0.0,
                "free_ratio": 0.0,
            }

        brk_total_memory = self.total_used + self.total_free
        brk_free_memory = self.total_free
        brk_largest_free = self.largest_free

        free_ratio = round(brk_free_memory / brk_total_memory, 4) if brk_total_memory > 0 else 0.0
        frag_ratio = round(1.0 - (brk_largest_free / brk_free_memory), 4) if brk_free_memory > 0 else 0.0

        return {
            "timestamp": timestamp,
            "fragmentation_ratio": frag_ratio,
            "free_ratio": free_ratio,
        }

    def generate_fragment_data(self, brk_base: int | None = None, current_brk: int | None = None):
        """
        生成紧凑格式的内存布局（用于可视化）及统计摘要。
        仅针对 brk 管理范围内的内存进行报告。
        """
        # 如果brk范围未定义，则返回空
        if brk_base is None or current_brk is None:
            return {"memory_fragments": [], "summary": {}}

        compact_layout = []
        
        # 过滤只计算brk范围内的块
        brk_used_count = 0
        brk_free_count = 0
        for start, end, status in self.fragments:
            # 确保只处理在brk范围内的碎片
            if start < brk_base or start >= current_brk:
                continue
            if status == "alloc":
                brk_used_count += 1
            elif status == "free":
                brk_free_count += 1

        for start, end, status in self.fragments:
            # 确保只处理在brk范围内的碎片
            if start < brk_base or start >= current_brk:
                continue
            
            relative_end = end - brk_base
            status_code = 1 if status == "alloc" else 0
            compact_layout.append([relative_end, status_code])

        summary = {
            "total_memory": self.total_used + self.total_free,
            "free_memory": self.total_free,
            "used_memory": self.total_used,
            "largest_free_fragment_size": self.largest_free,
            "free_fragments_count": brk_free_count,
            "used_fragments_count": brk_used_count,
        }
        
        return {"memory_fragments": compact_layout, "summary": summary}


class ParserContext:
    """保存内存分析过程中的解析状态。"""

    def __init__(self):
        """初始化解析器上下文。"""
        # 全局栈帧映射表和反向查找表
        self.stack_frame_map: dict[int, StackFrame] = {}
        self.reverse_stack_frame_map: dict[StackFrame, int] = {}
        self.next_stack_frame_id: int = 0
        
        # 临时存储文件名和函数名的映射，用于构建 StackFrame
        self._temp_filename_map: dict[int, str] = {}
        self._temp_function_map: dict[int, str] = {}
        
        # 其他状态
        self.tid_map: dict[tuple[int, int], tuple[Any, ...]] = {}
        self.alloc_map: dict[int, int] = {} # 已分配的地址 -> 大小
        # 存储分配信息（时间戳和事件索引）
        self.alloc_info_map: dict[int, dict[str, int]] = {} # addr -> {"ts": int, "event_idx": int}
        self.brk_base: int | None = None # BRK区域的基地址
        self.current_brk: int | None = None # 当前BRK指针位置
        self.brk_no: int = 0 # BRK事件序号
        self.trace_idx: int = 0 # 已处理的事件总数
        self.memory_manager: MemoryFragmentManager = MemoryFragmentManager() # 内存碎片管理器实例

def _handle_alloc_event(
    ctx: 'ParserContext',
    output: dict[str, list],
    ts: int,
    addr: int,
    size: int,
    callstack_path: list[int] | None,
    is_in_brk_heap: Callable[[int], bool]
):
    """处理一个内存分配事件。"""
    if size <= 0:
        return

    alloc_event = create_event("alloc", ts, addr, size, callstack_path, ctx.brk_base)
    output["events"].append(alloc_event)
    ctx.alloc_info_map[addr] = {"ts": ts, "event_idx": len(output["events"]) - 1}
    ctx.alloc_map[addr] = size
    
    # 只在地址位于brk堆区时更新
    if is_in_brk_heap(addr):
        ctx.memory_manager.update(addr, size, "alloc")
        output["fragmentation_data"].append(ctx.memory_manager.get_fragmentation_ratios(ts, ctx.brk_base))

def _handle_free_event(
    ctx: 'ParserContext',
    output: dict[str, list],
    ts: int,
    addr: int,
    callstack_path: list[int] | None,
    is_in_brk_heap: Callable[[int], bool]
):
    """处理一个内存释放事件。"""
    size = ctx.alloc_map.get(addr, 0)
    if size <= 0:
        return

    alloc_info = ctx.alloc_info_map.pop(addr, None)
    alloc_ts = alloc_info["ts"] if alloc_info else None

    free_event = create_event("free", ts, addr, size, callstack_path, ctx.brk_base, alloc_at=alloc_ts)
    output["events"].append(free_event)

    if alloc_info:
        alloc_event_idx = alloc_info["event_idx"]
        if alloc_event_idx < len(output["events"]):
            output["events"][alloc_event_idx].free_at = ts

    # 只在地址位于brk堆区时更新
    if is_in_brk_heap(addr):
        ctx.memory_manager.update(addr, size, "free")
        output["fragmentation_data"].append(ctx.memory_manager.get_fragmentation_ratios(ts, ctx.brk_base))
    
    ctx.alloc_map.pop(addr, None)

def _handle_brk_event(
    ctx: 'ParserContext',
    output: dict[str, list],
    ts: int,
    new_brk: int,
    callstack_path: list[int] | None
):
    """处理一个 brk/sbrk 事件。"""
    if ctx.brk_base is None:
        ctx.brk_base = new_brk

    previous_brk = ctx.current_brk or new_brk
    ctx.current_brk = new_brk

    if new_brk > previous_brk:
        new_size = new_brk - previous_brk
        # BRK事件直接更新管理器，因为它定义了堆的边界
        ctx.memory_manager.update(previous_brk, new_size, "free")
    elif new_brk < previous_brk:
        shrunk_size = previous_brk - new_brk
        ctx.memory_manager.update(new_brk, shrunk_size, "remove")

    brk_change_size = new_brk - previous_brk
    prev_offset = previous_brk - ctx.brk_base
    new_offset = new_brk - ctx.brk_base
    range_str = f"{prev_offset}-{new_offset}"

    brk_event = Event(
        time=ts,
        operation="brk",
        range=range_str,
        callstack_path=callstack_path if callstack_path is not None else [],
        size=brk_change_size
    )
    
    output["events"].append(brk_event)
    output["brk_events"].append(brk_event)
    ctx.brk_no += 1
    output["fragmentation_data"].append(ctx.memory_manager.get_fragmentation_ratios(ts, ctx.brk_base))

def extract_events(
    binary: bytes,
    snapshots: list | None = None,
    ctx: ParserContext | None = None,
    start_idx: int = 0,
    output: dict | None = None,
    total_events: int = 0,
    total_duration: int = 0,
):
    """
    解析二进制数据以提取内存事件，支持增量解析和在指定时间戳生成快照。
    """
    if ctx is None:
        ctx = ParserContext()
    if output is None:
        # output 用于在增量解析中累积数据，在生成快照时复制并返回
        output = {"events": [], "fragmentation_data": [], "brk_events": []}

    # 确保 snapshots 列表已排序并处理下一个目标快照
    snapshots_copy = sorted(snapshots) if snapshots else []  # 对传入的snapshots做一份拷贝，避免修改原始列表
    next_snapshot_target = snapshots_copy.pop(0) if snapshots_copy else None

    HEADER_SIZE = struct.calcsize(TRACE_HEADER_FORMAT)
    FRAME_SIZE = struct.calcsize(FRAME_FORMAT)
    bin_idx = start_idx

    while bin_idx < len(binary):
        event_start_idx = bin_idx  # 记录当前事件的起始位置，以便回溯

        entry_type = binary[bin_idx]

        if entry_type in (0x00, 0x01):  # 处理文件名或函数名映射
            if bin_idx + 3 > len(binary):
                logger.warning(f"数据末尾不足以解析文件名/函数名长度字段，在索引 {bin_idx} 处停止。")
                break
            name_len = struct.unpack("<H", binary[bin_idx + 1: bin_idx + 3])[0]
            if bin_idx + 3 + name_len > len(binary):
                logger.warning(f"数据末尾不足以解析完整的名称字符串，在索引 {bin_idx} 处停止。")
                break
            name = binary[bin_idx + 3: bin_idx + 3 + name_len].decode(
                "utf-8", errors="replace"
            )
            if entry_type == 0x00:
                ctx._temp_filename_map[len(ctx._temp_filename_map)] = name
            else:
                ctx._temp_function_map[len(ctx._temp_function_map)] = name
            bin_idx += 3 + name_len
            continue

        if bin_idx + HEADER_SIZE > len(binary):
            # 数据不足以解析完整头部，结束解析
            logger.warning(f"数据末尾不足以解析完整的事件头部，在索引 {bin_idx} 处停止。")
            break

        tag, tid, arg1, arg2, ts, depth = struct.unpack(
            TRACE_HEADER_FORMAT, binary[bin_idx: bin_idx + HEADER_SIZE]
        )
        ctx.trace_idx += 1

        # 日志输出
        if ctx.trace_idx % config.settings.log_interval == 0:
            log_parts = []
            # 事件进度
            if total_events > 0:
                trace_percent = (ctx.trace_idx / total_events) * 100
                log_parts.append(f"trace: {ctx.trace_idx}/{total_events} ({trace_percent:.1f}%)")
            else:
                log_parts.append(f"trace: {ctx.trace_idx}")

            # 时间进度
            if total_duration > 0:
                # 时间戳除以1,000,000以缩短显示
                current_ts_short = ts // 1_000_000
                total_duration_short = total_duration // 1_000_000
                time_percent = (ts / total_duration) * 100
                log_parts.append(f"time: {current_ts_short}/{total_duration_short} ({time_percent:.1f}%)")
            else:
                log_parts.append(f"time: {ts}")

            logger.info(" | ".join(log_parts))

        # 检查是否需要在此时间戳暂停并生成快照
        if next_snapshot_target is not None and ts > next_snapshot_target:
            # 回溯到当前事件的开始处，以便下次从这里继续
            bin_idx = event_start_idx
            # 传递 current_brk 以便正确过滤输出
            mem_fragments_data = ctx.memory_manager.generate_fragment_data(ctx.brk_base, ctx.current_brk)
            # 准备返回的快照数据 (注意：events, fragmentation_data, brk_events 是当前累积的副本)
            snapshot_data = {
                "timestamp": next_snapshot_target,
                "events": output["events"].copy(),
                "fragmentation_data": output["fragmentation_data"].copy(),
                "brk_events": output["brk_events"].copy(),
                "memory_fragments": mem_fragments_data,
                "ctx": ctx,  # 传递当前上下文，用于增量解析
                "next_idx": bin_idx,  # 记录下一次开始解析的索引
            }
            # 获取下一个快照时间戳
            next_snapshot_target = snapshots_copy.pop(0) if snapshots_copy else None
            # 返回快照数据
            yield snapshot_data
            continue  # 继续循环，从 bin_idx 处重新处理当前事件

        bin_idx += HEADER_SIZE

        # 解析调用栈信息，使用 StackFrame 对象
        callstack_path = []
        for _ in range(depth):
            if bin_idx + FRAME_SIZE > len(binary):
                logger.warning(f"数据末尾不足以解析完整的栈帧，在索引 {bin_idx} 处停止。事件 {ctx.trace_idx} 的栈不完整。")
                callstack_path = []  # 清空不完整的栈
                break  # 退出栈帧解析循环
            file_idx, func_idx, line, col = struct.unpack(
                FRAME_FORMAT, binary[bin_idx: bin_idx + FRAME_SIZE]
            )
            
            # 从临时映射中获取文件名和函数名
            filename = ctx._temp_filename_map.get(file_idx, f"<unknown_file_{file_idx}>")
            funcname = ctx._temp_function_map.get(func_idx, f"<unknown_func_{func_idx}>")
            
            # 创建 StackFrame 对象
            frame = StackFrame(file=filename, func=funcname, line=line, col=col)
            
            # 检查 frame 是否已存在于反向映射中
            if frame in ctx.reverse_stack_frame_map:
                frame_id = ctx.reverse_stack_frame_map[frame]
            else:
                # 分配新的 ID 并添加到映射表
                frame_id = ctx.next_stack_frame_id
                ctx.stack_frame_map[frame_id] = frame
                ctx.reverse_stack_frame_map[frame] = frame_id
                ctx.next_stack_frame_id += 1
            
            # 将单个 frame_id 添加到 callstack_path
            callstack_path.append(frame_id)
            bin_idx += FRAME_SIZE

        # 根据配置参数截断调用栈
        if config.settings.callstack_depth >= 0 and len(callstack_path) > config.settings.callstack_depth:
            callstack_path = callstack_path[:config.settings.callstack_depth]

        # 处理操作码逻辑
        op_code = tag >> 1
        is_ret = bool(tag & 1)  # 判断是调用还是返回
        name, need_ret = get_op_info(op_code)
        key = (tid, op_code)  # 用于匹配调用和返回的键

        # 跳过new/delete操作的逻辑
        if config.settings.skip_cpp and name in CPP_OP_TYPES:
            # 跳过new/delete操作，直接继续下一个事件
            continue

        # 辅助函数，判断地址是否在brk堆区
        def is_in_brk_heap(addr: int) -> bool:
            return (ctx.brk_base is not None and
                    ctx.current_brk is not None and
                    addr >= ctx.brk_base and
                    addr < ctx.current_brk)

        # 处理不需要返回（即单条日志记录完成）的事件
        if not is_ret and not need_ret:
            if name in ALLOC_TYPES:
                addr, size = arg2, arg1
                _handle_alloc_event(ctx, output, ts, addr, size, callstack_path, is_in_brk_heap)
            elif name in FREE_TYPES:
                addr = arg1
                _handle_free_event(ctx, output, ts, addr, callstack_path, is_in_brk_heap)
            continue

        # 处理需要配对的操作（调用/返回匹配）
        if not is_ret:  # 调用请求
            ctx.tid_map[key] = (arg1, arg2, ts, callstack_path)  # 存储调用时的参数、时间戳和callstack_path
        else:  # 返回响应
            if key not in ctx.tid_map:
                logger.warning(f"发现未匹配的返回事件 (Tag: {tag}, TID: {tid}, OpCode: {op_code})，可能日志不完整或已跳过部分。")
                continue  # 未找到对应的调用请求，跳过此返回事件
            prev_a1, prev_a2, t_invoke, callstack_path = ctx.tid_map.pop(key)  # 获取调用时的信息和callstack_path
            addr, size = 0, 0

            if name in ALLOC_TYPES:
                if name == "REALLOC":
                    old_addr = prev_a1
                    # realloc 的 free 部分
                    _handle_free_event(ctx, output, ts, old_addr, callstack_path, is_in_brk_heap)
                    # realloc 的 alloc 部分
                    addr, size = arg1, prev_a2
                elif name in {"MALLOC", "VALLOC", "NEW", "NEW[]"}:
                    addr, size = arg1, prev_a1
                elif name == "CALLOC":
                    addr, size = arg1, prev_a1 * prev_a2
                
                _handle_alloc_event(ctx, output, ts, addr, size, callstack_path, is_in_brk_heap)

            elif name in FREE_TYPES:
                addr = prev_a1
                _handle_free_event(ctx, output, ts, addr, callstack_path, is_in_brk_heap)

            elif name == "BRK":
                new_brk = arg1
                _handle_brk_event(ctx, output, ts, new_brk, callstack_path)

    # 循环结束后，生成最终快照
    # 传递 current_brk 以便正确过滤输出
    mem_fragments_data = ctx.memory_manager.generate_fragment_data(ctx.brk_base, ctx.current_brk)
    yield {
        "timestamp": "final",  # 标记为最终快照
        "events": output["events"],
        "fragmentation_data": output["fragmentation_data"],
        "brk_events": output["brk_events"],
        "memory_fragments": mem_fragments_data,
        "ctx": ctx,  # 传递最终上下文
        "next_idx": bin_idx,  # 传递最终读取位置
    }