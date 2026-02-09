#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <vector>

char *allocate_long_lived_buffer(int iteration) {
  size_t size = 8192 + (iteration % 5) * 128;
  char *buffer = (char *)malloc(size);
  if (buffer) {
    buffer[0] = 'L';
    buffer[size - 1] = 'L';
  }
  return buffer;
}

char *allocate_short_lived_buffer(int iteration) {
  size_t size = 1024 + (iteration % 10) * 64;
  char *buffer = (char *)malloc(size);
  if (buffer) {
    buffer[0] = 'S';
    buffer[size - 1] = 'S';
  }
  return buffer;
}

void process_tasks_with_fragmentation() {
  const int NUM_TASKS = 100;
  std::vector<char *> long_lived_storage;
  std::vector<char *> short_lived_storage;

  for (int i = 0; i < NUM_TASKS; ++i) {
    // 分配长生命周期对象
    long_lived_storage.push_back(allocate_long_lived_buffer(i));
    // 分配短生命周期对象
    short_lived_storage.push_back(allocate_short_lived_buffer(i));
  }

  for (char *ptr : short_lived_storage) {
    free(ptr);
  }
  short_lived_storage.clear();


  // 碎片产生时刻
  std::vector<char *> large_alloc;
  for (int t = 0; t < 8; t++) {
    large_alloc.push_back((char *)malloc(8192));
  }

  // 业务结束，清理所有长生命周期的对象
  for (char *ptr : long_lived_storage) {
    free(ptr);
  }
  for (char *ptr : large_alloc) {
    free(ptr);
  }
  long_lived_storage.clear();
  large_alloc.clear();
}

int main() {
  // 调用包含问题代码的函数
  process_tasks_with_fragmentation();
  return 0;
}
