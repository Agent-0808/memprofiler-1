#include <iostream>
#include <unistd.h>

int main() {
  int *p = nullptr; // Declare a pointer to an int
  sleep(5);

  // Use new to allocate memory for an integer initialized to 10
  p = new int(10);

  // Print the value stored at the allocated memory
  std::cout << "The value at p is: " << *p << std::endl;
  std::cout << "The malloc at p is: " << (void *)malloc << std::endl;

  // Use delete to free the allocated memory
  sleep(10);
  delete p;

  return 0;
}
