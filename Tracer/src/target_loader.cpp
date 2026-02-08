#include "target_loader.h"

#include <cstring>

#include "elf.h"
#include "elfutils/libdwfl.h"
#include "fcntl.h"
#include "libunwind-ptrace.h"
#include "libunwind.h"
#include "sys/mman.h"
#include "sys/stat.h"
#include "unistd.h"

#include "utils.h"

namespace Memory::Profile {

namespace {
constexpr size_t NUMBER_SIZE = 32;
constexpr size_t BUFFER_SIZE = 8192;
} // namespace

std::string get_target_path(pid_t pid) {
  // 读取文件"/proc/pid/exe"，获取目标可执行程序的路径
  char path[NUMBER_SIZE] = {0};
  auto result = snprintf(path, sizeof(path), "/proc/%d/exe", pid);
  if (result <= 0 || result >= sizeof(path)) {
    Log("get target proc exe path of pid(%d) error: result(%d) out of "
        "range(%llu)",
        pid, result, sizeof(path));
    return "";
  }

  char content[BUFFER_SIZE] = {0};
  result = readlink(path, content, sizeof(content));
  if (result <= 0 || result >= sizeof(content)) {
    Log("get target proc exe content of '%s' error: result(%d) out of "
        "range(%llu)",
        path, result, sizeof(content));
    return "";
  }

  return std::string(content, result);
}

std::string get_file_path(pid_t pid, uint64_t fd) {
  // 读取文件"/proc/pid/exe"，获取目标可执行程序的路径
  char path[NUMBER_SIZE << 1] = {0};
  auto result = snprintf(path, sizeof(path), "/proc/%d/fd/%lu", pid, fd);
  if (result <= 0 || result >= sizeof(path)) {
    Log("get fd(%llu) file path of pid(%d) error: result(%d) out of "
        "range(%llu)",
        fd, pid, result, sizeof(path));
    return "";
  }

  char content[BUFFER_SIZE] = {0};
  result = readlink(path, content, sizeof(content));
  if (result <= 0) {
    return "";
  } else if (result >= sizeof(content)) {
    Log("get file path content of '%s' error: result(%d) out of range(%llu)",
        path, result, sizeof(content));
    return "";
  }

  return std::string(content, result);
}
uintptr_t get_maps_addr(pid_t pid, const char *segment) {
  uintptr_t result{};
  get_maps_addr(pid, {},
                [&result, segment](const char *name, uintptr_t base) -> bool {
                  if (strcmp(segment, name) == 0) {
                    result = base;
                    return true;
                  }
                  return false;
                });
  return result;
}

bool get_maps_addr(pid_t pid, const std::set<std::string> &ignore,
                   OffsetCallback callback) {
  // 读取文件"/proc/pid/maps"，获取目标基地址等
  char path[NUMBER_SIZE] = {0};
  auto n = snprintf(path, sizeof(path), "/proc/%d/maps", pid);
  if (n <= 0 || n >= sizeof(path)) {
    Log("get target proc maps path of pid(%d) error: size(%d) out of "
        "range(%llu)",
        pid, n, sizeof(path));
    return false;
  }

  auto file = fopen(path, "rb");
  if (!file) {
    perror("open maps file");
    return false;
  }

  char addr[NUMBER_SIZE] = {0};
  char maps[NUMBER_SIZE] = {0};
  char name[BUFFER_SIZE] = {0};
  while (!feof(file)) {
    // 解析一行：
    // 例如：7f6764831000-7f6764833000 r--p 00000000 08:10 6230
    // /usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2
    // 以空格分隔，第一项的"-"左边数字为待提取的基地址，存入addr，第三项是maps，第六项为name
    if (fscanf(file, "%[^-]-%*[^ ] %*[^ ] %[^ ] %*[^ ] %*[^ ] %[^\n]\n", addr,
               maps, name) < 0) {
      perror("read line of maps file");
      break;
    }

    // 检查匹配条件:
    // 检查maps是否以"00000000"开头，表示它是可执行文件的基地址
    // 检查name是否是segment(进程的可执行文件路径或"[head]")
    // 将addr转为uintptr_t并记录
    if (strcmp(maps, "00000000") == 0 && ignore.find(name) == ignore.end()) {
      uintptr_t base{};
      sscanf(addr, "%lx", &base);
      if (callback(name, base)) {
        break;
      }
    }
  }

  fclose(file);
  return true;
}

bool parse_elf_file(const char *data, size_t length, OffsetCallback callback,
                    bool from_relocation) {
  // 将data强制转换为Elf64_Ehdr结构体指针，表示ELF文件头
  if (length <= sizeof(Elf64_Ehdr)) {
    return false;
  }
  auto ehdr = reinterpret_cast<const Elf64_Ehdr *>(data);
  // 读取 ELF 文件头中的段表数量
  auto table_max = ehdr->e_shnum;
  // 读取 ELF 文件头中字符串表的位置(字符串表在段表中的下标)
  auto shstrndx = ehdr->e_shstrndx;

  // 计算段表数组，将data加上段表在文件中的偏移(e_shoff)得到Elf64_Shdr数组的起始位置
  if (length <= ehdr->e_shoff + sizeof(Elf64_Shdr)) {
    return false;
  }
  auto stables = reinterpret_cast<const Elf64_Shdr *>(data + ehdr->e_shoff);

  // 字符串表
  auto shstrtab_addr = data + stables[shstrndx].sh_offset;

  // 符号表的位置和项数
  const Elf64_Sym *dynsym = nullptr;
  uint64_t dynsym_count = 0;
  // 字符串表的位置
  const char *dynstr = nullptr;
  uint64_t dynstr_size = 0;
  // 重定向表的位置和项数
  const Elf64_Rela *plt_rel = nullptr;
  uint64_t plt_rel_count = 0;

  // 查找段表名
  int count = from_relocation ? 3 : 2;
  for (decltype(table_max) i = 0; i < table_max && count > 0; i++) {
    if (length < stables[i].sh_offset + stables[i].sh_size) {
      return false;
    } else if (strcmp(shstrtab_addr + stables[i].sh_name, ".dynsym") == 0) {
      // 获取动态符号表
      dynsym = reinterpret_cast<const Elf64_Sym *>(data + stables[i].sh_offset);
      dynsym_count = stables[i].sh_size / sizeof(Elf64_Sym);
      count--;
    } else if (strcmp(shstrtab_addr + stables[i].sh_name, ".dynstr") == 0) {
      // 获取字符串表
      dynstr = data + stables[i].sh_offset;
      dynstr_size = stables[i].sh_size;
      count--;
    } else if (from_relocation &&
               strcmp(shstrtab_addr + stables[i].sh_name, ".rela.plt") == 0) {
      // 获取重定向表
      plt_rel =
          reinterpret_cast<const Elf64_Rela *>(data + stables[i].sh_offset);
      plt_rel_count = stables[i].sh_size / sizeof(Elf64_Rela);
      count--;
    }
  }

  if (from_relocation) {
    // 遍历重定向表
    for (uint64_t i = 0; i < plt_rel_count; i++, plt_rel++) {
      auto sym = ELF64_R_SYM(plt_rel->r_info);
      if (sym != 0) {
        if (dynstr_size <= dynsym[sym].st_name) {
          return false;
        }
        auto sym_name = dynstr + dynsym[sym].st_name;
        if (callback(sym_name, plt_rel->r_offset)) {
          break;
        }
      }
    }
  } else {
    // 遍历动态符号表
    for (uint64_t i = 0; i < dynsym_count; i++, dynsym++) {
      // 检查符号类型，确保是函数
      if (ELF64_ST_TYPE(dynsym->st_info) != STT_FUNC) {
        continue;
      }
      if (dynstr_size <= dynsym->st_name) {
        return false;
      }
      auto sym_name = dynstr + dynsym->st_name;
      if (callback(sym_name, dynsym->st_value)) {
        break;
      }
    }
  }

  return true;
}

inline bool get_function_offset(const char *path, OffsetCallback callback,
                                bool from_relocation) {
  auto fd = open(path, O_RDONLY);
  if (fd < 0) {
    perror("open target file");
    return false;
  }

  // obtain file size
  struct stat sb;
  if (fstat(fd, &sb) < 0) {
    perror("get file stat");
    return false;
  } else if (sb.st_size <= 0) {
    Log("bad size(%d) of target file: %s", sb.st_size, path);
    return false;
  }

  auto length = static_cast<size_t>(sb.st_size);
  auto data = static_cast<const char *>(
      mmap(nullptr, length, PROT_READ, MAP_PRIVATE, fd, 0));
  if (data == MAP_FAILED) {
    perror("mmap target file");
    return false;
  }

  if (!parse_elf_file(data, length, callback, from_relocation)) {
    Log("bad elf format of target file: %s", path);
    return false;
  }

  return true;
}

bool get_function_offset(const char *path, OffsetCallback callback) {
  return get_function_offset(path, callback, false);
}

bool get_relocation_offset(const char *path, OffsetCallback callback) {
  return get_function_offset(path, callback, true);
}
} // namespace Memory::Profile
