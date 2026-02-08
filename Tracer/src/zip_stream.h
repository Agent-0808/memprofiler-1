#pragma once

#include <memory>

namespace Zip::Stream {

enum class CompressionLevel : int {
    DEFAULT = 0,
};

std::shared_ptr<std::ostream> CreateFile(const std::string &file, CompressionLevel level = CompressionLevel::DEFAULT);
std::shared_ptr<std::istream> OpenFile(const std::string &file);

} // namespace Zip::Stream
