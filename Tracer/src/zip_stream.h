/*
Copyright (c) 2026, Chen Jie, Joungtao, Xuzheng Jiang
All rights reserved.
This source code is licensed under the BSD-2-Clause license found in the
LICENSE file in the root directory of this source tree.
*/

#pragma once

#include <memory>

namespace Zip::Stream {

enum class CompressionLevel : int {
    DEFAULT = 0,
};

std::shared_ptr<std::ostream> CreateFile(const std::string &file, CompressionLevel level = CompressionLevel::DEFAULT);
std::shared_ptr<std::istream> OpenFile(const std::string &file);

} // namespace Zip::Stream
