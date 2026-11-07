// GPU replacement for source/egg/core/Decomp.cc (transform.py copies it over xsrc/source/egg/core/Decomp.cu).
// Decompressing a multi-MB Yaz0 archive on one GPU thread could run past the Windows GPU watchdog (TDR, ~2 s), so the
// host decompresses every uploaded file in advance and DecodeSZS copies the matching result into the same heap buffer
// the CPU build would have filled. The heap layout and contents stay identical to the CPU build.
#include "Decomp.hh"

struct KinokoFile {
    const char *path;
    const unsigned char *data;
    size_t size;
    const unsigned char *expanded;  // host-decompressed Yaz0 payload, or nullptr
    size_t expandedSize;
};

extern __device__ KinokoFile g_kinokoFiles[16];
extern __device__ int g_kinokoFileCount;

namespace Kinoko::EGG::Decomp {

s32 GetExpandSize(const u8 *src) {
    if (src[0] == 'Y' && src[1] == 'a' && src[2] == 'z') {
        return static_cast<s32>(u32(src[4]) << 24 | u32(src[5]) << 16 | u32(src[6]) << 8 | u32(src[7]));
    }
    return -1;
}

s32 DecodeSZS(const u8 *src, u8 *dst) {
    for (int i = 0; i < g_kinokoFileCount; ++i) {
        const KinokoFile &f = g_kinokoFiles[i];
        if (!f.expanded || memcmp(f.data, src, f.size < 4096 ? f.size : 4096) != 0) {
            continue;
        }
        memcpy(dst, f.expanded, f.expandedSize);
        return static_cast<s32>(f.expandedSize);
    }
    printf("GPU: DecodeSZS on data that matches no uploaded file\n");
    __trap();
    return -1;
}

} // namespace Kinoko::EGG::Decomp
