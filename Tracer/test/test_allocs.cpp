#include <cstdio>
#include <cstdlib>
#include <unistd.h>
void f_malloc() {
  printf("....\n....malloc....\n....\n");
  auto p = (int *)malloc(sizeof(int));
  *p = 30;
  free(p);
}
void f_calloc() {
  printf("....\n....calloc....\n....\n");
  auto p = (int *)calloc(20, sizeof(int));
  p[0] = 100;
  p[19] = 30;
  free(p);
}
void f_realloc() {
  printf("....\n....realloc....\n....\n");
  auto p = (int *)realloc(nullptr, 4 * sizeof(int));
  p[3] = 100;
  p = (int *)realloc(p, 64 * sizeof(int));
  p[19] = 30;
  realloc(p, 0);
}

void f_valloc() {
  printf("....\n....valloc....\n....\n");
  size_t size = 100; // 分配的内存大小，以页面为单位
  void *p = valloc(size);
  ((char *)p)[0] = 1;
  ((char *)p)[size - 1] = 2;
  free(p);
}
void f_posix_memalign() {
  printf("....\n....posix_memalign....\n....\n");
  size_t alignment = 16; // 假设我们希望以16字节对齐
  size_t size = 100;
  char *p;
  int ret = posix_memalign((void **)&p, alignment, size);
  if (ret) {
    printf("ERROR: posix_memalign failed, code = %d", ret);
    return;
  }
  p[0] = 1;
  p[size - 1] = 2;

  printf("\nposix_memalign &p: %p\n", &p);
  printf("p: %p, *p: %d\n\n", p, *p);
  free(p);
}

void f_aligned_alloc() {
  printf("....\n....aligned_alloc....\n....\n");
  size_t alignment = 16; // 假设我们希望以16字节对齐
  size_t size = 100;
  int *p = (int *)aligned_alloc(alignment, size);
  p[0] = 1;
  p[size - 1] = 2;
  free(p);
}

void f_new() {
  printf("....\n....new....\n....\n");
  int *p = new int;
  *p = 50;
  delete p;
}
void f_new_array() {
  printf("....\n....new_array....\n....\n");
  int *p = new int[80];
  p[0] = 50;
  p[79] = 21;
  delete[] p;
}

void f_sbrk() {
  printf("....\n....sbrk....\n....\n");

  // 使用 sbrk 系统调用查询当前堆地址
  int *p = (int *)sbrk(0);
  // 记录该堆内存地址
  int *p_old = p;

  // 申请 1024 字节内存
  p = (int *)sbrk(1024);

  // 打印进程 ID , PID
  printf("pid : %d\n", getpid());
  // 打印申请的堆内存地址, 发现地址没有变化
  printf("p_old : %p \np     : %p \n", p_old, p);

  // 申请新的堆内存
  int *p_new = (int *)sbrk(0);
  // 打印新的堆内存地址
  printf("p_new : %p\n", p_new);
}
void f_test() {
  printf("....\n....start....\n....\n");
  f_malloc();
  f_calloc();
  f_realloc();

  f_valloc();
  f_posix_memalign();
  f_aligned_alloc();

  f_new();
  f_new_array();
  f_sbrk();

  printf("....\n....end....\n....\n");
}

int main(int argc, char *argv[]) {
  printf("test case %d %p\n", argc, argv);

  f_test();

  return 0;
}
