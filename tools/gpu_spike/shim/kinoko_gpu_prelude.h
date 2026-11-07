#pragma once
// Included first in every GPU translation unit: libc pieces the engine uses that NVRTC does not provide.
#include <cuda/std/cstddef>
#include <cuda/std/cstdint>
using size_t = ::cuda::std::size_t;
[[noreturn]] inline void abort() { __trap(); }
inline long double asinl(long double x) { return asin((double)x); }
inline long double acosl(long double x) { return acos((double)x); }
#include <compare>
// stdio as used by Logger.hh macros: device printf exists, the rest are no-ops.
struct FILE;
#define stdout ((FILE *)nullptr)
#define stderr ((FILE *)nullptr)
inline int fflush(FILE *) { return 0; }
// fprintf captures its arguments (as doubles) instead of formatting them: device printf allows at most 32 arguments,
// and the host compares/uses the values anyway. Each thread captures into its own buffer (runtime.cu): [0] = count,
// values from [1]. runtime.cu k_rows uses this to run host/FrameState.cc for every race at once.
extern "C" double *kinoko_capture_buffer();
#define KINOKO_CAPTURE_DOUBLES 128
template <class T> inline void kinoko_capture(T v) {
    double *b = kinoko_capture_buffer();
    int n = (int)b[0];
    if (n < KINOKO_CAPTURE_DOUBLES - 8) { b[1 + n] = (double)v; b[0] = n + 1; }
}
inline void kinoko_capture(const char *) {}
template <class... A> inline int fprintf(FILE *, const char *, A... a) { (kinoko_capture(a), ...); return 0; }
inline int fputs(const char *, FILE *) { return 0; }
// string.h pieces used by archive/ghost/object code
inline int strcmp(const char *a, const char *b) { while (*a && *a == *b) { ++a; ++b; } return (unsigned char)*a - (unsigned char)*b; }
inline int strncmp(const char *a, const char *b, size_t n) { for (; n; --n, ++a, ++b) { if (*a != *b || !*a) return (unsigned char)*a - (unsigned char)*b; } return 0; }
inline int memcmp(const void *a, const void *b, size_t n) { const unsigned char *x = (const unsigned char *)a, *y = (const unsigned char *)b; for (; n; --n, ++x, ++y) if (*x != *y) return *x - *y; return 0; }
inline size_t strlen(const char *s) { size_t n = 0; while (s[n]) ++n; return n; }
inline char *strncpy(char *d, const char *s, size_t n) { size_t i = 0; for (; i < n && s[i]; ++i) d[i] = s[i]; for (; i < n; ++i) d[i] = 0; return d; }
// Minimal snprintf for the engine's path building: %s %c %d %u %%.
struct KinokoFmtOut {
    char *buf; size_t n, len = 0;
    void put(char c) { if (len + 1 < n) buf[len] = c; ++len; }
    void str(const char *s) { while (*s) put(*s++); }
    void num(long long v) { if (v < 0) { put('-'); v = -v; } char t[24]; int k = 0; do { t[k++] = char('0' + v % 10); v /= 10; } while (v); while (k) put(t[--k]); }
};
inline void kinoko_fmt_arg(KinokoFmtOut &o, char spec, const char *s) { if (spec == 's') o.str(s ? s : "(null)"); }
inline void kinoko_fmt_arg(KinokoFmtOut &o, char spec, char *s) { kinoko_fmt_arg(o, spec, (const char *)s); }
template <class T> inline void kinoko_fmt_arg(KinokoFmtOut &o, char spec, T v) { if (spec == 'c') o.put((char)v); else o.num((long long)v); }
inline void kinoko_fmt(KinokoFmtOut &o, const char *f) { for (; *f; ++f) { if (*f == '%' && f[1] == '%') { o.put('%'); ++f; } else o.put(*f); } }
template <class T, class... A> inline void kinoko_fmt(KinokoFmtOut &o, const char *f, T v, A... rest) {
    for (; *f; ++f) {
        if (*f != '%') { o.put(*f); continue; }
        ++f;
        if (*f == '%') { o.put('%'); continue; }
        while (*f == 'l' || *f == 'z' || *f == 'h') ++f;
        kinoko_fmt_arg(o, *f, v);
        kinoko_fmt(o, f + 1, rest...);
        return;
    }
}
template <class... A> inline int snprintf(char *buf, size_t n, const char *f, A... a) {
    KinokoFmtOut o{buf, n};
    kinoko_fmt(o, f, a...);
    if (n) buf[o.len < n ? o.len : n - 1] = 0;
    return (int)o.len;
}
// Per-race statics (see transform.py rewrite_statics): each mutable static lives in a slot of the calling race's
// statics block, which the runtime places right after the race's private heap region.
#define KINOKO_STATIC_SLOT 128
extern "C" char *kinoko_race_statics();
extern "C" void kinoko_statics_init();
