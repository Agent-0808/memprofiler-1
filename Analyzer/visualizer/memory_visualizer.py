"""
Copyright (c) 2026, Chen Jie, Joungtao, Xuzheng Jiang
All rights reserved.
This source code is licensed under the BSD-2-Clause license found in the
LICENSE file in the root directory of this source tree.
"""

import json
import tkinter as tk
from tkinter import messagebox
import ttkbootstrap as tb
from dataclasses import dataclass
from typing import Any, Callable
from pathlib import Path
from tap import Tap

import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.font_manager as fm
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

import patchMatplotlib
patchMatplotlib.applyPatch()

# 设置中文字体 (保持原有逻辑，适配不同系统)
font_candidates = ['MiSans', 'SimHei', 'Microsoft YaHei', 'Helvetica', 'Segoe UI', 'DejaVu Sans', 'Liberation Sans', 'sans-serif']
plt.rcParams['font.sans-serif'] = font_candidates
plt.rcParams['axes.unicode_minus'] = False


class Config(Tap):
    """可视化器配置"""
    timestamp: str = "90116493068"  # 时间戳
    benchmark_name: str = "fragmentation_test3"  # 基准测试名称
    base_dir: Path | None = None  # 基础目录

    def configure(self) -> None:
        """配置初始化"""
        if self.base_dir is None:
            self.base_dir = Path(__file__).parent.parent

# --- 1. 数据模型与业务逻辑 (Model & Controller) ---

@dataclass
class MemoryBlock:
    """代表一个连续的内存块。"""
    start_addr: int
    end_addr: int
    status: str  # 'free' 或 'used'

    @property
    def size(self) -> int:
        return self.end_addr - self.start_addr

class MemoryLayout:
    """管理整个堆的内存布局。"""
    def __init__(self):
        self.blocks: list[MemoryBlock] = []
        self.heap_size: int = 0
        self.focus_regions: list[list[int]] = []
        self._initial_filepath: str | None = None
        # 缓存初始状态
        self._initial_blocks: list[MemoryBlock] | None = None
        self._initial_heap_size: int | None = None

    def load_from_file(self, filepath: str) -> None:
        self._initial_filepath = filepath
        print(f"Loading memory layout from {filepath}...")
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error loading memory layout: {e}")
            return

        self.heap_size = data['summary']['total_memory']
        self.heap_size = max(self.heap_size, 1) # 防止为0
        
        if not self.focus_regions:
            self.focus_regions = data.get('focus_regions', [])

        # 从文件中解析已知的内存片段
        file_blocks: list[MemoryBlock] = []
        for segment in data.get('memory_segments', []):
            current_addr = segment['start_addr']
            for end_addr, status_code in segment['fragments']:
                if end_addr > current_addr:
                    status = 'used' if status_code == 1 else 'free'
                    file_blocks.append(MemoryBlock(current_addr, end_addr, status))
                current_addr = end_addr
        
        file_blocks.sort(key=lambda b: b.start_addr)
        
        # 构建完整的、无间隙的内存布局
        complete_blocks: list[MemoryBlock] = []
        current_addr = 0
        for block in file_blocks:
            # 如果当前块与上一块之间有空隙，则用一个 'used' 块填充
            # 这代表了我们不了解其具体布局的区域
            if block.start_addr > current_addr:
                complete_blocks.append(MemoryBlock(current_addr, block.start_addr, 'used'))
            
            # 添加文件中有明确记录的块
            complete_blocks.append(block)
            current_addr = block.end_addr

        # 填充从最后一个已知块到堆末尾的剩余空间
        if current_addr < self.heap_size:
            complete_blocks.append(MemoryBlock(current_addr, self.heap_size, 'used'))
        
        # 如果文件块为空，则整个堆都是一个大的未知区域
        if not complete_blocks and self.heap_size > 0:
            complete_blocks.append(MemoryBlock(0, self.heap_size, 'used'))

        self.blocks = complete_blocks
        
        # 深拷贝保存初始状态
        self._initial_blocks = [MemoryBlock(b.start_addr, b.end_addr, b.status) for b in self.blocks]
        self._initial_heap_size = self.heap_size

    def reset(self) -> None:
        if self._initial_blocks is not None and self._initial_heap_size is not None:
            self.blocks = [MemoryBlock(b.start_addr, b.end_addr, b.status) for b in self._initial_blocks]
            self.heap_size = self._initial_heap_size
        elif self._initial_filepath:
            self.load_from_file(self._initial_filepath)

    def apply_alloc(self, start: int, end: int) -> None:
        for i, block in enumerate(self.blocks):
            if block.status == 'free' and block.start_addr <= start and block.end_addr >= end:
                new_blocks = []
                if block.start_addr < start:
                    new_blocks.append(MemoryBlock(block.start_addr, start, 'free'))
                new_blocks.append(MemoryBlock(start, end, 'used'))
                if block.end_addr > end:
                    new_blocks.append(MemoryBlock(end, block.end_addr, 'free'))
                self.blocks[i:i+1] = new_blocks
                return

    def apply_free(self, start: int, end: int) -> None:
        for block in self.blocks:
            if block.status == 'used' and block.start_addr == start and block.end_addr == end:
                block.status = 'free'
                self._merge_free_blocks()
                return

    def _merge_free_blocks(self) -> None:
        if not self.blocks: return
        merged = [self.blocks[0]]
        for curr in self.blocks[1:]:
            last = merged[-1]
            if last.status == 'free' and curr.status == 'free' and last.end_addr == curr.start_addr:
                last.end_addr = curr.end_addr
            else:
                merged.append(curr)
        self.blocks = merged

    def apply_brk(self, new_heap_size: int) -> None:
        old_size = self.heap_size
        if new_heap_size > old_size:
            self.blocks.append(MemoryBlock(old_size, new_heap_size, 'free'))
            self._merge_free_blocks()
        elif new_heap_size < old_size:
            self.blocks = [b for b in self.blocks if b.start_addr < new_heap_size]
            if self.blocks and self.blocks[-1].end_addr > new_heap_size:
                self.blocks[-1].end_addr = new_heap_size
        self.heap_size = new_heap_size

class EventProcessor:
    """处理事件流逻辑。"""
    def __init__(self, memory_layout: MemoryLayout):
        self.events: list[dict[str, Any]] = []
        self.current_event_index: int = -1
        self.memory_layout = memory_layout
        self.stack_frame_map: dict[str, dict[str, Any]] = {}

    def load_data(self, events_path: str, stack_path: str) -> None:
        # 1. Load Events
        try:
            with open(events_path, 'r', encoding='utf-8') as f:
                self.events = json.load(f)
            print(f"Loaded {len(self.events)} events.")
        except Exception as e:
            print(f"Error loading events: {e}")

        # 2. Load Stack Map
        try:
            with open(stack_path, 'r', encoding='utf-8') as f:
                self.stack_frame_map = json.load(f)
        except Exception:
            print("Stack frame map not found or invalid.")

    def step_forward(self) -> dict[str, Any] | None:
        if self.current_event_index >= len(self.events) - 1:
            return None

        self.current_event_index += 1
        event = self.events[self.current_event_index]

        try:
            op = event['operation']
            
            # 兼容brk事件没有range的情况
            if op == 'brk':
                # brk 操作通常只关心结束地址，即新的堆大小
                new_heap_size = int(event['range'].split('-')[1])
                self.memory_layout.apply_brk(new_heap_size)
            else:
                start_str, end_str = event['range'].split('-')
                start, end = int(start_str), int(end_str)
                if op == 'alloc':
                    self.memory_layout.apply_alloc(start, end)
                elif op == 'free':
                    self.memory_layout.apply_free(start, end)
        except (KeyError, ValueError, IndexError) as e:
            print(f"\n--- [WARNING] FAILED TO PROCESS EVENT ---")
            print(f"Step: {self.current_event_index + 1}")
            print(f"Event data: {json.dumps(event)}")
            print(f"Error: {e}")
            print(f"This event will be skipped, visualization may be inaccurate.")
            print(f"-----------------------------------------\n")
            # 即使处理失败，也返回事件本身，以便UI可以高亮显示问题所在
        
        return event

    def reset(self) -> None:
        self.current_event_index = -1
        self.memory_layout.reset()

    """处理事件流逻辑。"""
    def goto_step(self, target_step: int) -> dict[str, Any] | None:
        target_idx = target_step - 1
        if not (0 <= target_idx < len(self.events)):
            return None

        # 如果目标在前面，或者就是当前位置但需要重绘，则重置
        if target_idx <= self.current_event_index:
            self.reset()
        
        # 循环处理直到目标步骤的前一步
        # 我们希望循环结束后，current_event_index 是 target_idx - 1
        while self.current_event_index < target_idx - 1:
            self.step_forward() # 在内部推进状态，但不关心返回值
            
        # 执行并返回最后一步，即目标步骤
        return self.step_forward()

    def get_stack_str(self, event: dict | None) -> str:
        if not event: return ""
        ids = event.get('callstack_path', [])[:10]
        lines = [
            f"{i+1}. {self.stack_frame_map.get(str(fid), {}).get('func', '<unknown>')}"
            f" @ {Path(self.stack_frame_map.get(str(fid), {}).get('file', '')).name}"
            f":{self.stack_frame_map.get(str(fid), {}).get('line', '')}"
            if self.stack_frame_map.get(str(fid), {}).get('file') else
            f"{i+1}. {self.stack_frame_map.get(str(fid), {}).get('func', '<unknown>')}"
            for i, fid in enumerate(ids)
        ]
        return "\n".join(lines) if lines else "N/A"

# --- 2. UI 界面类 (View) ---

class MemoryVisualizerApp:
    COLORS = {
        'used': 'royalblue',
        'free': 'grey',            # 空闲内存 - 灰色
        'highlight': 'red',
        'focus': 'lightyellow'     # 关注区域 - 浅黄色
    }

    def __init__(self, root: tk.Tk, processor: EventProcessor):
        self.root = root
        self.processor = processor
        self.layout = processor.memory_layout
        
        self.root.title("Memory Fragmentation Visualizer")
        # self.root.geometry("1400x800") # 移除硬编码，由外部控制或自适应
        
        # 状态变量
        self.is_playing = False
        self.play_speed = 10.0 # events per second
        self.view_initialized = False
        
        # --- [修复] 防止递归调用的标志位 ---
        self.ignore_selection_change = False

        self._setup_ui()
        
        # 延迟初始绘制，确保窗口布局完成
        # self.root.after(200, self._initial_draw)
        # 有了独立的 plot_frame，可能不再需要延迟绘制，但为了保险起见，保留一次重绘
        self.root.after(100, lambda: self.draw_memory(None, reset_view_limits=True))

    def _initial_draw(self):
        """初始绘制，确保 Canvas 获取正确尺寸"""
        # 再次强制更新布局信息
        self.root.update_idletasks()
        self.draw_memory(None, reset_view_limits=True)

    def _setup_ui(self):
        """构建整体 UI 布局"""
        # 2. 右侧信息栏 (事件列表 + 调用栈) - 优先 pack 以保证不被遮挡
        right_panel = tb.Frame(self.root, width=350)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=5, pady=5)

        # 1. 顶部工具栏和绘图区 (左侧)
        left_panel = tb.Frame(self.root)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # [布局调整] 优先 pack 底部控制面板，确保其在窗口缩小时不被遮挡
        control_frame = tb.LabelFrame(left_panel, text="Controls")
        control_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
        self._setup_controls(control_frame)

        # [新增] 顶部状态信息标签 (替代 Matplotlib 标题)
        self.lbl_status = tb.Label(left_panel, text="Ready", anchor="center")
        self.lbl_status.pack(side=tk.TOP, fill=tk.X)
        
        # [重构] 创建专门的绘图容器
        self.plot_frame = tb.Frame(left_panel)
        self.plot_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # [优化] 初始尺寸设小一点，避免撑大布局，依靠 pack(expand=True) 自动拉伸
        self.fig = Figure(figsize=(5, 4), dpi=100)
        # [优化] 减少留白
        self.fig.subplots_adjust(left=0.02, right=0.98, top=0.98, bottom=0.15)
        
        self.ax = self.fig.add_subplot(111)
        
        # 嵌入 Matplotlib Canvas
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        self.canvas.draw()

        # 添加原生导航工具栏 (Zoom, Pan, Save) - 先 pack 到底部
        self.toolbar = NavigationToolbar2Tk(self.canvas, self.plot_frame)
        self.toolbar.update()
        self.toolbar.pack(side=tk.BOTTOM, fill=tk.X)

        # 将画布的 Tkinter 组件放入框架 - 后 pack 到顶部，expand=True
        canvas_widget = self.canvas.get_tk_widget()
        canvas_widget.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        # 事件列表 (Treeview)
        event_frame = tb.LabelFrame(right_panel, text="Events", height=6)
        event_frame.pack(side=tk.TOP, fill=tk.BOTH, pady=5)
        
        # 使用 grid 布局以支持双向滚动条
        event_frame.columnconfigure(0, weight=1)
        event_frame.rowconfigure(0, weight=1)
        
        columns = ("step", "time", "op", "size")
        self.event_list = tb.Treeview(event_frame, columns=columns, show="headings", height=10, selectmode="browse")

        self.event_list.heading("step", text="Step")
        self.event_list.column("step", width=50, anchor=tk.CENTER, stretch=False)

        self.event_list.heading("time", text="Time")
        self.event_list.column("time", width=88, anchor=tk.E, stretch=False)

        self.event_list.heading("op", text="Op.")
        self.event_list.column("op", width=55, anchor=tk.CENTER, stretch=False)
        
        self.event_list.heading("size", text="Size")
        self.event_list.column("size", width=55, anchor=tk.E, stretch=False)
        
        # 滚动条
        vsb = tb.Scrollbar(event_frame, orient="vertical", command=self.event_list.yview)
        hsb = tb.Scrollbar(event_frame, orient="horizontal", command=self.event_list.xview)
        self.event_list.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.event_list.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        # 绑定点击跳转
        self.event_list.bind("<<TreeviewSelect>>", self._on_tree_select)
        
        # 填充事件列表
        self._populate_event_list()

        # 调用栈显示
        stack_frame = tb.LabelFrame(right_panel, text="Callstack")
        stack_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, pady=5)
        
        # 使用 grid 布局以支持双向滚动条
        stack_frame.columnconfigure(0, weight=1)
        stack_frame.rowconfigure(0, weight=1)
        
        self.stack_text = tk.Text(stack_frame, height=15, width=40, font=("Consolas", 9), wrap="none")
        
        vsb = tb.Scrollbar(stack_frame, orient="vertical", command=self.stack_text.yview)
        hsb = tb.Scrollbar(stack_frame, orient="horizontal", command=self.stack_text.xview)
        self.stack_text.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.stack_text.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

    def _setup_controls(self, parent):
        """底部控制按钮布局"""
        # 布局网格
        parent.columnconfigure(tuple(range(12)), weight=1)
        
        # 跳转功能
        tb.Label(parent, text="Jump to:").grid(row=0, column=0, padx=5)
        self.ent_goto = tb.Entry(parent, width=8)
        self.ent_goto.grid(row=0, column=1, padx=2)
        self.ent_goto.bind("<Return>", lambda e: self._goto_step())
        tb.Button(parent, text="Go", command=self._goto_step, width=4).grid(row=0, column=2, padx=2)

        # 视图控制
        tb.Button(parent, text="Reset View", command=self._reset_view).grid(row=0, column=3, padx=5)

        # 播放控制
        tb.Button(parent, text="⏮ Reset", command=self._reset_simulation).grid(row=0, column=4, padx=2)
        self.btn_play = tb.Button(parent, text="▶ Play", command=self._toggle_play)
        self.btn_play.grid(row=0, column=5, padx=2)
        tb.Button(parent, text="⏭ Step", command=self._step_once).grid(row=0, column=6, padx=2)
        
        # 速度控制
        tb.Label(parent, text="Speed").grid(row=0, column=8, padx=5, sticky=tk.E)
        self.scale_speed = tb.Scale(parent, from_=1, to=50, value=10, command=self._on_speed_change)
        self.scale_speed.grid(row=0, column=9, sticky=tk.EW, padx=5)
        self.lbl_speed = tb.Label(parent, text="10/s")
        self.lbl_speed.grid(row=0, column=10, sticky=tk.W)

    def _populate_event_list(self):
        """显示所有事件"""
        for i, event in enumerate(self.processor.events):
            # 插入树节点，values=(step_num, time, op, size)
            self.event_list.insert("", tk.END, iid=str(i+1),
                values=(i+1, event['time'], event['operation'], event['size']))

    # --- 交互回调 ---

    def _on_speed_change(self, val):
        self.play_speed = float(val)
        self.lbl_speed.config(text=f"{int(self.play_speed)}/s")

    def _toggle_play(self):
        if self.is_playing:
            self.is_playing = False
            self.btn_play.config(text="▶ Play")
        else:
            self.is_playing = True
            self.btn_play.config(text="⏸ Pause")
            self._auto_step_loop()

    def _auto_step_loop(self):
        if not self.is_playing:
            return

        event = self.processor.step_forward()

        # 1. 首先检查是否已到达事件流末尾
        if event is None:
            self.is_playing = False
            self.btn_play.config(text="▶ Play")
            # 只有在真正结束后才弹窗
            if self.processor.current_event_index >= len(self.processor.events) - 1:
                 messagebox.showinfo("Simulation End", "Reached the end of the event stream.")
            return

        # 2. 如果事件有效，则绘制内存状态
        self.draw_memory(event)

        # 3. 调度下一次执行
        delay = int(1000 / self.play_speed)
        self.root.after(delay, self._auto_step_loop)

    def _step_once(self):
        self.is_playing = False
        self.btn_play.config(text="▶ Play")
        event = self.processor.step_forward()
        self.draw_memory(event)

    def _reset_simulation(self):
        self.is_playing = False
        self.btn_play.config(text="▶ Play")
        self.processor.reset()
        self.draw_memory(None)

    def _reset_view(self):
        self.draw_memory(None, reset_view_limits=True)

    def _goto_step(self):
        try:
            step = int(self.ent_goto.get())
            self.is_playing = False
            self.btn_play.config(text="▶ Play")
            
            event = self.processor.goto_step(step)
            self.draw_memory(event)
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid step number.")

    def _on_tree_select(self, event):
        # 如果是程序自动更新触发的，直接返回，不执行跳转逻辑
        if self.ignore_selection_change:
            return

        selected = self.event_list.selection()
        if not selected: return
        
        # 树的 iid 我们设置为了步骤编号 (str)
        step = int(selected[0])
        
        # 只有当点击的步骤与当前步骤不同时才执行跳转（防止重复刷新）
        if step == self.processor.current_event_index + 1:
            return

        self.is_playing = False
        self.btn_play.config(text="▶ Play")
        
        # 跳转
        evt = self.processor.goto_step(step)
        self.draw_memory(evt)

    # --- 绘图与更新逻辑 ---

    def draw_memory(self, current_event: dict | None, reset_view_limits: bool = False):
        """核心绘图函数"""
        # 保存当前视图范围，避免重绘时跳动
        if self.view_initialized and not reset_view_limits:
            xlim = self.ax.get_xlim()
            ylim = self.ax.get_ylim()
        else:
            xlim, ylim = None, None

        self.ax.clear()
        
        # 1. 绘制关注区域高亮
        if self.layout.focus_regions:
            for start, end in self.layout.focus_regions:
                self._draw_focus_region(start, end)

        # 2. 绘制内存块
        for block in self.layout.blocks:
            self.ax.add_patch(patches.Rectangle(
                (block.start_addr, 0), block.size, 0.5,
                facecolor=self.COLORS.get(block.status, 'black'),
                edgecolor='white', linewidth=0.5
            ))

        # 3. 高亮当前操作
        if current_event:
            # 修复：正确处理所有事件的 range
            try:
                s_str, e_str = current_event['range'].split('-')
                start, end = int(s_str), int(e_str)

                # 对于 brk 操作，高亮的是新增的区域
                width = end - start

                self.ax.add_patch(patches.Rectangle(
                    (start, 0), width, 0.5,
                    fill=False, edgecolor=self.COLORS['highlight'],
                    linewidth=2.5,
                    linestyle='--'
                ))
            except (ValueError, KeyError):
                # 如果事件没有 'range' 或格式不正确，则不进行高亮
                print(f"信息: 事件 {self.processor.current_event_index + 1} ({current_event.get('operation')}) 没有有效的 'range' 字段，跳过高亮。")


        # 4. 更新标题和文本
        self._update_title(current_event)
        self._update_stack_display(current_event)

        # 5. 设置坐标轴和视图
        self.ax.set_yticks([])
        self.ax.set_xlabel("Memory Address")
        self.ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format(int(x), ',')))
        self.ax.set_ylim(-0.2, 0.7) # 固定 Y 轴

        # 智能设置 X 轴范围
        if reset_view_limits or not self.view_initialized:
            if self.layout.focus_regions:
                min_start = min(r[0] for r in self.layout.focus_regions)
                max_end = max(r[1] for r in self.layout.focus_regions)
                margin = (max_end - min_start) * 0.1 if max_end > min_start else 100
                self.ax.set_xlim(max(0, min_start - margin), max_end + margin)
            else:
                self.ax.set_xlim(0, max(self.layout.heap_size, 100))
            self.view_initialized = True
        elif xlim:
            self.ax.set_xlim(xlim)
            self.ax.set_ylim(ylim)

        # 刷新画布
        self.canvas.draw()
        
        # 同步事件列表选中状态
        if current_event:
            step_idx = self.processor.current_event_index + 1
            iid = str(step_idx)
            
            if self.event_list.exists(iid):
                # 检查当前是否已经选中了该项，如果是，则跳过，减少闪烁和事件触发
                current_selection = self.event_list.selection()
                if not current_selection or current_selection[0] != iid:
                    # 设置标志位，屏蔽事件回调
                    self.ignore_selection_change = True
                    try:
                        # 先清除旧选择（Tkinter有时候多选行为很奇怪）
                        if current_selection:
                            self.event_list.selection_remove(current_selection)
                        self.event_list.selection_set(iid)
                        self.event_list.see(iid)
                    finally:
                        # 确保标志位被还原
                        self.ignore_selection_change = False
            else:
                # 如果当前步不是关键事件，取消选中
                if self.event_list.selection():
                    self.ignore_selection_change = True
                    try:
                        self.event_list.selection_remove(self.event_list.selection())
                    finally:
                        self.ignore_selection_change = False
        elif self.processor.current_event_index == -1:
             if self.event_list.selection():
                self.ignore_selection_change = True
                try:
                    self.event_list.selection_remove(self.event_list.selection())
                finally:
                    self.ignore_selection_change = False

    def _draw_focus_region(self, start, end):
        """绘制关注区域高亮背景"""
        self.ax.add_patch(patches.Rectangle(
            (start, -0.1), end - start, 0.7,
            facecolor=self.COLORS['focus'], alpha=0.6,
            edgecolor='orange', linewidth=1.5,  # 添加橙色描边
            zorder=0  # 背景在最底层
        ))

    def _update_title(self, event: dict | None):
        if not event:
            title = "Initial" if self.processor.current_event_index == -1 else "End"
        else:
            idx = self.processor.current_event_index + 1
            total = len(self.processor.events)
            op_text = event['operation'].upper()
            title = (f"Step {idx}/{total} | Time: {event['time']} | {op_text} ({event['size']}B) | "
                     f"Addr: {event['range']} "
                     f"\n Frag: {event['fragmentation_ratio']:.1%} | Free: {event['free_ratio']:.1%} | Impact Score: {event['impact_score']:.1%}")
        
        # 更新 Tkinter 标签而不是 Matplotlib 标题
        self.lbl_status.config(text=title)
        # self.ax.set_title(title, loc='left', fontsize=10)

    def _update_stack_display(self, event: dict | None):
        self.stack_text.delete(1.0, tk.END)
        text = self.processor.get_stack_str(event)
        self.stack_text.insert(tk.END, text)

def launch_visualizer_window(master_root, timestamp: str, benchmark_name: str, base_dir: Path):
    """
    供外部调用的启动函数，弹出一个新的 Toplevel 窗口显示可视化器
    """
    # 1. 构建配置
    config = Config()
    config.timestamp = str(timestamp) # 确保是字符串
    config.benchmark_name = benchmark_name
    config.base_dir = base_dir
    # config.configure() # Tap 的 configure 通常处理参数解析，这里手动设置即可，如果有自定义逻辑需手动调用

    # 路径解析
    data_dir = base_dir / f"tracedata/{config.benchmark_name}/output"

    files = {
        'frag_before': data_dir / f"{config.timestamp}_memory_fragments_before.json",
        'events': data_dir / f"{config.timestamp}_events_with_frag.json",
        'stack': data_dir / "stack_frame_map.json"
    }

    # 检查关键文件
    if not files['frag_before'].exists():
        messagebox.showerror("File Missing", f"Could not find the data file for this timestamp:\n{files['frag_before']}", parent=master_root)
        return

    # 2. 创建 Toplevel 窗口 (子窗口)
    window = tb.Toplevel(master_root)
    window.title(f"Visualizer - {timestamp}")
    
    # 适配高 DPI
    try:
        ppi = window.winfo_fpixels('1i')
        scale_factor = ppi / 96.0
        if scale_factor > 1.0:
            width = int(1400 * scale_factor)
            height = int(800 * scale_factor)
            window.geometry(f"{width}x{height}")
            print(f"高 DPI 模式，缩放比例: {scale_factor:.2f}")
        else:
            window.geometry("1400x800")
    except Exception:
        window.geometry("1400x800")

    # 3. 初始化逻辑
    layout = MemoryLayout()
    processor = EventProcessor(layout)
    
    # 加载数据
    try:
        layout.load_from_file(str(files['frag_before']))
        processor.load_data(str(files['events']), str(files['stack']))
    except Exception as e:
        messagebox.showerror("Load Failed", f"Data loading error: {e}", parent=window)
        window.destroy()
        return

    # 4. 启动 UI App，绑定到新窗口
    app = MemoryVisualizerApp(window, processor)
    
    # 强制更新布局，确保 Canvas 获取正确尺寸
    # window.update()
    # window.update_idletasks()
    
    # app.draw_memory(None, reset_view_limits=True)

# --- Main Entry ---

def main():
    config = Config(underscores_to_dashes=True).parse_args()
    config.configure()
    
    # 路径解析
    base_dir = config.base_dir
    data_dir = base_dir / f"tracedata/{config.benchmark_name}/output"

    files = {
        'frag_before': data_dir / f"{config.timestamp}_memory_fragments_before.json",
        'events': data_dir / f"{config.timestamp}_events_with_frag.json",
        'stack': data_dir / "stack_frame_map.json"
    }

    # 1. 初始化逻辑
    layout = MemoryLayout()
    processor = EventProcessor(layout)
    
    # 2. 加载数据
    if not files['frag_before'].exists():
        messagebox.showerror("Error", f"Data file not found:\n{files['frag_before']}")
        return

    layout.load_from_file(str(files['frag_before']))
    processor.load_data(str(files['events']), str(files['stack']))

    # 3. 启动 UI
    # root = tb.Window(themename="cosmo")
    root = tk.Tk()

    # 适配高 DPI：根据屏幕 PPI 调整窗口大小
    try:
        # 获取屏幕 PPI (通常 Windows 标准是 96)
        ppi = root.winfo_fpixels('1i')
        scale_factor = ppi / 96.0
        if scale_factor > 1.0:
            width = int(1400 * scale_factor)
            height = int(800 * scale_factor)
            root.geometry(f"{width}x{height}")
        else:
            root.geometry("1400x800")
    except Exception:
        root.geometry("1400x800")

    # 设置一些全局样式
    # style = ttk.Style()
    # style.theme_use('clam')  # 使用更现代的主题
    
    app = MemoryVisualizerApp(root, processor)
    
    # 强制更新布局，确保 Canvas 获取正确尺寸
    # root.update()
    # root.update_idletasks()
    
    # 初始绘制
    # app.draw_memory(None, reset_view_limits=True)
    
    root.mainloop()

if __name__ == "__main__":
    main()