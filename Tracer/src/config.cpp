#include "config.h"
#include "utils.h"

#include "boost/format.hpp"

#include <cstdlib> // for std::stoull
#include <cstring>
#include <filesystem>
#include <stdexcept> // for exception handling

namespace Memory::Profile {

static constexpr std::string_view HELP_TEXT =
    R"(Usage: mprofiler [OPTION...] [COMMAND]...
  
  Examples:
    mprofiler -p 12345        # Profile progress with specified pid(12345).
    mprofiler command args... # Run command with args and profile it.
  
  Options:
    -h, --help             Show help options
    -p, --pid              Specified pid of target progress
    --no-trace             Don't get trace data
    --no-stack             Don't get stack trace
    --no-save              Don't save trace data  
    --save-dir             Specified save directory
    --category             Specified save category. 
                           Preset: "/name/time" "/name-time" "time-name" "/name"
    --stack                Specified max stack trace depth, -1 means don't trace
    --no-print-log         Don't print logs
    --no-print-stack       Don't print stack trace
    --no-print-save        Don't print saved entries
    --no-print-extra       Don't print extra info
    --extra key=value      Specified extra key-value pair(Saved in statinfo.txt)
  )";

bool Config::parseArgs(int argc, char *argv[]) {
  //  如果未提供有效的命令或参数，显示帮助信息
  if (argc <= 1) {
    Log("argc: %d", argc);
    for (int i = 0; i < argc; i++) {
      Log("argv %d: %s", i, argv[i]);
    }
    Log(HELP_TEXT.data());
    return false;
  }
  argc_ = argc;
  argv_ = argv;

  for (int i = 1; i < argc; ++i) {
    std::string arg = argv[i];

    // 检查是否为帮助命令
    if (arg == "-h" || arg == "--help") {
      Log(HELP_TEXT.data());
      exit(0);
      return false;
    }
    // 设置 PID 的命令
    else if ((arg == "-p" || arg == "--pid") && i + 1 < argc) {
      try {
        pid_ = std::stoull(argv[++i]);
      } catch (const std::invalid_argument &e) {
        Log("Invalid PID: %s", argv[i]);
        return false;
      } catch (const std::out_of_range &e) {
        Log("PID out of range: %s", argv[i]);
        return false;
      }
    }
    // 设置保存路径的命令
    else if ((arg == "--save-dir") && i + 1 < argc) {
      save_directory = argv[++i];
    }
    // 设置保存路径的子文件夹的命令
    else if ((arg == "--category") && i + 1 < argc) {
      save_category = argv[++i];
    }
    // 设置查找不查看调用栈的命令
    else if ((arg == "--no-stack") && i + 1 < argc) {
      isGetStackTrace = false;
    }
    // 设置查找堆栈深度的命令
    else if ((arg == "--stack") && i + 1 < argc) {
      maxStackTraceDepth = std::stoi(argv[++i]);
      isGetStackTrace = maxStackTraceDepth >= 0;
    }
    // 设置不跟踪信息的命令
    else if ((arg == "--no-trace")) {
      isGetTraceData = false;
    }
    // 设置不保存检测信息的命令
    else if (arg == "--no-save") {
      isSaveTraceData = false;
    }
    // 设置打印Log的命令
    else if (arg == "--print-log") {
      isPrintInvokeResultLog = true;
    }
    // 设置不打印Log的命令
    else if (arg == "--no-print-log") {
      isPrintInvokeResultLog = false;
    }
    // 设置打印调用栈的命令
    else if (arg == "--print-stack") {
      isPrintStack = true;
    }
    // 设置不打印调用栈的命令
    else if (arg == "--no-print-stack") {
      isPrintStack = false;
    }
    // 设置打印保存内容的命令
    else if (arg == "--print-save") {
      isPrintSaveEntry = true;
    }
    // 设置不打印保存内容的命令
    else if (arg == "--no-print-save") {
      isPrintSaveEntry = false;
    }
    // 设置打印统计信息的命令
    else if (arg == "--print-stat") {
      isPrintStatInfo = true;
    }
    // 设置不打印统计信息的命令
    else if (arg == "--no-print-stat") {
      isPrintStatInfo = false;
    }

    // 储存额外的信息（键值对）
    else if (arg == "--extra" && i + 1 < argc) {
      // 示例：--extra key1=value1,key2=value2,key3=value3
      const char delimiter = '=', comma = ',';
      std::string extra_arg = argv[++i];
      size_t comma_pos = 0;
      while (comma_pos != std::string::npos) {
        size_t next_comma_pos = extra_arg.find(comma, comma_pos);
        std::string pair_str =
            extra_arg.substr(comma_pos, next_comma_pos - comma_pos);

        size_t delimiter_pos = pair_str.find(delimiter);
        if (delimiter_pos != std::string::npos) {
          std::string key = pair_str.substr(0, delimiter_pos);
          std::string value = pair_str.substr(delimiter_pos + 1);
          if (!key.empty() && !value.empty()) {
            extrakeys.emplace_back(key, value);
            Log("Extra key-value pair: %s=%s", key.c_str(), value.c_str());
          } else {
            Log("Invalid key or value in extra argument: %s", pair_str.c_str());
            return false;
          }
        } else {
          Log("Invalid extra argument format: %s", pair_str.c_str());
          return false;
        }
        comma_pos = (next_comma_pos == std::string::npos) ? std::string::npos
                                                          : next_comma_pos + 1;
      }
    }

    // MemProfiler 的参数已结束，后面的是被测程序的参数
    else {
      // 提取被测程序的文件名
      std::string target = argv[i];

      // 判断config.command()[0]是否在文件系统中存在
      if (!std::filesystem::exists(target)) {
        perror("Failed to find target program");
        Log("ERROR: target program not found: %s", target.c_str());
        exit(1);
        return false;
      }
      size_t last_slash_pos = target.find_last_of('/');
      executable_name = (last_slash_pos == std::string::npos)
                            ? target
                            : target.substr(last_slash_pos + 1);

      // 将参数存储到 command_ 向量中
      while (i < argc) {
        command_.push_back(argv[i]);
        i++;
      }
      // 不额外添加一个空指针似乎会出错
      command_.push_back(nullptr);
    }
  }

  return true;
}
void Config::resolvePresetCategory() {
  if (save_category == "/name/time") {
    save_category = (std::filesystem::path)executable_name / start_timestamp;
  } else if (save_category == "/name-time") {
    save_category = executable_name + "-" + start_timestamp;
  } else if (save_category == "/time-name") {
    save_category = start_timestamp + "-" + executable_name;
  } else if (save_category == "/name") {
    save_category = executable_name;
  } else if (save_category.empty()) {
    // 默认情况：executable/time
    save_category = (std::filesystem::path)executable_name / start_timestamp;
  }
}
bool Config::init() {
  startTime_ = std::chrono::steady_clock::now();
  start_timestamp = getTimestamp();

  resolvePresetCategory(); // 处理category预设值

  // 创建保存目录
  std::filesystem::path parent_directory = parentDir();
  std::filesystem::create_directories(parent_directory);

  save_binary_path = parent_directory / save_binary_filename;
  stat_info_path = parent_directory / stat_info_filename;

  printf("Executing command: ");
  for (int i = 0; i < command_.size(); i++) {
    printf("%s ", command_[i]);
  }
  printf("\n");

  return true;
}
const std::string Config::parentDir() const {
  return (std::filesystem::path)save_directory / save_category;
}

const std::string Config::getTimestamp() const {
  using namespace std::chrono;
  // 获取当前时间点（使用system_clock以获取日历时间）
  auto now = system_clock::now();

  // 转换为time_t以获取年月日时分秒
  time_t tt = system_clock::to_time_t(now);
  struct tm tm;
#if defined(_WIN32)
  localtime_s(&tm, &tt);
#else
  localtime_r(&tt, &tm);
#endif

  // 分解时间到秒和纳秒部分
  auto since_epoch = now.time_since_epoch();
  auto sec = duration_cast<seconds>(since_epoch);
  since_epoch -= sec;
  auto nano = duration_cast<nanoseconds>(since_epoch);

  // 格式化日期和时间部分
  char date_time[20];
  strftime(date_time, sizeof(date_time), "%Y%m%d-%H%M%S", &tm);

  // 组合所有部分，确保纳秒部分为9位，前面补零
  return boost::str(boost::format("%s-%09d") % date_time % nano.count());
}

} // namespace Memory::Profile
