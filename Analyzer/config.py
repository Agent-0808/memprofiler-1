"""
Copyright (c) 2026, Chen Jie, Joungtao, Xuzheng Jiang
All rights reserved.
This source code is licensed under the BSD-2-Clause license found in the
LICENSE file in the root directory of this source tree.
"""

# config.py
from tap import Tap

class Config(Tap):
    """应用程序的配置模型"""

    # --- Input & Output ---
    input: str  # 输入文件路径
    output_dir: str = "output"  # 输出目录
    clear_output_dir: bool = False  # 是否清空输出目录
    compact_json: bool = False  # 是否生成紧凑的JSON格式

    # --- Report Generation ---
    flame: bool = False  # 是否生成火焰图
    fragmentation: bool = False  # 是否生成碎片化报告
    brk_events: bool = False  # 是否生成brk事件报告
    memory_layout: bool = False  # 是否生成内存布局报告
    final_events: bool = False  # 是否生成最终事件报告
    report_for_snapshots: bool = False  # 是否为快照生成报告

    # --- Snapshot Control ---
    timestamps: str | None = None  # 指定时间戳
    snapshot_interval: int | None = None  # 快照间隔

    # --- Peak Analysis ---
    peak_window: int = 500000000  # 峰值窗口大小
    peak_detection_window: int = 500  # 峰值检测窗口
    callstack_depth: int = -1  # 调用栈深度
    events_after_peak: int = 0  # 峰值后的事件数

    # --- Peak Focus ---
    enable_peak_focus: bool = False  # 是否启用峰值聚焦
    peak_focus_events: int = 50  # 峰值聚焦事件数
    peak_focus_context: int = 8192  # 峰值聚焦上下文
    peak_focus_output_events: int = 500  # 峰值聚焦输出事件数
    generate_peak_before_layout: bool = False  # 是否在布局前生成峰值

    # --- Cache Management ---
    no_cache: bool = False  # 是否禁用缓存
    clear_cache: bool = False  # 是否清空缓存

    # --- Advanced Settings ---
    log_interval: int = 2000  # 日志间隔
    skip_cpp: bool = False  # 是否跳过C++处理


# 全局配置实例
settings: Config = None


def initialize_config() -> None:
    """解析命令行参数并初始化全局的 `settings` 对象"""
    global settings
    if settings is not None:
        return
    settings = Config(underscores_to_dashes=True).parse_args()