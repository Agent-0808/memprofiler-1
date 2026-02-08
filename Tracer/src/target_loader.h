#pragma once

#include <cstdint>
#include <functional>
#include <set>
#include <string>

#include "sys/types.h"

namespace Memory::Profile {

using OffsetCallback = std::function<bool(const char *name, uintptr_t offset)>;

std::string get_target_path(pid_t pid);
std::string get_file_path(pid_t pid, uint64_t fd);

uintptr_t get_maps_addr(pid_t pid, const char *segment);

bool get_maps_addr(pid_t pid, const std::set<std::string> &ignore,
                   OffsetCallback callback);

bool get_function_offset(const char *path, OffsetCallback callback);
bool get_relocation_offset(const char *path, OffsetCallback callback);

} // namespace Memory::Profile
