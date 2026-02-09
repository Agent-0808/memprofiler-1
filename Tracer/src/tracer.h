/*
Copyright (c) 2026, Chen Jie, Joungtao, Xuzheng Jiang
All rights reserved.
This source code is licensed under the BSD-2-Clause license found in the
LICENSE file in the root directory of this source tree.
*/

#pragma once

#include "config.h"
#include "debugger.h"
#include "trace_data.h"

namespace Memory::Profile {
class Tracer : public Debugger<Tracer, TraceData::ThreadContext> {
  // 配置信息
  Config config;
  // 跟踪数据
  TraceData data;
  // 统计数据
  StatInfo stat;

#ifdef TRACE_BRK
  DEBUG_SYSCALL(brk, on_brk_invoke, on_brk_result);
#endif
#ifdef TRACE_SBRK
  DEBUG_FUNCTION(sbrk, on_sbrk_invoke, on_sbrk_result);
#endif
#ifdef TRACE_MMAP
  DEBUG_SYSCALL(mmap, on_mmap_invoke, on_mmap_result);
#endif
#ifdef TRACE_MUNMAP
  DEBUG_SYSCALL(munmap, on_munmap_invoke, on_munmap_result);
#endif
#ifdef TRACE_FORK
  DEBUG_SYSCALL(clone, on_clone_invoke, on_clone_result);
  DEBUG_SYSCALL(clone3, on_clone3_invoke, on_clone3_result);
  DEBUG_SYSCALL(fork, on_fork_invoke, on_fork_result);
  DEBUG_SYSCALL(vfork, on_vfork_invoke, on_vfork_result);
#endif
#ifdef TRACE_EXECVE
  DEBUG_SYSCALL(execve, on_execve_invoke, on_execve_result);
#endif
#ifdef TRACE_FREE
  DEBUG_FUNCTION(free, on_free_invoke);
#endif
#ifdef TRACE_MALLOC
  DEBUG_FUNCTION(malloc, on_malloc_invoke, on_malloc_result);
#endif
#ifdef TRACE_CALLOC
  DEBUG_FUNCTION(calloc, on_calloc_invoke, on_calloc_result);
#endif
#ifdef TRACE_REALLOC
  DEBUG_FUNCTION(realloc, on_realloc_invoke, on_realloc_result);
#endif
#ifdef TRACE_VALLOC
  DEBUG_FUNCTION(valloc, on_valloc_invoke, on_valloc_result);
#endif
#ifdef TRACE_MALLOCCALLED
  DEBUG_FUNCTION(posix_memalign, on_posix_memalign_invoke,
                 on_posix_memalign_result);
  DEBUG_FUNCTION(aligned_alloc, on_aligned_alloc_invoke,
                 on_aligned_alloc_result);
#endif
#ifdef TRACE_CPP
  DEBUG_FUNCTION(_Znwm, on_new_invoke, on_new_result);
  DEBUG_FUNCTION(_Znam, on_new_array_invoke, on_new_array_result);
  DEBUG_FUNCTION(_ZdlPv, on_delete_legacy_invoke);
  DEBUG_FUNCTION(_ZdlPvm, on_delete_invoke);
  DEBUG_FUNCTION(_ZdaPv, on_delete_array_invoke);
#endif

  bool run_target();
  bool attach_target();

  void gatherStat();

  void invoke(Operation op, pid_t tid, uintptr_t arg1, uintptr_t arg2,
              TraceData::ThreadContext &context);
  void result(Operation op, pid_t tid, uintptr_t ret,
              TraceData::ThreadContext &context);

public:
  int run(int argc, char *argv[]);
  void on_library_loaded(pid_t tid);
  void add_new_tid(pid_t parent, pid_t child);
};
} // namespace Memory::Profile
