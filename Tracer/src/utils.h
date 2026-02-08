#pragma once

#include <cstdarg>
#include <cstdio>
#include <ranges>


namespace Memory::Profile {

inline void Log(const char *format, ...) {
  va_list ap;
  va_start(ap, format);
  vfprintf(stdout, format, ap);
  va_end(ap);
  fprintf(stdout, "\n");
}

auto enumerate(auto &data) {
  return data | std::views::transform([i = 0](auto &value) mutable {
           return std::make_pair(i++, value);
         });
}

} // namespace Memory::Profile
