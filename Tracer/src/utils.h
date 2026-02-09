/*
Copyright (c) 2026, Chen Jie, Joungtao, Xuzheng Jiang
All rights reserved.
This source code is licensed under the BSD-2-Clause license found in the
LICENSE file in the root directory of this source tree.
*/

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
