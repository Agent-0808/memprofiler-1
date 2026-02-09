#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>


#define NUM_THREADS 5
#define ALLOC_SIZE 1024 // 每个线程分配的内存大小

// 线程函数
void *thread_function(void *arg) {
  int thread_num = *(int *)arg;         // 获取线程编号
  pid_t pid = getpid();                 // 获取当前进程ID
  pthread_t thread_id = pthread_self(); // 获取当前线程ID

  // 动态分配内存
  char *buffer = (char *)malloc(ALLOC_SIZE);
  if (buffer == NULL) {
    perror("malloc failed");
    pthread_exit(NULL);
  }

  // 模拟对内存的操作
  printf("Thread %d (PID: %d, TID: %lu): Memory allocated at %p\n", thread_num,
         pid, (unsigned long)thread_id, buffer);
  sleep(1); // 模拟一些工作

  // 释放内存
  free(buffer);
  printf("Thread %d (PID: %d, TID: %lu): Memory freed at %p\n", thread_num, pid,
         (unsigned long)thread_id, buffer);

  pthread_exit(NULL);
}

int main() {
  pthread_t threads[NUM_THREADS];
  int thread_args[NUM_THREADS];
  int i;

  // 创建多个线程
  for (i = 0; i < NUM_THREADS; i++) {
    thread_args[i] = i;
    if (pthread_create(&threads[i], NULL, thread_function,
                       (void *)&thread_args[i]) != 0) {
      perror("pthread_create failed");
      return 1;
    }
    sleep(10);
  }

  // 等待所有线程结束
  for (i = 0; i < NUM_THREADS; i++) {
    pthread_join(threads[i], NULL);
  }

  printf("All threads finished.\n");
  return 0;
}
