import json
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from tap import Tap

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from memory_visualizer import launch_visualizer_window

# 设置中文字体
font_candidates = ['MiSans', 'SimHei', 'Microsoft YaHei', 'Helvetica', 'Segoe UI', 'DejaVu Sans', 'Liberation Sans', 'sans-serif']
plt.rcParams['font.sans-serif'] = font_candidates
plt.rcParams['axes.unicode_minus'] = False

class Config(Tap):
    """内存指标可视化配置"""
    timestamp: str = "final"
    benchmark_name: str = "test_case"
    base_dir: Path | None = None

    def configure(self) -> None:
        """配置初始化"""
        if self.base_dir is None:
            self.base_dir = Path(__file__).parent.parent

def load_events(config: Config) -> tuple[list[dict[str, object]], list[int]]:
    """加载事件数据并识别 brk 事件"""
    data_dir = config.base_dir / f"tracedata/{config.benchmark_name}/output"
    events_path = data_dir / f"{config.timestamp}_events_with_frag.json"
    
    print(f"正在加载数据: {events_path}")
    
    if not events_path.exists():
        raise FileNotFoundError(f"找不到数据文件: {events_path}")
        
    try:
        with open(events_path, 'r', encoding='utf-8') as f:
            events = json.load(f)
        print(f"成功加载 {len(events)} 个事件")
        
        # 识别 brk 事件
        brk_timestamps = []
        for event in events:
            if event.get('operation') == 'brk':
                brk_timestamps.append(event.get('time'))
        print(f"找到 {len(brk_timestamps)} 个 brk 事件")
        
        return events, brk_timestamps
    except Exception as e:
        print(f"加载数据失败: {e}")
        return [], []

def scan_peak_timestamps(config: Config) -> list[int]:
    """扫描目录下所有符合模式的文件并提取时间戳"""
    data_dir = config.base_dir / f"tracedata/{config.benchmark_name}/output"
    peaks = []
    
    if not data_dir.exists():
        return peaks
        
    # 查找所有 *_events_with_frag.json 文件
    for file_path in data_dir.glob("*_events_with_frag.json"):
        try:
            # 提取文件名中的时间戳部分 (假设格式为 TIMESTAMP_events_with_frag.json)
            timestamp_str = file_path.name.split('_')[0]
            if timestamp_str.isdigit():
                peaks.append(int(timestamp_str))
        except Exception:
            continue
            
    print(f"找到 {len(peaks)} 个 Peak 时间点: {peaks}")
    return sorted(peaks)

class MetricsPlotterApp:
    """指标可视化主程序"""
    
    def __init__(self, root: tk.Tk, config: Config):
        self.root = root
        self.config = config
        self.events: list[dict[str, object]] = []
        self.peak_timestamps: list[int] = []
        self.brk_timestamps: list[int] = []
        
        self.root.title(f"Memory Metrics - {config.benchmark_name}")
        self.root.geometry("1400x800")
        
        self._setup_ui()
        self._load_data()
        self._plot_metrics()
    
    def _setup_ui(self):
        """构建 UI 布局"""
        # 主容器
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 顶部状态栏
        self.lbl_status = ttk.Label(main_frame, text="Ready", anchor="center")
        self.lbl_status.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        
        # Matplotlib 图表区域
        self.fig = Figure(figsize=(12, 6), dpi=100)
        self.ax1 = self.fig.add_subplot(111)
        
        # 嵌入 Matplotlib Canvas
        self.canvas = FigureCanvasTkAgg(self.fig, main_frame)
        self.canvas.draw()
        
        # 添加导航工具栏
        toolbar = NavigationToolbar2Tk(self.canvas, main_frame)
        toolbar.update()
        
        # 绑定 pick 事件
        self.canvas.mpl_connect('pick_event', self._on_pick)
        
        # 布局
        # toolbar.pack(side=tk.TOP, fill=tk.X)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
    
    def _load_data(self):
        """加载数据"""
        try:
            self.events, self.brk_timestamps = load_events(self.config)
            self.peak_timestamps = scan_peak_timestamps(self.config)
            self.lbl_status.config(text=f"Loaded {len(self.events)} events, {len(self.peak_timestamps)} peaks")
        except Exception as e:
            self.lbl_status.config(text=f"Loading failed: {e}")
            print(f"Error: {e}")
    
    def _plot_metrics(self):
        """绘制指标折线图"""
        if not self.events:
            print("没有数据可绘制")
            return

        # 提取数据
        times = []
        frag_ratios = []
        free_ratios = []
        impact_scores = []
        
        start_time = self.events[0]['time'] if self.events else 0
        
        for event in self.events:
            # 确保所有指标都存在
            if 'fragmentation_ratio' in event and 'free_ratio' in event and 'impact_score' in event:
                # 过滤掉 None 值
                if (event['fragmentation_ratio'] is not None and 
                    event['free_ratio'] is not None and 
                    event['impact_score'] is not None):
                    
                    # 使用原始时间戳
                    times.append(event['time'])
                    frag_ratios.append(event['fragmentation_ratio'])
                    free_ratios.append(event['free_ratio'])
                    impact_scores.append(event['impact_score'])

        if not times:
            print("没有包含完整指标的事件数据")
            return

        # 清空图表
        self.ax1.clear()
        
        # 绘制左轴数据 (Ratios)
        color_frag = 'tab:red'
        color_free = 'tab:blue'
        
        l1, = self.ax1.plot(times, frag_ratios, color=color_frag, label='Fragmentation Ratio', linewidth=1.0)
        l2, = self.ax1.plot(times, free_ratios, color=color_free, label='Free Ratio', linewidth=1.5, linestyle='--')
        
        self.ax1.set_xlabel('Time (ns)')
        
        # 禁用科学计数法和偏移
        formatter = ticker.ScalarFormatter(useOffset=False)
        formatter.set_scientific(False)
        self.ax1.xaxis.set_major_formatter(formatter)

        self.ax1.set_ylabel('Ratio', color='black')
        self.ax1.tick_params(axis='y', labelcolor='black')
        self.ax1.set_ylim(0, 1)
        
        # 绘制 y=0 和 y=1 的实线
        self.ax1.axhline(y=0, color='black', linewidth=1)
        self.ax1.axhline(y=1, color='black', linewidth=1)
        
        self.ax1.grid(True, alpha=0.3)

        # 绘制右轴数据 (Score)
        ax2 = self.ax1.twinx()
        color_score = 'tab:orange'
        
        l3, = ax2.plot(times, impact_scores, color=color_score, label='Impact Score', linewidth=2.0)
        
        ax2.set_ylabel('Impact Score', color=color_score)
        ax2.tick_params(axis='y', labelcolor=color_score)
        ax2.set_ylim(0, 1)
        
        # 添加 Peak 标记（可点击）
        if self.peak_timestamps:
            # 获取当前X轴范围，用于判断标记是否在视图内
            x_min, x_max = min(times), max(times)
            
            for peak in self.peak_timestamps:
                # 只绘制在当前数据时间范围内的标记
                if x_min <= peak <= x_max:
                    # 绘制可见的绿色虚线
                    self.ax1.axvline(x=peak, color='green', linestyle=':', alpha=0.6, linewidth=1.5)
                    # 添加文本标注（可点击）
                    text_artist = self.ax1.text(peak, -0.08, str(peak), transform=self.ax1.get_xaxis_transform(),
                                              rotation=0, ha='center', va='top', fontsize=7, color='green',
                                              picker=5,
                                              bbox=dict(boxstyle='round,pad=0.3',
                                                       facecolor='white',
                                                       edgecolor='green',
                                                       alpha=0.8))
                    text_artist.peak_timestamp = peak
                    # 绘制透明的宽线用于点击检测（覆盖整条竖线）
                    hit_line = self.ax1.axvline(x=peak, color='green', alpha=0.0, linewidth=30, picker=5)
                    # 将时间戳存储在 line 对象中
                    hit_line.peak_timestamp = peak
        
        # 添加 brk 事件标记
        if self.brk_timestamps:
            x_min, x_max = min(times), max(times)
            
            for brk_time in self.brk_timestamps:
                if x_min <= brk_time <= x_max:
                    # 绘制虚线
                    self.ax1.axvline(x=brk_time, color='grey', linestyle='--', alpha=0.7, linewidth=1.2)
                    # 添加文本标注
                    self.ax1.text(brk_time, 0.98, 'BRK', transform=self.ax1.get_xaxis_transform(),
                                 rotation=90, ha='center', va='top', fontsize=7, color='grey')

        # 合并图例
        lines = [l1, l2, l3]
        labels = [l.get_label() for l in lines]
        self.ax1.legend(lines, labels, loc='upper right')
        
        self.ax1.set_title('Memory Metrics Over Time')
        self.fig.tight_layout()
        
        # 刷新画布
        self.canvas.draw()
    
    def _on_pick(self, event):
        """处理点击事件"""
        print(f"Pick event triggered: {event}")
        if event.mouseevent.button != 1:  # 只响应左键点击
            return
        
        # 获取被点击的线条
        line = event.artist
        print(f"Clicked artist: {line}, type: {type(line)}")
        
        # 检查是否是 peak 标记线
        if hasattr(line, 'peak_timestamp'):
            timestamp = line.peak_timestamp
            print(f"点击了峰值时间戳: {timestamp}")
            
            # 打开 memory_visualizer 窗口
            launch_visualizer_window(
                self.root,
                timestamp=str(timestamp),
                benchmark_name=self.config.benchmark_name,
                base_dir=self.config.base_dir
            )

def main():
    config = Config(underscores_to_dashes=True).parse_args()
    config.configure()
    
    # 创建主窗口
    root = tk.Tk()
    
    # 创建应用
    app = MetricsPlotterApp(root, config)
    
    # 启动主循环
    root.mainloop()

if __name__ == "__main__":
    main()