#include "tracer.h"

using namespace Memory::Profile;
using namespace std;
int main() {

  Config config;
  TraceData2 data;
  TraceMap trace_map;

  string filename = config.save_binary_filename;
  // 从文件中加载解压缩数据
  SerializedData loaded_data;
  loaded_data.initdctx();
  loaded_data.loadDecompress(filename);

  cout << "Loading from" << filename << endl;
  // 反序列化
  TraceData2 loaded_tracedata(loaded_data);

  std::cout << "Loaded from " << filename << std::endl;

  cout << "loaded_tracedata[0]: " << endl;
  SerializedData(loaded_tracedata[0]).print();

  trace_map.loadFileMapFrom(config.fileIndexMap_filename);
  trace_map.loadFuncMapFrom(config.funcIndexMap_filename);

  if (loaded_tracedata.size() <= 1000)
    loaded_tracedata.printDataAndStack(trace_map);
  return 0;
}
