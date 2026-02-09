#include <cstdlib>

// 随机分配模式设置
#define MAX_SIZE 1024
#define ALLOC_TIMES 1000
#define FREE_EVERY_X 7

int main() {
  // 初始种子
  srand(0x808);
  char *ptr[ALLOC_TIMES] = {0};

  // 分配前一半内容
  for (int i = 0; i < ALLOC_TIMES; i += 2) {
    size_t size = (i % 128) + 1;
    ptr[i] = new char[size];
  }

  // 随机释放并分配后一半内容
  for (int i = 1; i < ALLOC_TIMES; i += 2) {
    size_t size = (rand() % MAX_SIZE) + 1;
    if (i % FREE_EVERY_X == 0 && ptr[i - 1]) {
      // 模拟部分释放
      delete ptr[i - 1];
    }
    ptr[i] = new char[size];
  }

  return 0;
}