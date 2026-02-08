/*
Copyright (c) 2026, Chen Jie, Joungtao, Xuzheng Jiang
All rights reserved.
This source code is licensed under the BSD-2-Clause license found in the
LICENSE file in the root directory of this source tree.
*/

#include "trace_data.h"
#include "utils.h"

#include "boost/format.hpp"
#include "libunwind-ptrace.h"

namespace Memory::Profile {

bool TraceData::ThreadContext::init(pid_t tid) {
  // 创建一个地址空间对象 (unw_addr_space_t)，地址空间是 libunwind
  // 中的一个概念，用来管理栈帧信息的访问和处理，_UPT_accessors
  // 是一个用于访问远程进程内存的结构体
  addr_space = unw_create_addr_space(&_UPT_accessors, 0);
  if (!addr_space) {
    Log("[%d][error] Failed to create address space", tid);
    return false;
  }

  // 通过传入目标进程的 PID 来创建这个上下文
  context = _UPT_create(tid);
  // 一个上下文对象，用于存储进程的当前状态，包括寄存器和内存信息
  if (!context) {
    Log("[%d][error] Failed to create unwind context", tid);
    return false;
  }

  return true;
}

TraceData::ThreadContext::~ThreadContext() {
  if (context != nullptr) {
    _UPT_destroy(context);
    unw_destroy_addr_space(addr_space);
    context = nullptr;
    addr_space = 0;
  }
}

bool TraceData::ThreadContext::get_stack_trace(TraceInfo &trace_info,
                                               int max_depth) {
  if (context == nullptr && !init(trace_info.tid)) {
    return false;
  }
  // 使用上下文 (context) 和地址空间 (addr_space) 初始化游标
  unw_cursor_t cursor; // 用于遍历栈帧的结构体
  if (unw_init_remote(&cursor, addr_space, context) != 0) {
    Log("[%d][error] Failed to initialize unwind cursor", trace_info.tid);
    return false;
  }

  trace_info.stack_size = 0;
  do {
    unw_get_reg(&cursor, UNW_REG_IP,
                &trace_info.stack[trace_info.stack_size++]);
  } while (unw_step(&cursor) > 0 && trace_info.stack_size < STACK_MAX &&
           trace_info.stack_size < max_depth);
  return true;
}

bool TraceData::start(pid_t pid) {
  start_time = std::chrono::steady_clock::now();
  clear_dwfl();
  target_pid = pid;
  output = Zip::Stream::CreateFile(config.save_binary_path);
  processor = std::thread([this]() -> void {
    if (!init_dwfl()) {
      return;
    }
    need_update_dwfl = true;

    // 主处理循环
    while (!stopped || !queue.empty() || need_update_dwfl) {
      // 如果需要更新 DWARF 信息，立即更新
      if (need_update_dwfl) {
        update_dwfl();
      }
      // 等待队列中有数据
      if (queue.empty()) {
        std::this_thread::sleep_for(std::chrono::milliseconds(25));
        continue;
      }

      TraceInfo trace_info;
      if (queue.pop(trace_info)) {
        // 处理数据
        process(trace_info);
      }
    }
  });
  Log("TraceData::start()");
  return true;
}

bool TraceData::stop() {
  stopped = true;
  if (processor.joinable()) {
    processor.join();
  }
  clear_dwfl();
  return true;
}

bool TraceData::init_dwfl() {
  std::lock_guard<std::mutex> lock(dwfl_mutex);
  static const Dwfl_Callbacks callbacks = {.find_elf = dwfl_linux_proc_find_elf,
                                           .find_debuginfo =
                                               dwfl_standard_find_debuginfo};
  dwfl = dwfl_begin(&callbacks);
  if (dwfl == nullptr) {
    Log("[%d][error] failed to create DWFL object", target_pid);
    return false;
  }
  if (dwfl_linux_proc_attach(dwfl, target_pid, false) < 0) {
    Log("[%d][error] failed to attach to PID %d", target_pid, target_pid);
    dwfl_end(dwfl);
    dwfl = nullptr;
    return false;
  }
  return true;
}

void TraceData::clear_dwfl() {
  std::lock_guard<std::mutex> lock(dwfl_mutex);
  if (dwfl != nullptr) {
    dwfl_end(dwfl);
    dwfl = nullptr;
  }
}

void TraceData::update_dwfl() {
  std::lock_guard<std::mutex> lock(dwfl_mutex);
  // Log("updating dwfl");
  dwfl_report_begin(dwfl);
  if (dwfl_linux_proc_report(dwfl, target_pid) < 0) {
    Log("[%d][error] failed to report process mappings for PID %d", target_pid,
        target_pid);
    dwfl_report_end(dwfl, nullptr, nullptr);
    return;
  }
  if (dwfl_report_end(dwfl, nullptr, nullptr) < 0) {
    Log("[%d][error] failed to finalize report update", target_pid);
    return;
  }
  function_cache.clear();
  need_update_dwfl = false;
  // Log("finished updating dwfl");
}

static inline bool
set_name_index(const char *&name, uint32_t &index,
               std::unordered_map<std::string, uint32_t> &names) {
  if (name == nullptr) {
    name = "<nil>";
  }
  auto item = names.find(name);
  if (item != names.end()) {
    index = item->second;
    // Log("[exist] [%s] already exists in names map", name);
    return false;
  } else {
    index = names[name] = names.size();
    // Log("[found] added [%s] as #%d", name, index);
    return true;
  }
}

void TraceData::process(TraceInfo &trace_info) {
  FunctionInfo stack[STACK_MAX] = {0};

  // 遍历每个调用栈地址
  for (uint16_t i = 0; i < trace_info.stack_size; i++) {
    // 先在缓存中查找是否存在
    auto cache_item = function_cache.find(trace_info.stack[i]);
    if (cache_item != function_cache.end()) {
      stack[i] = cache_item->second;
      continue;
    }

    // 将 unw_word_t 类型的 IP 地址转换为 Dwarf_Addr 类型
    Dwarf_Addr addr = trace_info.stack[i];
    // 根据 IP 地址获取对应的 DWARF 模块
    Dwfl_Module *mod = dwfl_addrmodule(dwfl, addr);
    if (mod == nullptr) {
      if (false) {
        Log("[%d][error] failed to get DWARF module for address 0x%lx, op=%s",
            trace_info.tid, addr, GetOperation(trace_info.tag).name().data());
      }
      continue;
    }

    auto &frame = stack[i];

    // 获取当前地址的函数名
    const char *func_name = dwfl_module_addrname(mod, addr);
    if (set_name_index(func_name, frame.func_index, func_names)) {
      write_name_entry(FUNC_NAME_ENTRY, func_name);
      function_max_length =
          std::max(function_max_length, (int)strlen(func_name));
    }

    // 获取源代码行信息
    Dwfl_Line *line = dwfl_module_getsrc(mod, addr);

    int line_no = -1, col_no = -1;

    // 获取文件名、行号和列号
    const char *file_name =
        dwfl_lineinfo(line, nullptr, &line_no, &col_no, nullptr, nullptr);
    if (set_name_index(file_name, frame.file_index, file_names)) {
      write_name_entry(FILE_NAME_ENTRY, file_name);
      filename_max_length =
          std::max(filename_max_length, (int)strlen(file_name));
    }

    frame.line_no = line_no;
    frame.col_no = col_no;

    // 将函数信息写入缓存
    function_cache[trace_info.stack[i]] = frame;
  }
  // 序列化到输出流
  write_trace_info(trace_info, stack);
}

void TraceData::showTraceInfo(TraceInfo &trace_info) const {
  auto &[tag, tid, args, timestamp, stack_size, stack] = trace_info;
  auto op = GetOperation(tag);

  // 时间后三位不显示了，节约空间
  printf("[%d][%ld]", tid, timestamp / 1000);
  // 是Invoke类型
  if (IsInvoke(trace_info.tag)) {
    // 打印调用类型
    printf(" invoke [%7s]", op.name().data());
    // 打印参数
    if (op.argc() == 2) {
      printf(" arg = [%#lx, %#lx]", args[0], args[1]);
    } else if (op.argc() == 1) {
      printf(" arg = [%#lx]", args[0]);
    }

    if (stack_size) {
      printf(", stack_size = [%d]", stack_size);
    }
    printf(".\n");
    // 打印调用栈
    if (stack_size && config.isPrintStack) {
      for (int i = 0; i < stack_size; i++) {
        Log("  stack[%d] = [%#lx]", i, stack[i]);
      }
    }
  } // 是Result类型
  else {
    // 打印调用类型
    printf(" result [%7s]", op.name().data());
    // 打印参数
    if (op.has_return()) {
      printf(" ret = [%#lx]", args[0]);
    }
    printf(".\n");
  }
}

void TraceData::write_name_entry(uint8_t entry_type, const char *name) {
  uint16_t name_length = strlen(name);
  write(entry_type);
  write(name_length);
  output->write(name, name_length);
  if (config.isPrintSaveEntry) {
    const char *type = entry_type == FILE_NAME_ENTRY ? "filename" : "function";
    Log("[%s][%lld]: len=[%2d], name=[%s]", type, getTime() / 1000, name_length,
        name);
  }
}

void TraceData::write_trace_info(TraceInfo &trace_info,
                                 FunctionInfo (&stack)[STACK_MAX]) {
  write(trace_info.tag);        // 1B
  write(trace_info.tid);        // 4B
  write(trace_info.args[0]);    // 8B
  write(trace_info.args[1]);    // 8B
  write(trace_info.timestamp);  // 8B
  write(trace_info.stack_size); // 2B

  union {
    const FunctionInfo (*ptr)[STACK_MAX]{};
    const char *data;
  };
  ptr = &stack;
  output->write(data, sizeof(FunctionInfo) * trace_info.stack_size);
  if (config.isPrintSaveEntry) {
    Log("[traceinfo][%lld]: tag=[%d(%s %s)] tid=[%d] args=[%#lx, %#lx], "
        "stacksize=[%d]",
        trace_info.timestamp / 1000, trace_info.tag,
        IsInvoke(trace_info.tag) ? "invoke" : "result",
        GetOperation(trace_info.tag).name().data(), trace_info.tid,
        trace_info.args[0], trace_info.args[1], trace_info.stack_size);
  }
}

bool TraceData::add(uint8_t tag, pid_t tid, uintptr_t arg1, uintptr_t arg2,
                    ThreadContext &context, int *stack_size = nullptr) {
  TraceInfo trace_info = {tag, tid, {arg1, arg2}, getTime(), 0, {0}};
  // 如果是调用操作(Invoke)，采集调用栈
  if (IsInvoke(tag) && config.isGetStackTrace &&
      !context.get_stack_trace(trace_info, config.maxStackTraceDepth)) {
    return false;
  }
  // 打印当前信息到日志
  if (config.isPrintInvokeResultLog) {
    showTraceInfo(trace_info);
  }
  // 传出栈大小
  if (stack_size) {
    *stack_size = trace_info.stack_size;
  }
  // 将追踪信息推入无锁队列
  if (!queue.push(std::move(trace_info))) {
    // 添加失败
    Log("[%d][error] cannot add trace data: tag(%u) args = [%#lx, %#lx]", tid,
        tag, arg1, arg2);
    return false;
  }
  return true;
}

void TraceData::on_library_loaded(pid_t tid) {
  need_update_dwfl = true;
}

bool StatInfo::save(const std::string &filename) const {
  std::ofstream file(filename);
  if (!file.is_open())
    return false;
  output(file, false);
  return true;
}

void StatInfo::print() const { output(std::cout, true); }

void StatInfo::output(std::ostream &os, bool console) const {
  // 对齐宽度
  const size_t align = 25;
  const size_t align_t = std::to_string(time_end).length();
  const size_t align_op = std::to_string(total_count).length();

  // 如果输出到控制台则输出分隔线
  auto printSection = [console, &os](const std::string &str) -> void {
    if (console) {
      os << str << std::endl;
    }
  };

  // 打印字符串
  auto printHead = [align, &os](const std::string &str) -> void {
    std::string fmt_str = "%-" + std::to_string(align) + "s: ";
    os << boost::format(fmt_str) % str;
  };
  // 打印变量或常量
  auto printVar = [printHead, &os](const std::string &name,
                                   const auto &var) -> void {
    printHead(name);
    os << var << std::endl;
  };

  // 打印向右对齐的变量
  auto printVarR = [printHead, &os](const std::string &name, const auto &value,
                                    const size_t ralign = 0) -> void {
    printHead(name);
    std::string fmt_str = "%" + std::to_string(ralign) + "s";
    os << boost::format(fmt_str) % value << std::endl;
  };

  // 打印容器内容
  auto printCon = [printHead, &os](const std::string &name,
                                   const auto &container) -> void {
    printHead(name);
    for (const auto &item : container) {
      os << item << " ";
    }
    os << std::endl;
  };
  // 打印 Pair 容器内容
  auto printPair = [printHead, &os](const std::string &name,
                                    const auto &pair) -> void {
    printHead(name);
    for (const auto &[first, second] : pair) {
      os << first << ">" << second << " ";
    }
    os << std::endl;
  };
  // 打印 map 容器内容
  auto printMap = [printHead, &os](const auto &map) -> void {
    for (const auto &[key, value] : map) {
      printHead(key);
      os << value << std::endl;
    }
  };
  // 打印数组内容（指定范围）
  auto printStrArr = [printHead, &os](const std::string &name,
                                      const auto &array, size_t start,
                                      size_t end) -> void {
    printHead(name);
    for (size_t i = start; i <= end; ++i) {
      os << (array[i] ? array[i] : "") << " ";
    }
    os << std::endl;
  };

  // 打印操作类型计数
  auto printOpCalledCount = [&]() -> void {
    for (int i = 0; i < Operation::op_type_count; ++i) {
      if (!op_invoke_count[i] && console)
        continue;

      printHead(std::string("num_of_") + std::string(Operation::op_meta[i].name));

      if (console) {
        // 使用单个 format 处理数字对齐
        std::string fmt = "%" + std::to_string(align_op) + "d";
        os << boost::format(fmt) % op_invoke_count[i];

        if (Operation::op_meta[i].has_return) {
          os << " / " << (boost::format(fmt) % op_result_count[i]);
        }
      } else {
        os << op_invoke_count[i] << ' ' << op_result_count[i];
      }
      os << '\n';
    }

    printHead("total_invoke/result");
    if (console) {
      std::string fmt = "%" + std::to_string(align_op) + "d";
      os << (boost::format(fmt) % invoke_count) << " / "
         << (boost::format(fmt) % result_count) << '\n';
    } else {
      os << invoke_count << ' ' << result_count << '\n';
    }
  };

  // 打印分隔线
  printSection("================ Statistic Information ================");

  // 打印统计信息
  if (!extrakeys.empty()) {
    printSection("-------- Extra Keys");
    printVar("num_of_extrakeys", extrakeys.size());
    printMap(extrakeys);
  }

  printSection("-------- Basic Information");
  printVar("argc", argc);
  printStrArr("argv[]", argv, 0, argc - 1);
  printStrArr("mprofiler_args", argv, 1, argc - 1 - commands.size() + 1);
  printStrArr("executed_commands", commands, 0, commands.size() - 1);
  printVar("target", target);
  printVar("target_full_path", target_full_path);
  printVar("working_directory", working_dir);
  printVar("save_path", save_path);

  printSection("-------- Trace Information");
  printVar("total_traceinfo_count", total_count);
  printVar("max_stack_size", max_stack_size);
  printVar("filename_max_length", filename_max_length);
  printVar("function_max_length", function_max_length);

  printSection("-------- Process Information");
  printVar("main_pid", main_pid);
  printVar("child_tid_num", child_tid_list.size());
  if (!child_tid_list.empty()) {
    printCon("child_tid_list", child_tid_list);
    printPair("tid_relations", tid_relations);
  }

  // 打印各项操作的时间
  printSection("-------- Time Cost");
  printVar("timestamp_start", timestamp_start);
  printVar("timestamp_end", timestamp_end);
  printVarR("time_end", time_end, align_t);

  // 打印操作类型计数
  printSection("-------- Operation Called");
  printOpCalledCount();

  printSection("================ ===================== ================");
}
} // namespace Memory::Profile