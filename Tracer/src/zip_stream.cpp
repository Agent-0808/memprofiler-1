/*
Copyright (c) 2026, Chen Jie, Joungtao, Xuzheng Jiang
All rights reserved.
This source code is licensed under the BSD-2-Clause license found in the
LICENSE file in the root directory of this source tree.
*/

#include "zip_stream.h"

#include <vector>
#include <fstream>

// Required to access ZSTD_isFrame()
#define ZSTD_STATIC_LINKING_ONLY
#include "zstd.h"

namespace Zip::Stream {

/**
 * Custom exception for zip error codes
 */
struct exception : public std::exception {
  explicit exception(int code) : msg_("zstd: ") {
    msg_ += ZSTD_getErrorName(code);
  }

  const char* what() const throw() {
    return msg_.c_str();
  }

private:
  std::string msg_;
};

inline size_t check(size_t code) {
  if (ZSTD_isError(code)) {
    throw exception(code);
  }
  return code;
}

/**
 * Provides stream compression functionality
 */
struct cstream {
  cstream() {
    cstrm_ = ZSTD_createCStream();
  }

  ~cstream() {
    check(ZSTD_freeCStream(cstrm_));
  }

  size_t init(CompressionLevel level = CompressionLevel::DEFAULT) {
    return check(ZSTD_initCStream(cstrm_, static_cast<int>(level)));
  }

  size_t compress(ZSTD_outBuffer* output, ZSTD_inBuffer* input) {
    return check(ZSTD_compressStream(cstrm_, output, input));
  }

  size_t flush(ZSTD_outBuffer* output) {
    return check(ZSTD_flushStream(cstrm_, output));
  }

  size_t end(ZSTD_outBuffer* output) {
    return check(ZSTD_endStream(cstrm_, output));
  }

private:
  ZSTD_CStream* cstrm_;
};

/**
 * Provides stream decompression functionality
 */
struct dstream {
  dstream() {
    dstrm_ = ZSTD_createDStream();
    check(ZSTD_initDStream(dstrm_));
  }

  ~dstream() {
    check(ZSTD_freeDStream(dstrm_));
  }

  size_t decompress(ZSTD_outBuffer* output, ZSTD_inBuffer* input) {
    return check(ZSTD_decompressStream(dstrm_, output, input));
  }

private:
  ZSTD_DStream* dstrm_;
};

/**
 * stream buffer for compression. Data is written in a single big frame.
 */
class ostreambuf : public std::streambuf {
public:
  explicit ostreambuf(std::streambuf* sbuf, CompressionLevel level = CompressionLevel::DEFAULT) : sbuf_(sbuf), clevel_(level), strInit_(false) {
    inbuf_.resize(ZSTD_CStreamInSize());
    outbuf_.resize(ZSTD_CStreamOutSize());
    inhint_ = inbuf_.size();
    setp(inbuf_.data(), inbuf_.data() + inhint_);
  }

  virtual ~ostreambuf() {
    sync();
  }

  using int_type = typename std::streambuf::int_type;

  virtual int_type overflow(int_type ch = traits_type::eof()) {
    auto pos = compress(pptr() - pbase());
    if (pos < 0) {
      setp(nullptr, nullptr);
      return traits_type::eof();
    }
    setp(inbuf_.data() + pos, inbuf_.data() + inhint_);
    return ch == traits_type::eof() ? traits_type::eof() : sputc(ch);
  }

  virtual int sync() {
    overflow();
    if (!pptr() || !strInit_) {
      return -1;
    }

    // We've been asked to sync, so finish the Zstd frame
    size_t ret = 0;
    while (strInit_) {
      ZSTD_outBuffer output = {outbuf_.data(), outbuf_.size(), 0};
      // If ret > 0, Zstd still needs to write some more data
      // and the frame is *not* finished
      ret = strm_.end(&output);
      strInit_ = ret > 0;

      if (output.pos > 0) {
        if (sbuf_->sputn(reinterpret_cast<char*>(output.dst), output.pos) !=
            ssize_t(output.pos)) {
          return -1;
        }
      }
    }

    // Sync underlying stream as well
    sbuf_->pubsync();
    return 0;
  }

private:
  ssize_t compress(size_t pos) {
    if (!strInit_) {
      strm_.init(clevel_);
      strInit_ = true;
    }

    ZSTD_inBuffer input = {inbuf_.data(), pos, 0};
    while (input.pos != input.size) {
      ZSTD_outBuffer output = {outbuf_.data(), outbuf_.size(), 0};
      auto ret = strm_.compress(&output, &input);
      inhint_ = std::min(ret, inbuf_.size());

      if (output.pos > 0 &&
          sbuf_->sputn(reinterpret_cast<char*>(output.dst), output.pos) !=
              ssize_t(output.pos)) {
        return -1;
      }
    }

    return 0;
  }

  std::streambuf* sbuf_;
  CompressionLevel clevel_;
  cstream strm_;
  std::vector<char> inbuf_;
  std::vector<char> outbuf_;
  size_t inhint_;
  bool strInit_;
};

/**
 * stream buffer for decompression. If input data is not compressed, this
 * stream will simply copy it.
 */
class istreambuf : public std::streambuf {
public:
  explicit istreambuf(std::streambuf* sbuf) : sbuf_(sbuf) {
    inbuf_.resize(ZSTD_DStreamInSize());
    inhint_ = inbuf_.size();
    setg(inbuf_.data(), inbuf_.data(), inbuf_.data());
  }

  virtual std::streambuf::int_type underflow() {
    if (gptr() != egptr()) {
      return traits_type::eof();
    }

    while (true) {
      if (inpos_ >= inavail_) {
        inavail_ = sbuf_->sgetn(inbuf_.data(), inhint_);
        if (inavail_ == 0) {
          return traits_type::eof();
        }
        inpos_ = 0;
      }

      // Check whether data is actually compressed
      if (!detected_) {
        compressed_ = ZSTD_isFrame(inbuf_.data(), inavail_);
        detected_ = true;
        if (compressed_) {
          outbuf_.resize(ZSTD_DStreamOutSize());
        }
      }

      if (compressed_) {
        // Consume input
        ZSTD_inBuffer input = {inbuf_.data(), inavail_, inpos_};
        ZSTD_outBuffer output = {outbuf_.data(), outbuf_.size(), 0};
        auto ret = strm_.decompress(&output, &input);
        inhint_ = std::min(ret, inbuf_.size());
        inpos_ = input.pos;
        if (output.pos == 0 && inhint_ > 0 && inpos_ >= inavail_) {
          // Zstd did not decompress anything but requested more data
          continue;
        }
        setg(outbuf_.data(), outbuf_.data(), outbuf_.data() + output.pos);
      } else {
        // Re-use inbuf_ to avoid extra copy
        inpos_ = inavail_;
        setg(inbuf_.data(), inbuf_.data(), inbuf_.data() + inavail_);
      }

      break;
    }
    return traits_type::to_int_type(*gptr());
  }

private:
  std::streambuf* sbuf_;
  dstream strm_;
  std::vector<char> inbuf_;
  std::vector<char> outbuf_; // only needed if actually compressed
  size_t inhint_;
  size_t inpos_ = 0;
  size_t inavail_ = 0;
  bool detected_ = false;
  bool compressed_ = false;
};

// Input stream for compressed data
struct istream : public std::istream {
  istream(std::streambuf* sbuf) : std::istream(new istreambuf(sbuf)) {
    exceptions(std::ios_base::badbit);
  }

  virtual ~istream() {
    exceptions(std::ios_base::goodbit);
    if (rdbuf()) {
      delete rdbuf();
    }
  }
};

/**
 * Output stream for compressed data
 */
struct ostream : public std::ostream {
  ostream(std::streambuf* sbuf, CompressionLevel level = CompressionLevel::DEFAULT) : std::ostream(new ostreambuf(sbuf, level)) {
    exceptions(std::ios_base::badbit);
  }

  virtual ~ostream() {
    if (rdbuf()) {
      delete rdbuf();
    }
  }
};

/**
 * This class enables [io]fstream below to inherit from [io]stream (required for
 * setting a custom streambuf) while still constructing a corresponding
 * [io]fstream first (required for initializing the zip streambufs).
 */
template <typename T>
struct fsholder {
  explicit fsholder(const std::string& path, std::ios_base::openmode mode = std::ios_base::out) : fs_(path, mode) {}

protected:
  T fs_;
};

/**
 * Output file stream that writes compressed data
 */
struct ofstream : private fsholder<std::ofstream>, public std::ostream {
  explicit ofstream(const std::string& path, CompressionLevel level = CompressionLevel::DEFAULT, std::ios_base::openmode mode = std::ios_base::out) : fsholder<std::ofstream>(path, mode | std::ios_base::binary), std::ostream(new ostreambuf(fs_.rdbuf(), level)) {
    exceptions(std::ios_base::badbit);
  }

  virtual ~ofstream() {
    exceptions(std::ios_base::goodbit);
    if (rdbuf()) {
      delete rdbuf();
    }
  }

  virtual operator bool() const { return bool(fs_); }

  void close() {
    flush();
    fs_.close();
  }
};

/**
 * Input file stream for compressed data
 */
struct ifstream : private fsholder<std::ifstream>, public std::istream {
  explicit ifstream(const std::string& path, std::ios_base::openmode mode = std::ios_base::in) : fsholder<std::ifstream>(path, mode | std::ios_base::binary), std::istream(new istreambuf(fs_.rdbuf())) {
    exceptions(std::ios_base::badbit);
  }

  virtual ~ifstream() {
    exceptions(std::ios_base::goodbit);
    if (rdbuf()) {
      delete rdbuf();
    }
  }

  operator bool() const { return bool(fs_); }
  void close() { fs_.close(); }
};

std::shared_ptr<std::ostream> CreateFile(const std::string &file, CompressionLevel level) {
  return std::make_shared<ofstream>(file, level);
}

std::shared_ptr<std::istream> OpenFile(const std::string &file) {
  return std::make_shared<ifstream>(file);
}

} // namespace Zip::Stream
