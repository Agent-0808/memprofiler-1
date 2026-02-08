#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>
#include <unistd.h>

#define NUM_THREADS 2
#define ALLOC_SIZE 1024  // 每个线程分配的内存大小

// 子线程函数
void* child_thread_function(void* arg) {
    int parent_thread_num = *(int*)arg;  // 获取父线程编号
    pid_t pid = getpid();                // 获取当前进程ID
    pthread_t thread_id = pthread_self();  // 获取当前子线程ID

    printf("Child thread of parent thread %d (PID: %d, TID: %lu)\n",
           parent_thread_num, pid, (unsigned long)thread_id);

    sleep(1);  // 模拟一些工作
    pthread_exit(NULL);
}

// 父线程函数
void* parent_thread_function(void* arg) {
    int thread_num = *(int*)arg;  // 获取线程编号
    pid_t pid = getpid();         // 获取当前进程ID
    pthread_t thread_id = pthread_self();  // 获取当前线程ID

    // 动态分配内存
    char* buffer = (char*)malloc(ALLOC_SIZE);
    if (buffer == NULL) {
        perror("malloc failed");
        pthread_exit(NULL);
    }

    printf("Parent thread %d (PID: %d, TID: %lu): Memory allocated at %p\n",
           thread_num, pid, (unsigned long)thread_id, buffer);

    // 创建一个子线程
    pthread_t child_thread;
    if (pthread_create(&child_thread, NULL, child_thread_function, (void*)&thread_num) != 0) {
        perror("pthread_create failed for child thread");
        free(buffer);
        pthread_exit(NULL);
    }

    // 等待子线程结束
    pthread_join(child_thread, NULL);

    // 释放内存
    free(buffer);
    printf("Parent thread %d (PID: %d, TID: %lu): Memory freed at %p\n",
           thread_num, pid, (unsigned long)thread_id, buffer);

    pthread_exit(NULL);
}

int main() {
    pthread_t threads[NUM_THREADS];
    int thread_args[NUM_THREADS];
    int i;

    // 创建多个父线程
    for (i = 0; i < NUM_THREADS; i++) {
        thread_args[i] = i;
        if (pthread_create(&threads[i], NULL, parent_thread_function, (void*)&thread_args[i]) != 0) {
            perror("pthread_create failed");
            return 1;
        }
    }

    // 等待所有父线程结束
    for (i = 0; i < NUM_THREADS; i++) {
        pthread_join(threads[i], NULL);
    }

    printf("All parent threads finished.\n");
    return 0;
}
