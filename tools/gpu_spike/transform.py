"""Copy source/ and include/ to tools/gpu_spike/xsrc with the C++23 -> C++20 rewrites NVRTC needs.

NVRTC accepts at most C++20 and no GNU extensions. The rewrites are mechanical, and each one is counted so the spike
can report how much of the code needed them (a real port would make the same edits in the tree itself):
  - multi-index subscripts  m[r, c]  ->  m(r, c)  (and the operator[] declarations -> operator())
  - GNU case ranges  case E::A... E::B:  ->  the enumerators in between
  - static constexpr locals inside functions -> constexpr locals (static locals in constexpr functions are C++23)

    python tools/gpu_spike/transform.py
"""

import collections
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import statics_rewrite  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(os.path.dirname(__file__), "xsrc")

COUNTS = collections.Counter()

SUBSCRIPT = re.compile(r'(\b[A-Za-z_][\w]*(?:(?:\.|->)[A-Za-z_]\w*)*(?:\(\))?)\[([\w]+), *([\w]+)\]')
OPDECL = re.compile(r'operator\[\]\((size_t \w+, size_t \w+)\)')
CASERANGE = re.compile(r'case (\w+)::(\w+)\s*\.\.\.\s*\1::(\w+):')
STATIC_LOCAL = re.compile(r'^(\s{4,})static constexpr ', re.M)


def enum_members(text):
    members = {}
    for m in re.finditer(r'enum class (\w+)[^{]*\{(.*?)\};', text, re.S):
        names = re.findall(r'^\s*(\w+)\s*(?:=|,)', m.group(2), re.M)
        members[m.group(1)] = names
    return members


def rewrite(path, text, enums):
    def sub_subscript(m):
        if m.group(1) in ("auto",):
            return m.group(0)
        COUNTS["multi-index subscript"] += 1
        return f"{m.group(1)}({m.group(2)}, {m.group(3)})"

    out_lines = []
    for line in text.split("\n"):
        code, sep, comment = line.partition("//")
        code2 = OPDECL.sub(lambda m: (COUNTS.update(["operator[] decl"]), f"operator()({m.group(1)})")[1], code)
        code2 = SUBSCRIPT.sub(sub_subscript, code2)
        out_lines.append(code2 + sep + comment)
    text = "\n".join(out_lines)

    def sub_case(m):
        names = enums.get(m.group(1))
        a, b = names.index(m.group(2)), names.index(m.group(3))
        COUNTS["GNU case range"] += 1
        return " ".join(f"case {m.group(1)}::{n}:" for n in names[a:b + 1])

    text = CASERANGE.sub(sub_case, text)

    # constexpr defaulted ctor over a union with an uninitialized member: EDG rejects it in C++20 mode
    if path.endswith("Matrix.hh"):
        COUNTS["constexpr defaulted ctor"] += text.count("constexpr Matrix34f() = default;")
        text = text.replace("constexpr Matrix34f() = default;", "Matrix34f() = default;")

    # function-scope statics with dynamic initialization (not allowed in device code)
    def sub_static_span(m):
        COUNTS["dynamic-init static local"] += 1
        return "return {};"
    text = re.sub(r'static owning_span<\w+> (\w+);\s*return \1\.view\(\);', sub_static_span, text)

    # 64-bit alignment: the heap rounds block sizes to 4 and defaults to 4-byte alignment (fine on the 32-bit Wii, and
    # x86 tolerates the misaligned pointers that result), but GPU loads/stores must be naturally aligned.
    if path.replace("\\", "/").endswith("abstract/memory/ExpHeap.cc"):
        old = "    size = RoundUp(size, 4);\n"
        assert old in text
        text = text.replace(old, "    size = RoundUp(size, 8);  // GPU: was 4\n"
                                 "    if (align >= 0 && align < 8) align = 8;  // GPU: minimum alignment 8\n"
                                 "    if (align < 0 && align > -8) align = -8;\n")
        COUNTS["heap alignment 8"] += 1

    # flexible array members (GNU extension): T name[];  ->  T name[1];  and the sizeof check of that struct drops it
    def sub_flex(m):
        COUNTS["flexible array member"] += 1
        return f"{m.group(1)}{m.group(2)} {m.group(3)}[1]; // GPU spike: was a flexible array member"
    text = re.sub(r'^(\s+)([A-Za-z_:<>0-9 ]+?) (\w+)\[\];', sub_flex, text, flags=re.M)
    if "was a flexible array member" in text:
        text = re.sub(r'STATIC_ASSERT\(sizeof\(\w+\) == 0x[0-9a-fA-F]+\);', '', text)

    # static constexpr locals inside *constexpr* functions (a C++23 feature) lose the `static`. Only there: in an
    # ordinary function the static must stay, because code keeps pointers to such tables (e.g. KartMove's
    # TURNING_PARAMS_ARRAY via m_turningParams); a non-static copy lives on the stack and the pointer dangles.
    lines = text.split("\n")
    func_open = re.compile(r'\)\s*(const)?\s*(noexcept)?\s*(override)?\s*\{\s*$')
    stack = []
    for i, line in enumerate(lines):
        code = line.split("//")[0]
        stripped = code.strip()
        if stack and stack[-1] == "cfunc" and stripped.startswith("static constexpr "):
            lines[i] = line.replace("static constexpr ", "constexpr ", 1)
            COUNTS["static constexpr local (in constexpr fn)"] += 1
        for ch in code:
            if ch == "{":
                if stack and stack[-1] in ("func", "cfunc"):
                    kind = stack[-1]
                elif func_open.search(code):
                    kind = "cfunc" if re.search(r'\bconstexpr\b', code) else "func"
                else:
                    kind = "other"
                stack.append(kind)
            elif ch == "}":
                if stack:
                    stack.pop()
    text = "\n".join(lines)
    # include guards instead of #pragma once: the unity build reaches some headers through differently spelled paths
    # (and some headers, e.g. ObjectTownBridge.hh, have no guard at all)
    if path.endswith((".hh", ".h")):
        guard = "KINOKO_GUARD_" + re.sub(r'\W', '_', os.path.relpath(path, ROOT)).upper()
        text = f"#ifndef {guard}\n#define {guard}\n" + text.replace("#pragma once", "", 1) + f"\n#endif // {guard}\n"
        COUNTS["include guard"] += 1
    if "/source/host/" not in path.replace("\\", "/"):
        text = statics_rewrite.rewrite(path, text)
    return text


def write_if_changed(path, text):
    """Leave unchanged files alone so build_gpu.py's per-unit cache (by mtime) only recompiles what changed."""
    if os.path.exists(path) and open(path, encoding="utf-8").read() == text:
        return
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def main():
    common = open(os.path.join(ROOT, "include", "Common.hh"), encoding="utf-8").read()
    enums = enum_members(common)
    nfiles = 0
    for top in ("source", "include"):
        for dirpath, _, files in os.walk(os.path.join(ROOT, top)):
            for f in files:
                if not f.endswith((".cc", ".hh", ".h")):
                    continue
                src = os.path.join(dirpath, f)
                # .cc -> .cu: CMakeLists globs **/*.cc over the whole repo, so the copy must not contain any .cc files
                dst = os.path.join(OUT, os.path.relpath(src, ROOT))
                if dst.endswith(".cc"):
                    dst = dst[:-3] + ".cu"
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                text = open(src, encoding="utf-8").read()
                new = rewrite(src, text, enums)
                if new != text:
                    nfiles += 1
                write_if_changed(dst, new)
    # device file loader replaces the std::ifstream one
    for name, dst in (("File_gpu.cu", "source/abstract/File.cu"), ("Decomp_gpu.cu", "source/egg/core/Decomp.cu")):
        write_if_changed(os.path.join(OUT, dst), open(os.path.join(os.path.dirname(__file__), name), encoding="utf-8").read())
    statics_rewrite.write_init(OUT)
    COUNTS.update(statics_rewrite.COUNTS)
    print(f"per-race statics: {len(statics_rewrite.DEFS)} definitions")
    print(f"rewrote {nfiles} files: " + ", ".join(f"{k}:{v}" for k, v in COUNTS.items()))


if __name__ == "__main__":
    main()
