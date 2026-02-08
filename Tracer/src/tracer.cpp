#include "tracer.h"

#include <limits>
#include <unistd.h>

#include "utils.h"

namespace Memory::Profile {

namespace {
bool init_traceconfig(TraceData &data, const Config &config) {
  data.config.isGetTraceData = config.isGetTraceData;
  data.config.isGetStackTrace = config.isGetStackTrace;
  data.config.isSaveTraceData = config.isSaveTraceData;
  data.config.maxStackTraceDepth = config.maxStackTraceDepth;
  data.config.isPrintStack = config.isPrintStack;
  data.config.isPrintInvokeResultLog = config.isPrintInvokeResultLog;
  data.config.isPrintSaveEntry = config.isPrintSaveEntry;

  data.config.save_binary_path = config.save_binary_path;
  return true;
}

bool init_statinfo(StatInfo &stat, const Config &config) {
  stat.argc = config.argc();
  stat.argv = config.argv();
  stat.timestamp_start = config.startTimestamp();
  return true;
}
} // namespace

void Tracer::invoke(Operation op, pid_t tid, uintptr_t arg1, uintptr_t arg2,
                    TraceData::ThreadContext &context) {
  stat.op_invoke_count[op.index()]++;
  int stacksize = 0;
  data.add(op.invoke(), tid, arg1, arg2, context, &stacksize);
  stat.max_stack_size = std::max(stacksize, stat.max_stack_size);
}

void Tracer::result(Operation op, pid_t tid, uintptr_t ret,
                    TraceData::ThreadContext &context) {
  stat.op_result_count[op.index()]++;
  data.add(op.result(), tid, ret, 0, context, nullptr);
}

#ifdef TRACE_BRK
void Tracer::on_brk_invoke(pid_t tid, const user_regs_struct &regs,
                           TraceData::ThreadContext &context) {
  invoke(op_type::BRK, tid, regs.rdi, 0, context);
}
void Tracer::on_brk_result(pid_t tid, const user_regs_struct &regs,
                           TraceData::ThreadContext &context) {
  result(op_type::BRK, tid, regs.rax, context);
}
#endif
#ifdef TRACE_SBRK
void Tracer::on_sbrk_invoke(pid_t tid, const user_regs_struct &regs,
                            TraceData::ThreadContext &context) {
  invoke(op_type::SBRK, tid, regs.rdi, 0, context);
}
void Tracer::on_sbrk_result(pid_t tid, const user_regs_struct &regs,
                            TraceData::ThreadContext &context) {
  result(op_type::SBRK, tid, regs.rax, context);
}
#endif
#ifdef TRACE_MMAP
void Tracer::on_mmap_invoke(pid_t tid, const user_regs_struct &regs,
                            TraceData::ThreadContext &context) {
  invoke(op_type::MMAP, tid, regs.rdi, regs.rsi, context);
}
void Tracer::on_mmap_result(pid_t tid, const user_regs_struct &regs,
                            TraceData::ThreadContext &context) {
  result(op_type::MMAP, tid, regs.rax, context);
}
#endif
#ifdef TRACE_MUNMAP
void Tracer::on_munmap_invoke(pid_t tid, const user_regs_struct &regs,
                              TraceData::ThreadContext &context) {
  invoke(op_type::MUNMAP, tid, regs.rdi, regs.rsi, context);
}
void Tracer::on_munmap_result(pid_t tid, const user_regs_struct &regs,
                              TraceData::ThreadContext &context) {
  result(op_type::MUNMAP, tid, regs.rax, context);
}
#endif

#ifdef TRACE_FORK
void Tracer::on_clone_invoke(pid_t tid, const user_regs_struct &regs,
                             TraceData::ThreadContext &context) {
  // RDI: flags
  invoke(op_type::CLONE, tid, regs.rdi, 0, context);
}

void Tracer::on_clone_result(pid_t tid, const user_regs_struct &regs,
                             TraceData::ThreadContext &context) {
  // RAX: child pid
  result(op_type::CLONE, tid, regs.rax, context);
}
void Tracer::on_clone3_invoke(pid_t tid, const user_regs_struct &regs,
                              TraceData::ThreadContext &context) {
  // RDI: flags
  invoke(op_type::CLONE3, tid, regs.rdi, 0, context);
}

void Tracer::on_clone3_result(pid_t tid, const user_regs_struct &regs,
                              TraceData::ThreadContext &context) {
  // RAX: child pid
  result(op_type::CLONE3, tid, regs.rax, context);
}
void Tracer::on_fork_invoke(pid_t tid, const user_regs_struct &regs,
                            TraceData::ThreadContext &context) {
  invoke(op_type::FORK, tid, 0, 0, context);
}

void Tracer::on_fork_result(pid_t tid, const user_regs_struct &regs,
                            TraceData::ThreadContext &context) {
  result(op_type::FORK, tid, regs.rax, context);
}
void Tracer::on_vfork_invoke(pid_t tid, const user_regs_struct &regs,
                             TraceData::ThreadContext &context) {
  invoke(op_type::VFORK, tid, 0, 0, context);
}

void Tracer::on_vfork_result(pid_t tid, const user_regs_struct &regs,
                             TraceData::ThreadContext &context) {
  result(op_type::VFORK, tid, regs.rax, context);
}
#endif

#ifdef TRACE_EXECVE
void Tracer::on_execve_invoke(pid_t tid, const user_regs_struct &regs,
                              TraceData::ThreadContext &context) {
  // RDI: flags
  invoke(op_type::EXECVE, tid, regs.rdi, regs.rsi, context);
}

void Tracer::on_execve_result(pid_t tid, const user_regs_struct &regs,
                              TraceData::ThreadContext &context) {
  // RAX: child pid
  result(op_type::EXECVE, tid, regs.rax, context);
}
#endif

#ifdef TRACE_FREE
void Tracer::on_free_invoke(pid_t tid, const user_regs_struct &regs,
                            TraceData::ThreadContext &context) {
  invoke(op_type::FREE, tid, regs.rdi, 0, context);
}
#endif
#ifdef TRACE_MALLOC
void Tracer::on_malloc_invoke(pid_t tid, const user_regs_struct &regs,
                              TraceData::ThreadContext &context) {
  invoke(op_type::MALLOC, tid, regs.rdi, 0, context);
}
void Tracer::on_malloc_result(pid_t tid, const user_regs_struct &regs,
                              TraceData::ThreadContext &context) {
  result(op_type::MALLOC, tid, regs.rax, context);
}
#endif
#ifdef TRACE_CALLOC
void Tracer::on_calloc_invoke(pid_t tid, const user_regs_struct &regs,
                              TraceData::ThreadContext &context) {
  invoke(op_type::CALLOC, tid, regs.rdi, regs.rsi, context);
}
void Tracer::on_calloc_result(pid_t tid, const user_regs_struct &regs,
                              TraceData::ThreadContext &context) {
  result(op_type::CALLOC, tid, regs.rax, context);
}
#endif
#ifdef TRACE_REALLOC
void Tracer::on_realloc_invoke(pid_t tid, const user_regs_struct &regs,
                               TraceData::ThreadContext &context) {
  invoke(op_type::REALLOC, tid, regs.rdi, regs.rsi, context);
}
void Tracer::on_realloc_result(pid_t tid, const user_regs_struct &regs,
                               TraceData::ThreadContext &context) {
  result(op_type::REALLOC, tid, regs.rax, context);
}
#endif
#ifdef TRACE_VALLOC
void Tracer::on_valloc_invoke(pid_t tid, const user_regs_struct &regs,
                              TraceData::ThreadContext &context) {
  invoke(op_type::VALLOC, tid, regs.rdi, 0, context);
}
void Tracer::on_valloc_result(pid_t tid, const user_regs_struct &regs,
                              TraceData::ThreadContext &context) {
  result(op_type::VALLOC, tid, regs.rax, context);
}
#endif
#ifdef TRACE_MALLOCCALLED
void Tracer::on_aligned_alloc_invoke(pid_t tid, const user_regs_struct &regs,
                                     TraceData::ThreadContext &context) {
  invoke(op_type::ALIGNED_ALLOC, tid, regs.rdi, regs.rsi, context);
}
void Tracer::on_aligned_alloc_result(pid_t tid, const user_regs_struct &regs,
                                     TraceData::ThreadContext &context) {
  result(op_type::ALIGNED_ALLOC, tid, regs.rax, context);
}

void Tracer::on_posix_memalign_invoke(pid_t tid, const user_regs_struct &regs,
                                      TraceData::ThreadContext &context) {
  // 注意：这个函数的参数顺序与malloc不同，所以需要特殊处理
  // posix_memalign(&ptr, alignment, size)， 返回值为0或报错码
  // 所以arg1, arg2分别是size(rdx), alignment(rsi)， 返回值为&ptr (rdi)
  invoke(op_type::POSIX_MEMALIGN, tid, regs.rdx, regs.rsi, context);
}
void Tracer::on_posix_memalign_result(pid_t tid, const user_regs_struct &regs,
                                      TraceData::ThreadContext &context) {
  result(op_type::POSIX_MEMALIGN, tid, regs.rdi, context);
}
#endif

#ifdef TRACE_CPP
void Tracer::on_new_invoke(pid_t tid, const user_regs_struct &regs,
                           TraceData::ThreadContext &context) {
  invoke(op_type::NEW, tid, regs.rdi, 0, context);
}
void Tracer::on_new_result(pid_t tid, const user_regs_struct &regs,
                           TraceData::ThreadContext &context) {
  result(op_type::NEW, tid, regs.rax, context);
}

void Tracer::on_new_array_invoke(pid_t tid, const user_regs_struct &regs,
                                 TraceData::ThreadContext &context) {
  invoke(op_type::NEW_ARRAY, tid, regs.rdi, regs.rsi, context);
}
void Tracer::on_new_array_result(pid_t tid, const user_regs_struct &regs,
                                 TraceData::ThreadContext &context) {
  result(op_type::NEW_ARRAY, tid, regs.rax, context);
}

void Tracer::on_delete_legacy_invoke(pid_t tid, const user_regs_struct &regs,
                                     TraceData::ThreadContext &context) {
  invoke(op_type::DELETE_LEGACY, tid, regs.rdi, 0, context);
}
void Tracer::on_delete_invoke(pid_t tid, const user_regs_struct &regs,
                              TraceData::ThreadContext &context) {
  invoke(op_type::DELETE, tid, regs.rdi, regs.rsi, context);
}
void Tracer::on_delete_array_invoke(pid_t tid, const user_regs_struct &regs,
                                    TraceData::ThreadContext &context) {
  invoke(op_type::DELETE_ARRAY, tid, regs.rdi, 0, context);
}
#endif

void Tracer::gatherStat() {

  // 统计调用次数
  for (int i = 0; i < Operation::op_type_count; i++) {
    stat.invoke_count += stat.op_invoke_count[i];
    stat.result_count += stat.op_result_count[i];
  }
  stat.total_count = stat.invoke_count + stat.result_count;

  // 统计数据
  stat.main_pid = target_pid;
  stat.time_end = data.getTime();
  stat.target_full_path = target_path;
  stat.main_pid = target_pid;
  stat.target = config.command()[0];
  stat.working_dir = std::filesystem::current_path().string();
  stat.save_path = config.parentDir();
  stat.commands = config.command();
  stat.timestamp_end = config.getTimestamp();
  stat.filename_max_length = data.filename_max_length;
  stat.function_max_length = data.function_max_length;

  // 额外的信息（键值对）
  stat.extrakeys = config.extrakeys;
}

void Tracer::on_library_loaded(pid_t tid) { data.on_library_loaded(tid); }
void Tracer::add_new_tid(pid_t parent, pid_t child) {
  stat.child_tid_list.push_back(child);
  stat.tid_relations.push_back(std::pair(parent, child));
}

bool Tracer::run_target() {
  auto pid = fork(); // 启动子程序

  if (pid > 0) {
    target_pid = pid;
    return true;
  } else if (pid < 0) {
    perror("fork");
    return false;
  }

  Log("run target: %s", config.command()[0]);

  /* 允许跟踪该进程 */
  if (ptrace(PTRACE_TRACEME, 0, 0, 0) < 0) {
    perror("trace me");
    return false;
  }

  // notify parent that tracing can start
  // kill(getpid(), SIGSTOP);

  /* 用给定的程序替换该进程的映像 */
  // execv(config.command()[0], config.command().data() + 1);
  execv(config.command()[0], config.command().data());
  return true;
}

bool Tracer::attach_target() {
  static constexpr auto PID_MAX =
      static_cast<pid_t>(std::numeric_limits<pid_t>::max());
  if (config.pid() > PID_MAX) {
    Log("config target pid(%llu) out of range(%llu)", config.pid(), PID_MAX);
    return false;
  }
  target_pid = static_cast<pid_t>(config.pid());

  Log("attach target with pid(%d)", target_pid);
  // TODO: attach target with pid
  if (ptrace(PTRACE_ATTACH, target_pid, nullptr, nullptr) == -1) {
    perror("Failed to attach to target process");
    Log("Failed to attach to target process with pid(%d)", target_pid);
    return false;
  }
  return true;
}

int Tracer::run(int argc, char *argv[]) {
#define CHECK(S)                                                               \
  do {                                                                         \
    if (!(S)) {                                                                \
      fprintf(stderr, "[CHECK]%s failed\n at [%s] from [%s] at line [%d]\n",   \
              #S, __func__, __FILE__, __LINE__);                               \
      return -1;                                                               \
    }                                                                          \
  } while (0)

  CHECK(config.parseArgs(argc, argv));
  CHECK(config.pid() > 0 ? attach_target() : run_target());

  if (target_pid == 0) {
    return 0;
  }
  CHECK(target_pid > 0);
  CHECK(config.init());
  CHECK(init_statinfo(stat, config));
  CHECK(init_traceconfig(data, config));
  CHECK(data.start(target_pid));
  CHECK(this->Debugger::run());

#undef CHECK
  gatherStat();

  if (config.isPrintStatInfo)
    stat.print();

  stat.save(config.stat_info_path);
  return 0;
}

} // namespace Memory::Profile
