#include "tracer.h"

int main(int argc, char *argv[]) {
  Memory::Profile::Tracer tracer;
  return tracer.run(argc, argv);
}
