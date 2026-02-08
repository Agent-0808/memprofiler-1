"""
Copyright (c) 2026, Chen Jie, Joungtao, Xuzheng Jiang
All rights reserved.
This source code is licensed under the BSD-2-Clause license found in the
LICENSE file in the root directory of this source tree.
"""

# main.py
import os
import pickle # 用于加载缓存
import logging # 导入 logging

import parser_core as Parser
import snapshot_manager as SnapshotMngr
from common_types import Snapshot
import output_handler as Output
import analysis 
import utils

# 导入配置并设置日志
import config
config.initialize_config()
utils.setup_logging()
logger = logging.getLogger(__name__)

def parse_statinfo(file_path: str) -> dict[str, str]:
    """
    解析 statinfo.txt 文件，返回一个包含键值对的字典。
    Args:
        file_path (str): statinfo.txt 文件的路径。
    Returns:
        dict[str, str]: 解析后的键值对字典。
    """
    stats = {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if ':' in line:
                    key, value = line.split(':', 1)
                    stats[key.strip()] = value.strip()
    except FileNotFoundError:
        logger.warning(f"元数据文件 'statinfo.txt' 未在路径 {os.path.dirname(file_path)} 中找到。")
    except Exception as e:
        logger.error(f"读取 statinfo.txt 文件时出错: {e}")
    return stats

def handle_snapshot(snapshot, ts: int | str, output_dir: str):
    """
    处理每个生成的快照。
    - 对于 "final" 快照: 写入所有相关的JSON文件并保存缓存。
    - 对于 --timestamps 指定的中间快照: 根据 config.settings.report_for_snapshots 参数决定是否生成报告文件
    Args:
        snapshot (Snapshot/dict): 当前生成的快照数据。
        ts (int/str): 快照的时间戳，或"final"。
        output_dir (str): 输出目录。
    """
    # 如果传入的是字典，转换为Snapshot对象
    if isinstance(snapshot, dict):
        snapshot = Snapshot.from_dict(snapshot)
    
    ts_str = str(ts) if ts != "final" else "final"

    # 始终保存快照上下文以供增量解析使用（除非禁用缓存）
    if not config.settings.no_cache:
        SnapshotMngr.save_snapshot_cache(snapshot, ts, output_dir)

    # 对于中间时间戳快照，根据 report_for_snapshots 参数决定是否生成报告
    if ts != "final":
        # 对于中间时间戳快照，只记录日志
        logger.info(f"已为中间时间戳快照 {ts_str} 保存缓存。")
        
        # 如果没有设置 report_for_snapshots 参数，则提前返回
        if not config.settings.report_for_snapshots:
            return
    
    logger.info(f"为{'最终' if ts == 'final' else ''}快照 '{ts_str}' 生成详细JSON文件...")
    events = snapshot.events
    frag_data = snapshot.fragmentation_data
    mem_frags_data = snapshot.memory_fragments # 内存布局数据
    
    # 只为非final快照生成events和events_with_frag文件
    if ts != "final":
        # 写入 events JSON (原始事件列表)
        events_file = os.path.join(output_dir, f"{ts_str}_events.json")
        Output.write_events(events, events_file)
        logger.info(f"快照 {ts_str}: 原始事件 -> {events_file}")

        # 合并碎片信息到 events 并写入
        merged_events = analysis.merge_fragmentation_into_events(events, frag_data)
        merged_file = os.path.join(output_dir, f"{ts_str}_events_with_frag.json")
        Output.write_events(merged_events, merged_file)
        logger.info(f"快照 {ts_str}: 带有碎片信息的事件 -> {merged_file}")
    else:
        # 对于final快照，根据final_events参数决定是否生成带碎片信息的事件文件
        if config.settings.final_events:
            # 合并碎片信息到 events 并写入
            merged_events = analysis.merge_fragmentation_into_events(events, frag_data)
            merged_file = os.path.join(output_dir, f"{ts_str}_events_with_frag.json")
            Output.write_events(merged_events, merged_file)
            logger.info(f"最终快照: 带有碎片信息的事件 -> {merged_file}")

    # 如果有 --memory 参数，写入内存碎片快照
    if config.settings.memory_layout and mem_frags_data:
        mem_file = os.path.join(output_dir, f"{ts_str}_memory_fragments.json")
        # 传递时间戳信息，对于final快照，使用"final"作为时间戳
        timestamp = ts if ts != "final" else "final"
        Output.write_memory_fragments(mem_frags_data, mem_file, timestamp)
        logger.info(f"快照 {ts_str}: 内存碎片布局 -> {mem_file}")

class MainProcessor:
    def __init__(self, input_dir, output_dir):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.settings = config.settings # 直接引用全局配置
        
        # 内部状态
        self.stat_info = {}
        self.binary_data = None
        self.final_snapshot = None
        self.peaks = []
        
    def run(self):
        """执行完整的分析流程"""
        self._prepare()
        
        # 解析内存数据
        self._parse_memory_data()
            
        # 检测内存碎片峰值
        self._find_peaks()
        
        # 为每个峰值生成详细报告
        self._process_peak_details()

        # 生成最终报告
        self._generate_final_reports()

        # 清理临时数据
        self._cleanup()
        logger.info("所有处理完成。")
        
    def _prepare(self):
        """准备阶段：清空目录、加载元数据等"""
        if self.settings.clear_output_dir:
            Output.remove_output_dir(self.output_dir)
        os.makedirs(self.output_dir, exist_ok=True)
        
        statinfo_path = os.path.join(self.input_dir, "statinfo.txt")
        self.stat_info = parse_statinfo(statinfo_path)
        
        # 检查 memory.profile 文件是否存在
        input_profile_path = os.path.join(self.input_dir, "memory.profile")
        if not os.path.exists(input_profile_path):
            logger.error(f"错误: 在目录 '{self.input_dir}' 中未找到 'memory.profile' 文件。")
            return
            
        # 解析并打印 statinfo.txt
        if self.stat_info:
            logger.info("--- 从 statinfo.txt 加载的元数据 ---")
            for key, value in self.stat_info.items():
                if key in ["bench", "total_traceinfo_count", "time_end"]:
                    logger.info(f"  {key}: {value}")
            logger.info("------------------------------------")
        
        # 设置输出格式
        if self.settings.compact_json:
            Output.set_pretty_print(False)  # 禁用美观输出
            
    def _load_binary_data(self):
        """按需加载和解压二进制文件，确保只执行一次"""
        if self.binary_data is None:
            logger.info("解压输入文件...")
            profile_path = os.path.join(self.input_dir, "memory.profile")
            self.binary_data = Parser.decompress_zst(profile_path)
            logger.info("文件解压完成。")
            
    def _parse_memory_data(self) -> bool:
        """解析内存数据，获取最终快照"""
        logger.info("--- 阶段 1a: 解析内存数据 ---")
        
        # 尝试从缓存加载最终快照
        if not self.settings.no_cache:
            snapshot, ts = SnapshotMngr.load_latest_cache(self.output_dir)
            if snapshot and ts == "final":
                self.final_snapshot = snapshot
                logger.info("成功从缓存加载最终快照，跳过初始解析。")
                
        # 如果没有缓存，则执行完整解析
        if self.final_snapshot is None:
            self._load_binary_data()
            
            # 初始化解析器状态
            final_snapshot: Snapshot | None = None
            loaded_snapshot: Snapshot | None = None
            loaded_timestamp: str | None = None
            parser_context = Parser.ParserContext()
            parser_start_idx = 0
            parser_output: dict[str, list] = {"events": [], "fragmentation_data": [], "brk_events": []}
            
            # 尝试从缓存恢复
            if not self.settings.no_cache:
                loaded_snapshot, loaded_timestamp = SnapshotMngr.load_latest_cache(self.output_dir)
                
            if loaded_snapshot and loaded_timestamp == "final":
                final_snapshot = loaded_snapshot
                logger.info(f"成功从缓存加载最终快照，跳过初始解析阶段。")
            elif loaded_snapshot:
                logger.info(f"成功从缓存加载时间戳 '{loaded_timestamp}' 的快照，开始增量解析。")
                # 如果 ctx 是字典类型，需要转换为 ParserContext
                if isinstance(loaded_snapshot.ctx, dict):
                    parser_context = Parser.ParserContext()
                    # 从字典恢复 ParserContext 的状态
                    for key, value in loaded_snapshot.ctx.items():
                        if not hasattr(parser_context, key):
                            continue
                        # 特殊处理 memory_manager 的恢复
                        if key == "memory_manager" and isinstance(value, dict):
                            parser_context.memory_manager = Parser.MemoryFragmentManager.from_dict(value)
                        # 特殊处理 stack_frame_map 和 reverse_stack_frame_map 的恢复
                        elif key == "stack_frame_map" and isinstance(value, dict):
                            # 恢复 stack_frame_map: dict[int, StackFrame]
                            for frame_id, frame_data in value.items():
                                if isinstance(frame_data, dict):
                                    # 从字典恢复 StackFrame 对象
                                    frame = Parser.StackFrame(
                                        file=frame_data.get("file", ""),
                                        func=frame_data.get("func", ""),
                                        line=frame_data.get("line", 0),
                                        col=frame_data.get("col", 0)
                                    )
                                    parser_context.stack_frame_map[int(frame_id)] = frame
                        elif key == "reverse_stack_frame_map" and isinstance(value, dict):
                            # 恢复 reverse_stack_frame_map: dict[StackFrame, int]
                            for frame_data, frame_id in value.items():
                                if isinstance(frame_data, dict):
                                    # 从字典恢复 StackFrame 对象
                                    frame = Parser.StackFrame(
                                        file=frame_data.get("file", ""),
                                        func=frame_data.get("func", ""),
                                        line=frame_data.get("line", 0),
                                        col=frame_data.get("col", 0)
                                    )
                                    parser_context.reverse_stack_frame_map[frame] = int(frame_id)
                        else:
                            setattr(parser_context, key, value)
                else:
                    parser_context = loaded_snapshot.ctx
                parser_start_idx = loaded_snapshot.next_idx
                parser_output = {"events": loaded_snapshot.events, "fragmentation_data": loaded_snapshot.fragmentation_data, "brk_events": loaded_snapshot.brk_events}
            else:
                logger.info("未找到有效缓存或已禁用缓存，将从头开始完整解析。")
                
            # 如果没有加载到最终快照，则继续解析
            if final_snapshot is None:
                # 准备所有需要生成快照的时间戳
                user_timestamps = set(int(ts) for ts in self.settings.timestamps.split(",") if ts) if self.settings.timestamps else set()
                
                # 如果提供了 --snapshot-gap，则根据时间间隔生成
                gap_timestamps = set()
                if self.settings.snapshot_interval and self.settings.snapshot_interval > 0:
                    try:
                        # 从 stat_info 获取总时长
                        total_duration = int(self.stat_info.get('time_end', '0'))
                        if total_duration > 0:
                            logger.info(f"根据 --snapshot-interval={self.settings.snapshot_interval} 和总时长 {total_duration} 生成时间戳...")
                            for ts in range(self.settings.snapshot_interval, total_duration, self.settings.snapshot_interval):
                                gap_timestamps.add(ts)
                            logger.info(f"已生成 {len(gap_timestamps)} 个基于间隔的时间戳。")
                        else:
                            logger.warning("无法从 statinfo.txt 获取有效的 'time_end'，无法使用 --snapshot-interval 功能。")
                    except (ValueError, TypeError):
                        logger.warning("statinfo.txt 中的 'time_end' 格式无效，无法使用 --snapshot-interval 功能。")
                        
                # 合并所有时间戳并排序
                all_target_timestamps = sorted(list(user_timestamps.union(gap_timestamps)))
                
                if all_target_timestamps:
                    logger.info(f"将为 {len(all_target_timestamps)} 个目标时间戳生成快照。")
                    
                # 过滤掉已经处理过的时间戳（如果从缓存恢复）
                if loaded_snapshot and loaded_timestamp != "final":
                    assert loaded_timestamp is not None
                    loaded_ts_int = int(loaded_timestamp)
                    all_target_timestamps = [ts for ts in all_target_timestamps if ts > loaded_ts_int]
                    
                # 从 stat_info 获取总量数据
                total_events_count = 0
                total_duration_ns = 0
                try:
                    total_events_count = int(self.stat_info.get('total_traceinfo_count', '0'))
                    total_duration_ns = int(self.stat_info.get('time_end', '0'))
                except (ValueError, TypeError):
                    logger.warning("无法从 statinfo.txt 解析有效的总量数据 (total_traceinfo_count/time_end)。进度条可能不完整。")
                    
                # 启动解析器生成器
                parser_gen = Parser.extract_events(self.binary_data, snapshots=all_target_timestamps,
                                            ctx=parser_context, start_idx=parser_start_idx, output=parser_output,
                                            total_events=total_events_count, total_duration=total_duration_ns,
                                            )
                                            
                # 循环处理生成器产出的所有快照
                for snapshot in parser_gen:
                    ts = snapshot.get("timestamp")
                    logger.info(f"--- 捕获快照: {ts} ---")
                    assert isinstance(ts, (int, str))
                    handle_snapshot(snapshot, ts, self.output_dir)
                    if ts == "final":
                        self.final_snapshot = Snapshot.from_dict(snapshot)
                        break # 最终快照已经生成，退出循环
                        
        # 确保最终快照存在
        if self.final_snapshot is None:
            logger.error("未能获得最终快照以进行后续处理。")
            return False
            
        return True

    def _find_peaks(self):
        """检测内存碎片峰值"""
        logger.info("--- 阶段 1b: 检测内存碎片峰值 ---")
        
        # 找到峰值
        if self.final_snapshot:
            frag_data = self.final_snapshot.fragmentation_data
            self.peaks = analysis.find_peaks(frag_data, window=self.settings.peak_detection_window)
            logger.info(f"检测到 {len(self.peaks)} 个碎片峰值: {self.peaks}")
            return True
        else:
            logger.error("最终快照不存在，无法检测峰值。")
            return False

    def get_snapshot_for(self, ts_target: int, initial_ctx: Parser.ParserContext | None = None, 
                        initial_start_idx: int = 0, initial_output: dict | None = None) -> Snapshot | None:
        """
        中心化的快照获取方法，封装了缓存逻辑。
        这是对原 get_snapshot_for 函数的类内版本。
        """
        ts_str = str(ts_target)
        cache_file = os.path.join(self.output_dir, f"cache_{ts_str}.pkl")

        # 1. 检查此时间戳的快照是否已经存在精确缓存
        if not self.settings.no_cache and os.path.exists(cache_file):
            logger.info(f"发现已缓存的精确快照: {cache_file}")
            try:
                with open(cache_file, "rb") as f:
                    snapshot_data = pickle.load(f)
                return Snapshot.from_dict(snapshot_data)
            except Exception as e:
                logger.warning(f"加载缓存 {cache_file} 失败: {e}。将重新生成。")

        # 2. 如果不存在，则从最近的缓存开始解析（如果允许缓存）
        loaded_snapshot: Snapshot | None = None
        loaded_timestamp: str | None = None
        if not self.settings.no_cache:
            loaded_snapshot, loaded_timestamp = SnapshotMngr.load_latest_cache_before(self.output_dir, ts_target)

        current_ctx: Parser.ParserContext = initial_ctx if initial_ctx is not None else Parser.ParserContext()
        current_start_idx: int = initial_start_idx
        current_output: dict = initial_output if initial_output is not None else {"events": [], "fragmentation_data": [], "brk_events": []}

        if loaded_snapshot and loaded_timestamp:
            logger.info(f"从缓存快照 '{loaded_timestamp}' 恢复，为 {ts_target} 进行增量解析...")
            # 如果 ctx 是字典类型，需要转换为 ParserContext
            if isinstance(loaded_snapshot.ctx, dict):
                current_ctx = Parser.ParserContext()
                # 从字典恢复 ParserContext 的状态
                for key, value in loaded_snapshot.ctx.items():
                    if not hasattr(current_ctx, key):
                        continue
                    # 特殊处理 memory_manager 的恢复
                    if key == "memory_manager" and isinstance(value, dict):
                        current_ctx.memory_manager = Parser.MemoryFragmentManager.from_dict(value)
                    # 特殊处理 stack_frame_map 和 reverse_stack_frame_map 的恢复
                    elif key == "stack_frame_map" and isinstance(value, dict):
                        # 恢复 stack_frame_map: dict[int, StackFrame]
                        for frame_id, frame_data in value.items():
                            if isinstance(frame_data, dict):
                                # 从字典恢复 StackFrame 对象
                                frame = Parser.StackFrame(
                                    file=frame_data.get("file", ""),
                                    func=frame_data.get("func", ""),
                                    line=frame_data.get("line", 0),
                                    col=frame_data.get("col", 0)
                                )
                                current_ctx.stack_frame_map[int(frame_id)] = frame
                    elif key == "reverse_stack_frame_map" and isinstance(value, dict):
                        # 恢复 reverse_stack_frame_map: dict[StackFrame, int]
                        for frame_data, frame_id in value.items():
                            if isinstance(frame_data, dict):
                                # 从字典恢复 StackFrame 对象
                                frame = Parser.StackFrame(
                                    file=frame_data.get("file", ""),
                                    func=frame_data.get("func", ""),
                                    line=frame_data.get("line", 0),
                                    col=frame_data.get("col", 0)
                                )
                                current_ctx.reverse_stack_frame_map[frame] = int(frame_id)
                    else:
                        setattr(current_ctx, key, value)
            else:
                current_ctx = loaded_snapshot.ctx
            current_start_idx = loaded_snapshot.next_idx
            # 注意：这里我们只关心最终生成的快照，但解析器需要一个起点来累积数据
            # 确保只包含解析器会修改的键
            current_output = {"events": loaded_snapshot.events, "fragmentation_data": loaded_snapshot.fragmentation_data, "brk_events": loaded_snapshot.brk_events}
        else:
            logger.warning(f"未找到 {ts_target} 之前的有效缓存或禁用缓存，将从头开始解析...")

        # 执行解析并获取快照
        # 这个生成器循环只会执行一次，因为我们只请求了一个时间戳
        snapshot_generated = False

        parser_gen = Parser.extract_events(self.binary_data, snapshots=[ts_target],
                                    ctx=current_ctx, start_idx=current_start_idx, output=current_output)
        
        for snapshot in parser_gen:
            if snapshot.get("timestamp") == ts_target:
                # 缓存这个新生成的精确快照
                SnapshotMngr.save_snapshot_cache(snapshot, ts_target, self.output_dir)
                snapshot_generated = True
                return Snapshot.from_dict(snapshot) # 我们只需要这一个快照

        if not snapshot_generated:
            logger.warning(f"未能为时间戳 {ts_target} 生成快照。可能该时间戳超出了数据范围或解析失败。")
        return None
        
    def _process_peak_details(self):
        """阶段2：为每个峰值生成详细报告"""
        if not self.peaks:
            return
            
        logger.info("--- 阶段 2: 为峰值生成详细报告 ---")
        self._load_binary_data() # 确保数据已加载
        
        all_events_with_frag = analysis.merge_fragmentation_into_events(
            self.final_snapshot.events, self.final_snapshot.fragmentation_data
        )
        
        # 从最终快照中获取所有的 brk 事件，只需执行一次
        all_brk_events = [e for e in all_events_with_frag if e.operation == 'brk']
        
        # 按时间顺序处理，以便后续的峰值可以利用前面峰值生成的缓存
        for i, t_peak in enumerate(sorted(self.peaks)):
            logger.info(f">>>>> 正在处理峰值: {t_peak} ({i+1}/{len(self.peaks)}) <<<<<")
            snapshot = self.get_snapshot_for(t_peak)
            if not snapshot:
                logger.warning(f"未能为时间戳 {t_peak} 获取快照，跳过。")
                continue
                
            # 过滤内存布局
            mem_data_to_write = snapshot.memory_fragments
            focus_regions: list[tuple[int, int]] | None = None # 初始化为 None
            
            # 从 all_events_with_frag 中筛选出在峰值窗口内的事件
            window_start_time = t_peak - self.settings.peak_window
            evs_in_window = [e for e in all_events_with_frag if window_start_time <= e.time <= t_peak]

            # 如果设置了events_after_peak，则在峰值后继续读取指定数量的操作
            if self.settings.events_after_peak > 0:
                logger.info(f"根据 --events-after-peak={self.settings.events_after_peak} 参数，在峰值后继续读取操作...")
                
                # 获取峰值时间点之后的事件
                events_after_peak = [e for e in all_events_with_frag if e.time > t_peak]
                
                # 按时间排序并取前N个事件
                events_after_peak = sorted(events_after_peak, key=lambda e: e.time)[:self.settings.events_after_peak]
                
                # 将这些事件添加到窗口事件列表中
                evs_in_window.extend(events_after_peak)
                
                # 如果有events_after_peak，需要获取峰值后最后一个事件的时间点作为快照时间
                if events_after_peak:
                    last_event_time = events_after_peak[-1].time
                    logger.info(f"获取峰值后最后一个事件时间点: {last_event_time}，作为快照时间点")
                    
                    # 获取峰值后最后一个事件时间点的快照
                    after_peak_snapshot = self.get_snapshot_for(last_event_time)
                    
                    if after_peak_snapshot is not None:
                        # 使用这个新的快照数据
                        snapshot = after_peak_snapshot
                        mem_data_to_write = snapshot.memory_fragments
                    else:
                        logger.warning(f"未能为时间戳[{last_event_time}]获取精确快照，使用峰值时间点的快照")
                        
            if self.settings.enable_peak_focus:
                logger.info(f"过滤内存布局：关注最近 {self.settings.peak_focus_events} 个事件，上下文扩展 {self.settings.peak_focus_context} 字节。")
                # 步骤 1: 统一计算焦点区域
                focus_regions = analysis.calculate_focus_regions_from_events(
                    evs_in_window,
                    num_events=self.settings.peak_focus_events,
                    context_size=self.settings.peak_focus_context
                )
                
                # 步骤 2: 使用计算出的区域过滤 'after' 内存布局
                if focus_regions:
                    mem_data_to_write = analysis.filter_memory_by_regions(
                        snapshot.memory_fragments,
                        focus_regions
                    )
                
                # 根据内存区域过滤事件
                if focus_regions:
                    logger.info(f"根据内存区域过滤事件...")
                    filtered_events = analysis.filter_events_by_memory_regions(evs_in_window, focus_regions)
                    
                    # 只保留最后X个事件
                    num_events_to_keep = self.settings.peak_focus_output_events
                    if num_events_to_keep >= 0:
                        original_count = len(filtered_events)
                        filtered_events = filtered_events[-num_events_to_keep:]
                        logger.info(f"根据 --peak-focus-output-events={num_events_to_keep} 参数，事件从 {original_count} 个过滤到 {len(filtered_events)} 个。")
                    
                    # 更新要导出的事件列表
                    evs_in_window = filtered_events
                
            # 立即导出文件
            logger.info(f"为峰值[{t_peak}]导出详细文件...")
            # 导出内存布局 (使用可能被过滤后的数据)
            mem_file = os.path.join(self.output_dir, f"{t_peak}_memory_fragments_after.json")
            Output.write_memory_fragments(mem_data_to_write, mem_file, t_peak, focus_regions=focus_regions)
            logger.info(f"已导出 after 内存布局: {mem_file}")

            # 导出事件窗口
            # 注意：调用栈深度已在事件生成时根据event_stack_depth参数处理
            # 这里不再需要额外处理callstack_path

            ev_file = os.path.join(self.output_dir, f"{t_peak}_events_with_frag.json")
            Output.write_events(evs_in_window, ev_file)
            logger.info(f"已导出事件记录: {ev_file}")
            
            # 如果启用了峰值前内存布局生成，则生成第一个操作之前的内存布局
            if self.settings.generate_peak_before_layout and evs_in_window:
                # 获取第一个操作的时间
                first_event_time = evs_in_window[0].time
                
                # 获取第一个操作之前时间点的快照
                before_snapshot = self.get_snapshot_for(first_event_time - 1)
                
                if before_snapshot is not None:
                    before_mem_data_to_write = before_snapshot.memory_fragments
                    # 如果计算了焦点区域，则用相同的区域过滤'before'布局
                    if focus_regions:
                        # 步骤 3: 使用相同的区域过滤 'before' 内存布局
                        before_mem_data_to_write = analysis.filter_memory_by_regions(
                            before_snapshot.memory_fragments,
                            focus_regions
                        )
                    
                    # 导出峰值前的内存布局
                    before_mem_file = os.path.join(self.output_dir, f"{t_peak}_memory_fragments_before.json")
                    Output.write_memory_fragments(
                        before_mem_data_to_write, 
                        before_mem_file, 
                        first_event_time - 1,
                        focus_regions=focus_regions
                    )
                    logger.info(f"已导出 before 内存布局: {before_mem_file}")
                else:
                    logger.warning(f"未能为峰值[{t_peak}]生成第一个操作之前的内存布局，无法获取时间点 {first_event_time - 1} 的快照")
            
            logger.info("----------------------------")
        
        # 输出已处理的峰值时间戳和数量
        logger.info(f"已处理 {len(self.peaks)} 个峰值: {sorted(self.peaks)}")

    def _generate_final_reports(self):
        """生成火焰图等最终聚合报告"""
        logger.info("--- 生成最终聚合报告 ---")

        # 输出栈帧映射表
        Output.write_stack_frame_map(
            self.final_snapshot.ctx.stack_frame_map, 
            os.path.join(self.output_dir, "stack_frame_map.json")
        )
        logger.info("栈帧映射表已生成: stack_frame_map.json")

        # 火焰图
        if self.settings.flame:
            logger.info("正在生成火焰图...")
            # 火焰图需要完整的事件列表，因此使用 final_snapshot 中的事件
            flame_graph = analysis.build_flame_graph(
                self.final_snapshot.events, 
                self.final_snapshot.ctx.stack_frame_map
            )
            Output.write_flamegraph(flame_graph, os.path.join(self.output_dir, "flame.json"))
            logger.info("火焰图已生成: flame.json")

        # 完整碎片率数据
        if self.settings.fragmentation:
            logger.info("正在生成碎片率数据...")
            Output.write_fragmentation(self.final_snapshot.fragmentation_data, os.path.join(self.output_dir, "fragmentation.json"))
            logger.info("碎片率数据已生成: fragmentation.json")

        # BRK 事件
        if self.settings.brk_events:
            logger.info("正在生成 BRK 事件数据...")
            Output.write_brk_events(self.final_snapshot.brk_events, os.path.join(self.output_dir, "brk_events.json"))
            logger.info("BRK 事件已生成: brk_events.json")

        logger.info("输出处理完成。")
        
    def _cleanup(self):
        """清理工作，如删除缓存"""
        if self.settings.clear_cache:
            count_deleted = SnapshotMngr.clear_all_cache(self.output_dir)
            logger.info(f"已清理 {count_deleted} 个缓存文件。")

def main():

    processor = MainProcessor(
        config.settings.input, 
        os.path.join(config.settings.input, config.settings.output_dir)
    )
    processor.run()

if __name__ == "__main__":
    main()