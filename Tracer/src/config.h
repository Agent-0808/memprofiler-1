#pragma once
#include <chrono>
#include <cstdint>
#include <string>
#include <vector>

namespace Memory::Profile {
using TimePoint = std::chrono::steady_clock::time_point; // 时间点
class Config {
  uint64_t pid_ = 0;
  std::vector<char *> command_;
  TimePoint startTime_;
  std::string start_timestamp;
  std::string executable_name;
  int argc_ = 0;
  char **argv_;
  void resolvePresetCategory();

public:
  bool parseArgs(int argc, char *argv[]);
  bool init();

// 是否检测特定调用
#define TRACE_BRK
#define TRACE_SBRK
#define TRACE_MMAP
#define TRACE_MUNMAP
#define TRACE_FORK
#define TRACE_EXECVE
#define TRACE_FREE
#define TRACE_MALLOC
#define TRACE_CALLOC
#define TRACE_REALLOC
#define TRACE_VALLOC
#define TRACE_MALLOCCALLED
#define TRACE_CPP

  // 是否提取调用栈信息
  bool isGetStackTrace = true;
  // 遍历调用栈时最大查找深度
  int maxStackTraceDepth = 100;

  // 是否打印invoke或result的Log记录
  bool isPrintInvokeResultLog = true;
  // 调试时是否打印调用栈
  bool isPrintStack = false;
  // 是否打印调用栈的文件名或函数名
  bool isPrintSaveEntry = false;
  // 是否打印额外信息
  bool isPrintStatInfo = true;

  // 是否保存跟踪数据
  bool isGetTraceData = true;  // TODO
  bool isSaveTraceData = true; // TODO
  const std::string save_binary_filename = "memory.profile";
  const std::string stat_info_filename = "statinfo.txt";

  std::string save_directory = "tracedata";
  std::string save_category = "";

  std::string save_binary_path = save_directory + save_binary_filename;
  std::string stat_info_path = save_directory + stat_info_filename;

  // 额外记录的键值对
  std::vector<std::pair<std::string, std::string>> extrakeys;

  int argc() const { return argc_; }
  char **argv() const { return argv_; }
  uint64_t pid() const { return pid_; }
  const std::vector<char *> &command() const { return command_; }
  const TimePoint &startTime() const { return startTime_; }
  const std::string parentDir() const;
  const std::string getTimestamp() const;
  const std::string startTimestamp() const { return start_timestamp; }
};
} // namespace Memory::Profile
