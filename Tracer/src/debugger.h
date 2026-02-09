/*
Copyright (c) 2026, Chen Jie, Joungtao, Xuzheng Jiang
All rights reserved.
This source code is licensed under the BSD-2-Clause license found in the
LICENSE file in the root directory of this source tree.
*/

#pragma once

#include <cstdio>   // 包含 C 标准输入输出函数，如 snprintf
#include <cstdlib>  // 包含 atoi 函数
#include <cstring>  // 包含字符串操作函数，如 strlen, strcmp
#include <dirent.h> // 包含目录操作函数
#include <fcntl.h>
#include <filesystem>
#include <map>
#include <mutex>
#include <shared_mutex>
#include <thread>
#include <vector>

#include "sys/ptrace.h"  // 提供 ptrace 系统调用的定义
#include "sys/syscall.h" // 提供系统调用的相关定义
#include "sys/user.h" // 定义了 struct user_regs_struct，用于保存寄存器的值
#include "sys/wait.h" // 提供 wait 和相关宏的定义

#include "target_loader.h"
#include "utils.h"

namespace Memory::Profile {

template <class T, class S> class Debugger {
  static constexpr size_t INVALID_INDEX = UINT64_MAX;

  bool has_loading_libraries = false;
  std::atomic_flag doing_setup = false;
  std::mutex libraries_mutex;
  std::set<std::string> loading_libraries;
  std::set<std::string> loaded_libraries;

  mutable std::shared_mutex functions_mutex;
  mutable std::shared_mutex breakpoints_mutex;
  std::map<uintptr_t, size_t> functions;
  std::map<uintptr_t, uint64_t> breakpoints;
  uintptr_t breakpoint_min = 0;
  uintptr_t breakpoint_max = 0;

  static inline bool is_breakpoint(uintptr_t rip, uintptr_t addr) {
    return rip - 1 == addr;
  }

  std::pair<uintptr_t, size_t> get_function(uintptr_t rip) const {
    std::shared_lock<std::shared_mutex> lock(functions_mutex);
    auto item = functions.find(rip - 1);
    if (item == functions.end()) {
      return {0, 0};
    }
    return {item->first, item->second};
  }

  uintptr_t get_breakpoint(uintptr_t rip) const {
    std::shared_lock<std::shared_mutex> lock(breakpoints_mutex);
    return breakpoints.find(rip - 1) != breakpoints.end() ? (rip - 1) : 0;
  }

  // 在目标线程的内存地址addr处插入断点，并保存原始数据
  bool add_breakpoint(pid_t tid, uintptr_t addr) {
    // 使用PTRACE_PEEKTEXT从目标进程的内存中读取地址addr处的原始数据，并保存到orig中
    breakpoints[addr] = ptrace(PTRACE_PEEKTEXT, tid, addr, 0);
    if (breakpoint_min == 0 && breakpoint_min > addr) {
      breakpoint_min = addr;
    }
    if (breakpoint_max == 0 && breakpoint_max < addr) {
      breakpoint_max = addr;
    }
    return enable_breakpoint(tid, addr);
  }

  // 通过设置断点处的字节来启用断点
  bool enable_breakpoint(pid_t tid, uintptr_t addr) const {
    // 使用PTRACE_POKETEXT将地址addr处的内容替换为断点指令0xCC(int
    // 3)，并保留原始数据的其他部分
    auto orig = breakpoints.at(addr);
    ptrace(PTRACE_POKETEXT, tid, addr, (orig & ~0xFF) | 0xCC);
    uint64_t result = ptrace(PTRACE_PEEKDATA, tid, addr, nullptr);
    // TODO: 需要检查result是否正常
    return true;
  }

  // 通过将断点处的字节替换回原始字节来禁用断点
  bool disable_breakpoint(pid_t tid, uintptr_t addr) const {
    // 从目标进程的内存中读取地址addr处的数据
    auto data = ptrace(PTRACE_PEEKTEXT, tid, addr, 0);
    // 确保读取到的数据的最低字节是断点指令0xCC，以验证断点是否仍然存在
    if ((data & 0xFF) != 0xCC) {
      Log("[%d][warning] breakpoint already disabled: 0x%llx for 0x%llx", tid,
          data, addr);
      return true;
    }
    // 将断点位置的内容恢复为原始数据
    auto orig = breakpoints.at(addr);
    uint64_t result =
        ptrace(PTRACE_POKETEXT, tid, addr, (data & ~0xFF) | (orig & 0xFF));
    // TODO: 需要检查result是否正常
    return true;
  }

  // 恢复进程在断点处的执行，并恢复断点
  bool resume_breakpoint(pid_t tid, uintptr_t addr, user_regs_struct &regs) {
    // 将RIP寄存器的值设置回断点的地址，这是因为在断点处，RIP寄存器会指向断点指令的下一个地址
    regs.rip = addr;
    // 使用PTRACE_SETREGS将寄存器的值（特别是RIP）设置回断点的地址
    ptrace(PTRACE_SETREGS, tid, 0, &regs);
    // 禁用断点，通过将断点位置的内容恢复为原始数据来实现
    disable_breakpoint(tid, addr);

    // 多执行一步，避免恢复执行后又立即被暂停，导致断点重复处理
    for (int i = 0; i <= 1; i++) {
      // 使用PTRACE_SINGLESTEP指令让目标进程执行单步操作，这将执行断点位置的原始指令
      if (ptrace(PTRACE_SINGLESTEP, tid, 0, 0) < 0) {
        perror("resume");
        return false;
      }

      // 等待目标进程的状态更新
      int status = 0;
      if (waitpid(tid, &status, __WALL) < 0) {
        perror("wait resume single step");
        return false;
      }

      // 如果进程因调用 exit 系统调用而正常退出，返回 0 表示成功
      if (WIFEXITED(status)) {
        return true;
      }
    }

    // 重新启用断点，恢复断点指令
    return enable_breakpoint(tid, addr);
  }

  // 多线程场景下，恢复指定线程在断点处的执行
  bool resume_thread_breakpoint(pid_t tid, uintptr_t addr,
                                user_regs_struct &regs) {
    std::unique_lock<std::shared_mutex> lock(breakpoints_mutex);
    if (!pause_others(tid)) {
      return false;
    }
    if (!resume_breakpoint(tid, addr, regs)) {
      return false;
    }
    return continue_others(tid);
  }

protected:
  using ThreadSafeArena = S;

private:
  // 断点信息
  struct ResultBreakpoint {
    uintptr_t breakpoint;
    size_t function_index;
  };

  // 线程数据
  struct ThreadData {
    bool paused = false;
    ThreadSafeArena arena;
    std::thread tracer;
    std::vector<bool> syscalls;
    std::vector<ResultBreakpoint> stack;
  };

  std::shared_mutex threads_mutex;
  std::atomic<size_t> active_threads;
  std::map<pid_t, ThreadData> threads;

  std::pair<bool, ThreadData &> get_thread(pid_t tid) {
    static ThreadData empty;
    std::shared_lock<std::shared_mutex> lock(threads_mutex);
    auto item = threads.find(tid);
    return {item != threads.end(), item->second};
  }

  ThreadData &add_thread(pid_t tid) {
    std::unique_lock<std::shared_mutex> lock(threads_mutex);
    auto item = threads.find(tid);
    if (item != threads.end()) {
      Log("[%d] thread already traced!", tid);
      return item->second;
    }

    auto &thread = threads[tid];
    thread.syscalls.resize(get_syscall_callbacks().size(), false);
    return thread;
  }

  void join_threads() {
    std::shared_lock<std::shared_mutex> lock(threads_mutex);
    for (auto &[tid, thread] : threads) {
      if (tid != target_pid) {
        thread.tracer.join();
      }
    }
  }

  bool pause_others(pid_t tid) {
    int status;
    siginfo_t siginfo;
    std::shared_lock<std::shared_mutex> lock(threads_mutex);
    for (auto &[oid, t] : threads) {
      t.paused = false;
      // 检查线程是否已停止
      if (oid == tid || ptrace(PTRACE_GETSIGINFO, oid, 0, &siginfo) < 0) {
        continue;
      }

      // 发送 SIGSTOP 信号暂停线程
      if (kill(oid, SIGSTOP) < 0) {
        perror("pause others");
        return false;
      }

      // 等待线程暂停
      if (waitpid(oid, &status, __WALL) < 0) {
        perror("waitpid");
        return false;
      } else if (!WIFSTOPPED(status)) {
        Log("[%d] thread %d not paused", tid, oid);
        return false;
      }
      t.paused = true;
    }
    return true;
  }

  bool continue_others(pid_t tid) {
    int status;
    siginfo_t siginfo;
    std::shared_lock<std::shared_mutex> lock(threads_mutex);
    for (auto &[oid, t] : threads) {
      if (!t.paused) {
        continue;
      }

      // 继续线程执行
      if (ptrace(PTRACE_SYSCALL, oid, 0, 0) < 0) {
        perror("continue others");
        return false;
      }
      t.paused = false;
    }
    return true;
  }

  void reset_breakpoint(pid_t tid, uintptr_t range_min, uintptr_t range_max) {
    std::unique_lock<std::shared_mutex> lock(breakpoints_mutex);
    for (auto [addr, orig] : breakpoints) {
      if (addr < range_min || addr > range_max) {
        continue;
      }
      auto curr = ptrace(PTRACE_PEEKTEXT, tid, addr, 0);
      if ((curr & 0xFF) != 0xCC) {
        add_breakpoint(tid, addr);
      }
    }
  }

  bool setup_breakpoint(pid_t tid) {
    bool result = true;
    if (!doing_setup.test_and_set()) {
      return result;
    }
    auto process_maps_entry = [this, tid, &result](const char *path,
                                                   uintptr_t base) -> bool {
      auto load_libary = [this, tid, &result, path,
                          base](const char *name, uintptr_t offset) -> bool {
        if (offset == 0) {
          return false;
        }
        for (size_t function_index = 0; auto &c : get_function_callbacks()) {
          auto breakpoint = base + offset;
          if (c.name == name &&
              breakpoints.find(breakpoint) == breakpoints.end()) {
            functions[breakpoint] = function_index;
            Log("[function] name: [%s], index: [%llu], file: [%s], base: [%p], "
                "offset: "
                "[%p], invoke: [%p], result: [%p]",
                name, function_index, path, base, offset, c.invoke, c.result);
            if (!add_breakpoint(tid, breakpoint)) {
              result = false;
            }
          }
          function_index++;
        }
        return false;
      };
      {
        std::lock_guard<std::mutex> lock(libraries_mutex);
        loaded_libraries.insert(path);
        loading_libraries.erase(path);
        has_loading_libraries = !loading_libraries.empty();
      }
      static_cast<SubClass *>(this)->on_library_loaded(tid);
      // 如果对应的项存在（即属于文件）才进行加载
      if (!std::filesystem::exists(path)) {
        // Log("[File] Skip non-file entry: %s", path);
        return false;
      }
      int fd = open(path, O_RDONLY);
      if (fd < 0) {
        perror("open file for ELF check");
        return false;
      }
      // ELF魔数检查
      char magic[4];
      bool is_elf = (read(fd, magic, sizeof(magic)) == sizeof(magic)) &&
                    (memcmp(magic,
                            "\x7f"
                            "ELF",
                            sizeof(magic)) == 0);
      if (!is_elf) {
        close(fd);
        // Log("[File] Skip non-ELF library: %s", path);
        return false;
      }
      close(fd);
      Log("[File] Load library: [%s], base: [%p]", path, base);
      std::unique_lock<std::shared_mutex> functions_lock(functions_mutex);
      std::unique_lock<std::shared_mutex> breakpoints_lock(breakpoints_mutex);
      if (!get_function_offset(path, load_libary)) {
        result = false;
      }
      return false;
    };
    if (!get_maps_addr(target_pid, loaded_libraries, process_maps_entry)) {
      result = false;
    }
    doing_setup.clear();
    return result;
  }

  bool trace_syscall(pid_t tid) {
    auto [ok, thread] = get_thread(tid);
    if (!ok) {
      Log("[%d] trace syscall thread not exists", tid);
      return false;
    }

    user_regs_struct regs;
    // 读取进程的寄存器值到一个结构体regs中
    ptrace(PTRACE_GETREGS, tid, 0, &regs);

    for (size_t i = 0; auto &c : get_syscall_callbacks()) {
      if (c.syscall == regs.orig_rax) {
        if (thread.syscalls[i]) {
          if (c.result != nullptr) {
            c.result(static_cast<SubClass *>(this), tid, regs, thread.arena);
          }
          thread.syscalls[i] = false;
        } else {
          if (c.invoke != nullptr) {
            c.invoke(static_cast<SubClass *>(this), tid, regs, thread.arena);
          }
          thread.syscalls[i] = true;
        }
      }
      i++;
    }
    return true;
  }

  bool trace_breakpoint(pid_t tid) {
    auto [ok, thread] = get_thread(tid);
    if (!ok) {
      Log("[%d] trace breakpoint thread not exists", tid);
      return false;
    }

    user_regs_struct regs;
    // 读取进程的寄存器值到一个结构体regs中
    ptrace(PTRACE_GETREGS, tid, 0, &regs);

    auto &callbacks = get_function_callbacks();

    auto process = [this, tid, &regs, &thread](uintptr_t addr,
                                               Callback callback,
                                               size_t index) -> bool {
      if (callback != nullptr) {
        callback(static_cast<SubClass *>(this), tid, regs, thread.arena);
      }

      if (index != INVALID_INDEX) {
        uintptr_t result_addr = ptrace(PTRACE_PEEKDATA, tid, regs.rsp, nullptr);
        thread.stack.emplace_back(result_addr, index);
        std::unique_lock<std::shared_mutex> lock(breakpoints_mutex);
        if (breakpoints.find(result_addr) == breakpoints.end()) {
          if (!add_breakpoint(tid, result_addr)) {
            return false;
          }
        }
      }

      return resume_thread_breakpoint(tid, addr, regs);
    };

    if (auto [addr, index] = get_function(regs.rip); addr != 0) {
      auto &c = callbacks[index];
      return process(addr, c.invoke,
                     c.result != nullptr ? index : INVALID_INDEX);
    }

    // result
    if (!thread.stack.empty()) {
      ResultBreakpoint &currentBreakpoint = thread.stack.back();
      if (is_breakpoint(regs.rip, currentBreakpoint.breakpoint)) {
        const FunctionCallback &callback =
            callbacks[currentBreakpoint.function_index];
        thread.stack.pop_back();
        return process(currentBreakpoint.breakpoint, callback.result,
                       INVALID_INDEX);
      }
    }

    if (auto breakpoint = get_breakpoint(regs.rip); breakpoint > 0) {
      return process(breakpoint, nullptr, INVALID_INDEX);
    }

    return true;
  }

  bool trace_new_thread(pid_t tid) {
    // regs.rdi is clone_flags
    int status;
    union {
      pid_t new_child;
      uint64_t _;
    };
    ptrace(PTRACE_GETEVENTMSG, tid, nullptr, &new_child);
    if (new_child >= 0) {
      Log("[%d] new thread %d", tid, new_child);
      static_cast<SubClass *>(this)->add_new_tid(tid, new_child);
      waitpid(new_child, &status, __WALL);
      ptrace(PTRACE_DETACH, new_child, nullptr, SIGSTOP);
      auto &thread = add_thread(new_child);
      active_threads++;
      thread.tracer = std::thread([this, new_child]() -> void {
        int status;
        ptrace(PTRACE_ATTACH, new_child);
        waitpid(new_child, &status, 0);
        trace_thread(new_child);
        active_threads--;
      });
    }
    return true;
  }

  bool trace_thread(pid_t tid) {
    Log("[%d] start trace thread", tid);

    ptrace(PTRACE_SETOPTIONS, tid, nullptr,
           PTRACE_O_TRACESYSGOOD |   // get syscall info
               PTRACE_O_TRACECLONE | // trace cloned processes
               PTRACE_O_TRACEFORK |  // trace forked processes
               PTRACE_O_TRACEVFORK | // trace vforked processes
               PTRACE_O_TRACEEXEC |  // disable legacy sigtrap on execve
               PTRACE_O_EXITKILL);   // send SIGKILL to target if tracer exits

    ptrace(PTRACE_SYSCALL, tid, 0, 0);

    while (true) {
      int status;
      waitpid(tid, &status, __WALL);

      if (status >> 8 == (SIGTRAP | (PTRACE_EVENT_CLONE << 8)) ||
          status >> 8 == (SIGTRAP | (PTRACE_EVENT_FORK << 8)) ||
          status >> 8 == (SIGTRAP | (PTRACE_EVENT_VFORK << 8))) {
        if (!trace_new_thread(tid)) {
          return false;
        }
      }

      if (WIFEXITED(status)) {
        break;
      } else if (!WIFSTOPPED(status)) {
      } else if (WSTOPSIG(status) == (SIGTRAP | 0x80)) {
        if (has_loading_libraries && !setup_breakpoint(tid)) {
          return false;
        } else if (!trace_syscall(tid)) {
          return false;
        }
      } else if (WSTOPSIG(status) == SIGTRAP) {
        if (!trace_breakpoint(tid)) {
          return false;
        }
      } else {
        // signal delivery stop
        ptrace(PTRACE_SYSCALL, tid, 0, WSTOPSIG(status));
        continue;
      }
      ptrace(PTRACE_SYSCALL, tid, 0, 0);
    }
    return true;
  }
  static inline void on_mmap_invoke(T *self, pid_t tid,
                                    const user_regs_struct &regs,
                                    ThreadSafeArena &) {
    constexpr std::string_view so_ext = ".so";
    auto file_path = get_file_path(self->target_pid, regs.r8);
    auto so_pos = file_path.find(so_ext);
    if (so_pos == std::string::npos) {
      return;
    }
    auto so_tail = so_pos + so_ext.size();
    if (so_tail == file_path.size() || file_path[so_tail] == '.') {
      std::lock_guard<std::mutex> lock(self->libraries_mutex);
      self->loading_libraries.insert(file_path);
      self->has_loading_libraries = true;
    }
  }

  static inline void on_mmap_result(T *self, pid_t tid,
                                    const user_regs_struct &regs,
                                    ThreadSafeArena &) {
    if (regs.rax < self->breakpoint_max &&
        regs.rax + regs.rsi > self->breakpoint_min) {
      self->Debugger::reset_breakpoint(tid, regs.rax, regs.rax + regs.rsi);
      self->on_library_loaded(tid);
    }
  }

protected:
  pid_t target_pid;
  std::string target_path;
  bool attach_all_threads(pid_t pid) {
    DIR *dir;
    struct dirent *entry;
    char task_path[256];
    snprintf(task_path, sizeof(task_path), "/proc/%d/task", pid);

    dir = opendir(task_path);
    if (dir == nullptr) {
      perror("opendir");
      return false;
    }

    while ((entry = readdir(dir)) != nullptr) {
      if (entry->d_name[0] == '.') {
        continue; // 跳过 "." 和 ".."
      }

      int tid = atoi(entry->d_name);
      if (tid == 0) {
        continue;
      }

      // 如果 tid 等于 pid，则说明这是主线程，已经附加过，跳过
      if (tid == pid) {
        continue;
      }
      int status;
      // printf("Attaching to thread: %d\n", tid);
      waitpid(tid, &status, __WALL);
      ptrace(PTRACE_DETACH, tid, nullptr, SIGSTOP);
      ptrace(PTRACE_ATTACH, tid);
      waitpid(tid, &status, 0);
      if (!trace_thread(tid)) {
        return false;
      }
    }

    closedir(dir);
    return true;
  }
  bool run() {
    Log("debugger for pid(%d) start", target_pid);

    int status;
    /* 等待子进程停止执行第一个指令 */
    waitpid(target_pid, &status, 0);

    target_path = get_target_path(target_pid);
    if (target_path.empty()) {
      return false;
    }
    Log("path: %s", target_path.c_str());

    // TODO: 需要检查已经开启的所有线程，全都attach
    add_thread(target_pid);
    if (!trace_thread(target_pid)) {
      return false;
    }

    // wait for remaining threads
    constexpr auto interval = std::chrono::milliseconds(200);
    while (active_threads != 0) {
      std::this_thread::sleep_for(interval);
    }

    join_threads();

    Log("debugger end");
    return true;
  }

  using SubClass = T;
  using Callback = void (*)(SubClass *, pid_t, const user_regs_struct &,
                            ThreadSafeArena &);

  struct SyscallCallback {
    uint64_t syscall;
    Callback invoke;
    Callback result;
    SyscallCallback(uint64_t syscall_, Callback invoke_, Callback result_)
        : syscall(syscall_), invoke(invoke_), result(result_) {}
  };

  static inline std::vector<SyscallCallback> &get_syscall_callbacks() {
    static std::vector<SyscallCallback> syscall_callbacks;
    return syscall_callbacks;
  }

  struct SyscallRegister {
    SyscallRegister(uint64_t syscall, Callback invoke, Callback result) {
      get_syscall_callbacks().emplace_back(syscall, invoke, result);
    }
  };

  struct FunctionCallback {
    std::string name;
    Callback invoke;
    Callback result;
    FunctionCallback(const std::string_view &name_, Callback invoke_,
                     Callback result_)
        : name(name_), invoke(invoke_), result(result_) {}
  };

  static inline std::vector<FunctionCallback> &get_function_callbacks() {
    static std::vector<FunctionCallback> function_callbacks;
    return function_callbacks;
  }

  struct FunctionRegister {
    FunctionRegister(const std::string_view &name, Callback invoke,
                     Callback result) {
      get_function_callbacks().emplace_back(name, invoke, result);
    }
  };
  static inline auto on_mmap_register =
      SyscallRegister(SYS_mmap, on_mmap_invoke, on_mmap_result);
};

#define DEBUG_SYSCALL_1(NAME, INVOKE)                                          \
  void INVOKE(pid_t, const user_regs_struct &, ThreadSafeArena &);             \
  static inline void debug_##NAME##_callback_##INVOKE(                         \
      SubClass *self, pid_t tid, const user_regs_struct &regs,                 \
      ThreadSafeArena &arena) {                                                \
    self->INVOKE(tid, regs, arena);                                            \
  }                                                                            \
  static inline auto debug_##NAME##_register =                                 \
      SyscallRegister(SYS_##NAME, debug_##NAME##_callback_##INVOKE, nullptr)

#define DEBUG_SYSCALL_2(NAME, INVOKE, RESULT)                                  \
  void INVOKE(pid_t, const user_regs_struct &, ThreadSafeArena &);             \
  static inline void debug_##NAME##_callback_##INVOKE(                         \
      SubClass *self, pid_t tid, const user_regs_struct &regs,                 \
      ThreadSafeArena &arena) {                                                \
    self->INVOKE(tid, regs, arena);                                            \
  }                                                                            \
  void RESULT(pid_t, const user_regs_struct &, ThreadSafeArena &);             \
  static inline void debug_##NAME##_callback_##RESULT(                         \
      SubClass *self, pid_t tid, const user_regs_struct &regs,                 \
      ThreadSafeArena &arena) {                                                \
    self->RESULT(tid, regs, arena);                                            \
  }                                                                            \
  static inline auto debug_##NAME##_register =                                 \
      SyscallRegister(SYS_##NAME, debug_##NAME##_callback_##INVOKE,            \
                      debug_##NAME##_callback_##RESULT)

#define DEBUG_SYSCALL_(_1, _2, NAME, ...) NAME
#define DEBUG_SYSCALL(NAME, ...)                                               \
  DEBUG_SYSCALL_(__VA_ARGS__, DEBUG_SYSCALL_2, DEBUG_SYSCALL_1)                \
  (NAME, __VA_ARGS__)

#define DEBUG_FUNCTION_1(NAME, INVOKE)                                         \
  void INVOKE(pid_t, const user_regs_struct &, ThreadSafeArena &);             \
  static inline void debug_##NAME##_callback_##INVOKE(                         \
      SubClass *self, pid_t tid, const user_regs_struct &regs,                 \
      ThreadSafeArena &arena) {                                                \
    self->INVOKE(tid, regs, arena);                                            \
  }                                                                            \
  static inline auto debug_##NAME##_register =                                 \
      FunctionRegister(#NAME, debug_##NAME##_callback_##INVOKE, nullptr)

#define DEBUG_FUNCTION_2(NAME, INVOKE, RESULT)                                 \
  void INVOKE(pid_t, const user_regs_struct &, ThreadSafeArena &);             \
  static inline void debug_##NAME##_callback_##INVOKE(                         \
      SubClass *self, pid_t tid, const user_regs_struct &regs,                 \
      ThreadSafeArena &arena) {                                                \
    self->INVOKE(tid, regs, arena);                                            \
  }                                                                            \
  void RESULT(pid_t, const user_regs_struct &, ThreadSafeArena &);             \
  static inline void debug_##NAME##_callback_##RESULT(                         \
      SubClass *self, pid_t tid, const user_regs_struct &regs,                 \
      ThreadSafeArena &arena) {                                                \
    self->RESULT(tid, regs, arena);                                            \
  }                                                                            \
  static inline auto debug_##NAME##_register =                                 \
      FunctionRegister(#NAME, debug_##NAME##_callback_##INVOKE,                \
                       debug_##NAME##_callback_##RESULT)

#define DEBUG_FUNCTION_(_1, _2, NAME, ...) NAME
#define DEBUG_FUNCTION(NAME, ...)                                              \
  DEBUG_FUNCTION_(__VA_ARGS__, DEBUG_FUNCTION_2, DEBUG_FUNCTION_1)             \
  (NAME, __VA_ARGS__)

} // namespace Memory::Profile
