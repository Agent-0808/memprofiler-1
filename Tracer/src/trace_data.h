/*
Copyright (c) 2026, Chen Jie, Joungtao, Xuzheng Jiang
All rights reserved.
This source code is licensed under the BSD-2-Clause license found in the
LICENSE file in the root directory of this source tree.
*/

#pragma once

#include <chrono>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <mutex>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

#include "boost/lockfree/queue.hpp"
#include "elfutils/libdwfl.h"
#include "libunwind.h"
#include "zstd.h"

#include "zip_stream.h"

namespace Memory::Profile {

// 操作枚举类型
enum class op_type : uint8_t {
  UNKNOWN = 0,
  BRK,
  SBRK,
  MMAP,
  MUNMAP,
  CLONE,
  CLONE3,
  FORK,
  VFORK,
  EXECVE,
  FREE,
  MALLOC,
  CALLOC,
  REALLOC,
  VALLOC,
  POSIX_MEMALIGN,
  ALIGNED_ALLOC,
  NEW,
  NEW_ARRAY,
  DELETE_LEGACY,
  DELETE,
  DELETE_ARRAY,
  _TYPE_COUNT,
};

// 封装的操作类型类
class Operation {
  op_type type_;

public:
  // 操作的元数据
  struct OperationMeta {
    std::string_view name; // 操作名称
    uint8_t argc;          // 参数个数
    bool has_return;       // 是否有返回值
  };

  // 操作类型数量
  static constexpr size_t op_type_count =
      static_cast<size_t>(op_type::_TYPE_COUNT);
  // 操作元数据
  static constexpr OperationMeta op_meta[op_type_count] = {
      {"unknown", 2, true},       {"brk", 1, true},
      {"sbrk", 1, true},          {"mmap", 2, true},
      {"munmap", 2, true},        {"clone", 1, true},
      {"clone3", 1, true},        {"fork", 0, true},
      {"vfork", 0, true},         {"execve", 1, true},
      {"free", 1, false},         {"malloc", 1, true},
      {"calloc", 2, true},        {"realloc", 2, true},
      {"valloc", 1, true},        {"posix_memalign", 2, true},
      {"aligned_alloc", 2, true}, {"new", 1, true},
      {"new_arr", 1, true},       {"delete_legacy", 1, false},
      {"delete", 2, false},       {"delete_arr", 1, false},
  };

  // constexpr构造函数
  constexpr Operation(op_type type) noexcept : type_(type) {}
  // 转换到原始枚举
  constexpr operator op_type() const noexcept { return type_; }
  // 获取元数据
  const OperationMeta &meta() const {
    return op_meta[static_cast<size_t>(type_)];
  }

  // 读取方法
  op_type type() const { return type_; }
  uint8_t index() const { return static_cast<uint8_t>(type_); }
  const std::string_view &name() const { return meta().name; }
  uint8_t argc() const { return meta().argc; }
  bool has_return() const { return meta().has_return; }

  // Invoke操作，最低位为0
  constexpr uint8_t invoke() const { return static_cast<uint8_t>(type_) << 1; }
  // Result操作，最低位为1
  constexpr uint8_t result() const {
    return (static_cast<uint8_t>(type_) << 1) | 1;
  }
};

// 判断操作是否为Invoke操作
inline constexpr uint8_t IsInvoke(uint8_t tag) { return (tag & 1) == 0; }
// 从标记中提取原始操作类型
inline constexpr Operation GetOperation(uint8_t tag) {
  return Operation(static_cast<op_type>(tag >> 1));
}

using TimePoint = std::chrono::steady_clock::time_point; // 时间点
using timens_t = int64_t; // 时间戳类型（单位纳秒）

// 追踪数据核心类，负责内存操作信息的收集和处理
class TraceData {
  // 最大调用栈深度
  static inline constexpr uint16_t STACK_MAX = 100;

  // 单次内存操作的追踪信息（对应原TraceDataEntry）
  struct TraceInfo {
    uint8_t tag;                // 操作类型 + 调用/返回
    pid_t tid;                  // thread id
    uintptr_t args[2];          // 参数或返回值
    timens_t timestamp;         // 操作对应的时间戳
    uint16_t stack_size;        // 调用栈元素个数
    uintptr_t stack[STACK_MAX]; // 调用栈
  };

  static inline constexpr size_t QUEUE_INIT_SIZE = 10000; // 无锁队列初始容量
  boost::lockfree::queue<TraceInfo> queue{QUEUE_INIT_SIZE}; // 无锁队列容器

  bool stopped = false;  // 停止标志位
  pid_t target_pid = 0;  // 目标进程PID
  std::thread processor; // 后台处理线程
  TimePoint start_time;  // 开始时间点

  // 特殊标记：文件名条目（使用 UNKNOWN 的 Invoke 标记）
  static inline constexpr uint8_t FILE_NAME_ENTRY =
      Operation(op_type::UNKNOWN).invoke();
  // 特殊标记：函数名条目（使用 UNKNOWN 的 Result 标记）
  static inline constexpr uint8_t FUNC_NAME_ENTRY =
      Operation(op_type::UNKNOWN).result();

  // 函数信息结构，调用栈的一帧（对应原 StackFrame ）
  struct FunctionInfo {
    uint32_t file_index; // 文件名索引
    uint32_t func_index; // 函数名索引
    int32_t line_no;     // 源代码行号
    int32_t col_no;      // 源代码列号
  };

  // 索引到文件名/函数名的映射（对应原 TraceMap ）
  std::unordered_map<std::string, uint32_t> file_names; // 文件名到索引的映射
  std::unordered_map<std::string, uint32_t> func_names; // 函数名到索引的映射
  std::map<uintptr_t, FunctionInfo> function_cache; // 地址到函数信息的缓存

  std::shared_ptr<std::ostream> output; // 输出流（压缩文件）

  bool need_update_dwfl = false; // DWARF信息是否需要更新
  Dwfl *dwfl = nullptr;          // DWARF调试信息句柄
  std::mutex dwfl_mutex;         // 互斥锁保护 dwfl

  // dwfl相关操作
  bool init_dwfl();
  void clear_dwfl();
  void update_dwfl();

  // 处理单个追踪信息
  void process(TraceInfo &trace_info);
  // 打印追踪信息
  void showTraceInfo(TraceInfo &trace_info) const;

  // 向输出流写入任意类型数据
  template <typename T> void write(const T &value) {
    union {
      const T *ptr{};
      const char *data;
    };
    ptr = &value;
    output->write(data, sizeof(value));
  }

  // 写入文件名/函数名条目
  void write_name_entry(uint8_t entry_type, const char *name);
  // 写入完整的追踪信息
  void write_trace_info(TraceInfo &trace_info,
                        FunctionInfo (&stack)[STACK_MAX]);

public:
  TraceData() = default;
  ~TraceData() { stop(); }

  bool start(pid_t pid);
  bool stop();

  // 配置项
  struct TraceConfig {
    bool isGetStackTrace;
    bool isGetTraceData;
    bool isSaveTraceData;
    int maxStackTraceDepth;
    bool isPrintInvokeResultLog;
    bool isPrintStack;
    bool isPrintSaveEntry;

    std::string save_binary_path;

    // 调试时是否打印跟踪数据
    bool isPrintTraceData = true;
    // 调试时是否打印索引表，否则打印带名称的调用栈
    bool isCallStackInIndex = false;

  } config;

  int filename_max_length = -1;
  int function_max_length = -1;

  // 获取当前时间戳
  timens_t getTime() const {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(
               std::chrono::steady_clock::now() - start_time)
        .count();
  }

  // 线程上下文管理类（用于获取调用栈）
  class ThreadContext {
    void *context = nullptr;         // libunwind 上下文
    unw_addr_space_t addr_space = 0; // 地址空间对象

    bool init(pid_t tid); // 初始化上下文

  public:
    ThreadContext() = default;
    ~ThreadContext();

    // 获取当前线程的调用栈
    bool get_stack_trace(TraceInfo &trace_info, int max_depth = STACK_MAX);
  };

  // 添加追踪数据到队列
  bool add(uint8_t tag, pid_t tid, uintptr_t arg1, uintptr_t arg2,
           ThreadContext &context, int *stack_size);
  // 动态库加载时的回调
  void on_library_loaded(pid_t tid);
};

// 统计信息
struct StatInfo {
  std::vector<std::pair<std::string, std::string>> extrakeys;

  int argc;
  char **argv;
  std::vector<char *> commands;
  std::string target;
  std::string target_full_path;
  std::string working_dir;
  std::string save_path;

  int total_count;
  int max_stack_size = -1;
  int filename_max_length = -1;
  int function_max_length = -1;

  pid_t main_pid;
  std::vector<pid_t> child_tid_list;
  std::vector<std::pair<pid_t, pid_t>> tid_relations;

  std::string timestamp_start;
  std::string timestamp_end;
  timens_t time_end;

  int op_invoke_count[Operation::op_type_count];
  int op_result_count[Operation::op_type_count];
  int invoke_count;
  int result_count;

  bool save(const std::string &filename) const;
  void print() const;

private:
  void output(std::ostream &os, bool console) const;
};
} // namespace Memory::Profile
