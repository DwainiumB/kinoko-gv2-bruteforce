// GPU replacement for source/abstract/File.cc (transform.py copies it over xsrc/source/abstract/File.cu).
// The host uploads the game files the race needs into device memory and fills g_kinokoFiles; Load() copies a file into
// the game heap exactly like the CPU version does, so the heap layout matches the CPU build.
#include "File.hh"

#include <egg/core/Heap.hh>

struct KinokoFile {
    const char *path;  // e.g. "Race/Common.szs" (no leading slash)
    const unsigned char *data;
    size_t size;
    const unsigned char *expanded;  // host-decompressed Yaz0 payload (used by Decomp_gpu.cu), or nullptr
    size_t expandedSize;
};

__device__ KinokoFile g_kinokoFiles[16];
__device__ int g_kinokoFileCount;

namespace Kinoko::Abstract::File {

u8 *Load(const char *path, size_t &size) {
    if (path[0] == '/') {
        path++;
    }
    for (int i = 0; i < g_kinokoFileCount; ++i) {
        if (strcmp(g_kinokoFiles[i].path, path) == 0) {
            size = g_kinokoFiles[i].size;
            u8 *buffer = static_cast<u8 *>(EGG::egg_alloc(size, 4));
            memcpy(buffer, g_kinokoFiles[i].data, size);
            return buffer;
        }
    }
    printf("GPU: file not uploaded: %s\n", path);
    __trap();
    return nullptr;
}

u8 *LoadHost(const char *, size_t &size) {
    size = 0;
    __trap();
    return nullptr;
}

void Append(const char *, const char *, size_t) {}

int Remove(const char *) {
    return 0;
}

} // namespace Kinoko::Abstract::File
