#include <iostream>
using namespace std;

int *parent_func_new() {
  cout << "..." << endl << "...parent func new: " << endl << "..." << endl;
  int *vec = new int[6];
  vec[0] = 10;
  vec[5] = 808;
  return vec;
}

void parent_func_delete(int *vec) { delete[] vec; }

int parent_main() {
  cout << "..." << endl << "...parent main " << endl << "..." << endl;
  int *VEC = parent_func_new(); // 获取新分配的内存地址
  int ret = VEC[5];             // 使用VEC
  parent_func_delete(VEC);      // 释放内存

  return ret;
}