CMAKE_MINIMUM_REQUIRED(VERSION 3.8)

# 基础测试用例
set(TEST_CASE_SRCS
    "${CMAKE_CURRENT_SOURCE_DIR}/test_case.cpp"
)
add_executable(test_case ${TEST_CASE_SRCS})
target_compile_options(test_case PRIVATE -g)

# C++ new 测试用例
set(TEST_CPP_SRCS
    "${CMAKE_CURRENT_SOURCE_DIR}/test_cpp.cpp"
)
add_executable(test_cpp ${TEST_CPP_SRCS})
target_compile_options(test_cpp PRIVATE -g)

# 测试多种分配函数的测试用例
set(TEST_ALLOCS_SRCS
    "${CMAKE_CURRENT_SOURCE_DIR}/test_allocs.cpp"
)
add_executable(test_allocs ${TEST_ALLOCS_SRCS})
target_compile_options(test_allocs PRIVATE -g)

# 测试大量的MALLOC与FREE操作
set(TEST_MALLOCANDFREE_SRCS
    "${CMAKE_CURRENT_SOURCE_DIR}/test_mallocandfree.c"
)
add_executable(test_mallocandfree ${TEST_MALLOCANDFREE_SRCS})
target_compile_options(test_mallocandfree PRIVATE -g)

# mallocandfree的C++版本，使用new和delete
set(TEST_CPP_NEWANDDELETE_SRCS
    "${CMAKE_CURRENT_SOURCE_DIR}/test_cpp_newanddelete.cpp"
)
add_executable(test_cpp_newanddelete ${TEST_CPP_NEWANDDELETE_SRCS})
target_compile_options(test_cpp_newanddelete PRIVATE -g)

# 测试多线程
set(TEST_THREADS_SRCS
    "${CMAKE_CURRENT_SOURCE_DIR}/test_threads.c"
)
add_executable(test_threads ${TEST_THREADS_SRCS})
target_compile_options(test_threads PRIVATE -g)

# 测试多文件
set(TEST_PROJECT_SRCS
    "${CMAKE_CURRENT_SOURCE_DIR}/test_project_child.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/test_project_parent.h"
)
add_executable(test_project ${TEST_PROJECT_SRCS})
target_compile_options(test_project PRIVATE -g)

# 测试 clone/clone3/execve 系统调用
set(TEST_CLONE_SRCS
    "${CMAKE_CURRENT_SOURCE_DIR}/test_clone.cpp"
)
add_executable(test_clone ${TEST_CLONE_SRCS})
target_compile_options(test_clone PRIVATE -g)
