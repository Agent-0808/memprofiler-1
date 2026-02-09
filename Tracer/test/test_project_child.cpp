#include "test_project_parent.h"

void child_func() {
  cout << "..." << endl << "...child func: " << endl << "..." << endl;
  int *a = new int;
  *a = 890;
  delete a;
}

int main() {
  cout << "..." << endl << "...MAIN..." << endl << "..." << endl;
  child_func();
  int *t = new int;

  cout << "..." << endl << "...invoking parent_main" << endl << "..." << endl;
  *t = parent_main();
  cout << "..." << endl
       << "...parent_main returned: " << endl
       << "..." << t << endl;
  delete t;

  return 0;
}