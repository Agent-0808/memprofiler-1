/*
Copyright (c) 2026, Chen Jie, Joungtao, Xuzheng Jiang
All rights reserved.
This source code is licensed under the BSD-2-Clause license found in the
LICENSE file in the root directory of this source tree.
*/

#include "tracer.h"

int main(int argc, char *argv[]) {
  Memory::Profile::Tracer tracer;
  return tracer.run(argc, argv);
}
