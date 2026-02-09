#include <cstdlib>
#include <iostream>
#include <sys/wait.h>
#include <unistd.h>

void test_fork() {
  std::cout << "\n=== fork() test ===" << std::endl;
  pid_t fork_pid = fork();
  if (fork_pid == 0) {
    std::cout << "Child (fork): My PID is " << getpid() << std::endl;
    _exit(0);
  } else {
    waitpid(fork_pid, nullptr, 0);
    std::cout << "Parent: fork() child " << fork_pid << " exited\n";
  }
  sleep(1);
}

void test_vfork() {
  std::cout << "\n=== vfork() test ===" << std::endl;
  pid_t vfork_pid = vfork();
  if (vfork_pid == 0) {
    std::cout << "Child (vfork): Executing ls command" << std::endl;
    execlp("ls", "ls", "-l", nullptr);
    _exit(EXIT_FAILURE);
  }
  sleep(1);
}

void test_system() {
  std::cout << "\n=== system() test ===" << std::endl;
  int ret = system("echo 'Hello from system()'");
  std::cout << "system() return code: " << WEXITSTATUS(ret) << std::endl;
  sleep(1);
}

void test_execve() {
  std::cout << "\n=== execve() test ===" << std::endl;
  pid_t exec_pid = fork();
  if (exec_pid == 0) {
    char *argv[] = {nullptr};
    char *envp[] = {nullptr};
    execve("/bin/date", argv, envp);
    std::cerr << "execve failed" << std::endl;
    _exit(EXIT_FAILURE);
  } else {
    waitpid(exec_pid, nullptr, 0);
  }
  sleep(1);
}

void test_pthread() {
  auto thread_func = [](void *arg) -> void * {
    sleep(1);
    std::cout << "Thread (pthread_create): My TID is " << gettid() << std::endl;
    return nullptr;
  };
  std::cout << "\n=== pthread_create() test ===" << std::endl;
  pthread_t tid;
  pthread_create(&tid, nullptr, thread_func, nullptr);
  pthread_join(tid, nullptr);
  std::cout << "Thread joined successfully" << std::endl;
  sleep(1);
}

int main() {

  test_fork();
  test_vfork();
  test_system();
  test_execve();
  test_pthread();

  std::cout << "\nAll tests completed!" << std::endl;
  return 0;
}
