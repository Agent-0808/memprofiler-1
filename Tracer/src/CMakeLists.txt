CMAKE_MINIMUM_REQUIRED(VERSION 3.8)

set(MEMORY_PROFILER_SRCS
    "${CMAKE_CURRENT_SOURCE_DIR}/main.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/config.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/config.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/debugger.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/target_loader.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/target_loader.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/trace_data.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/trace_data.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/tracer.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/tracer.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/utils.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/zip_stream.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/zip_stream.h"
)

# 查找 libdw 和 libelf 库
find_library(LIBDW_LIB dw REQUIRED)
find_library(LIBELF_LIB elf REQUIRED)
find_library(ZSTD_LIB zstd REQUIRED)

# 查找 libdw 和 libelf 头文件路径
find_path(LIBDW_INCLUDE_DIR NAMES libdwfl.h PATH_SUFFIXES elfutils REQUIRED)
find_path(LIBELF_INCLUDE_DIR NAMES libelf.h REQUIRED)
find_path(ZSTD_INCLUDE_DIR NAMES zstd.h REQUIRED)

add_executable(mprofiler ${MEMORY_PROFILER_SRCS})

# 包含头文件路径
target_include_directories(mprofiler PRIVATE
    ${LIBDW_INCLUDE_DIR}
    ${LIBELF_INCLUDE_DIR}
    ${ZSTD_INCLUDE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_SOURCE_DIR}/include
)

# 链接库到可执行文件
target_link_libraries(mprofiler
    ${LIBDW_LIB}
    ${LIBELF_LIB}
    ${ZSTD_LIB}
    unwind-ptrace
    unwind-generic
)
