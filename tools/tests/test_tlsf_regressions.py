"""Run real allocator boundaries, coalescing and data-preservation regressions."""

from datetime import datetime, timezone
import ast
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from project_materials import project_materials_root

SOURCE = ROOT / "lib/tlsf/src/tlsf.c"
HARNESS = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#ifdef _WIN32
#include <windows.h>
#endif
#include TLSF_SOURCE

static union { uint64_t alignment[2]; unsigned char bytes[262144]; } heap;

static int area_count(void)
{
    unsigned int count = 0;
    for (area_info_t *entry = ((tlsf_t *)heap.bytes)->area_head; entry; entry = entry->next)
        if (++count > 8)
            return -1;
    return count;
}

static int check_areas(const char *scenario)
{
    const size_t area_size = 65536;
    unsigned char *first = NULL, *second = NULL, *combined = NULL;
    bool alias = !strncmp(scenario, "alias-", 6);
    if (alias)
    {
#ifdef _WIN32
        if (sizeof(void *) != 8)
            return 77;
        for (uintptr_t index = 0; index < 16; ++index)
        {
            uintptr_t base = UINT64_C(0x200000000) + index * UINT64_C(0x1000000);
            unsigned char *lower = VirtualAlloc((void *)base, area_size * 2,
                MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
            if (!lower)
                continue;
            unsigned char *upper = VirtualAlloc((void *)(base + UINT64_C(0x100000000) + area_size),
                area_size * 2, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
            if (!upper)
            {
                VirtualFree(lower, 0, MEM_RELEASE);
                continue;
            }
            bool reverse = !strcmp(scenario, "alias-before");
            first = reverse ? upper : lower;
            second = reverse ? lower : upper;
            break;
        }
#else
        return 77;
#endif
        if (!first || !second)
            return 77;
        memset(first + area_size, 0xa5, area_size);
        memset(second + area_size, 0x5a, area_size);
    }
    else
    {
        combined = calloc(3, area_size);
        if (!combined)
            return 71;
        bool reverse = !strcmp(scenario, "contiguous-before");
        first = combined + (reverse ? area_size : 0);
        second = combined + (reverse ? 0 : area_size);
        memset(combined + area_size * 2, 0xa5, area_size);
    }
    printf("AREAS %p %p\n", (void *)first, (void *)second);
    fflush(stdout);
    add_new_area(first, area_size, heap.bytes);
    add_new_area(second, area_size, heap.bytes);
    if (area_count() != (alias ? 3 : 2))
        return 81;
    for (size_t offset = 0; offset < area_size; ++offset)
        if (alias ? (first[area_size + offset] != 0xa5 || second[area_size + offset] != 0x5a)
                  : combined[area_size * 2 + offset] != 0xa5)
            return 82;
    unsigned char *allocation = malloc_ex(100000, heap.bytes);
    if (!allocation)
        return 83;
    if (!alias && ((uintptr_t)allocation < (uintptr_t)combined ||
        (uintptr_t)allocation + 100000 > (uintptr_t)combined + area_size * 2))
        return 84;
    memset(allocation, 0x63, 100000);
    free_ex(allocation, heap.bytes);
    destroy_memory_pool(heap.bytes);
#ifdef _WIN32
    if (alias)
    {
        VirtualFree(first, 0, MEM_RELEASE);
        VirtualFree(second, 0, MEM_RELEASE);
    }
#endif
    free(combined);
    return 0;
}

static uint32_t random_value(uint32_t *state)
{
    *state = *state * UINT32_C(1664525) + UINT32_C(1013904223);
    return *state;
}

static int stress(uint32_t seed)
{
    struct allocation { unsigned char *pointer; size_t size; unsigned char value; } slots[32] = {{0}};
    for (unsigned int step = 0; step < 5000; ++step)
    {
        struct allocation *slot = &slots[(random_value(&seed) >> 16) % 32];
        unsigned int operation = random_value(&seed) % 4;
        if (slot->pointer)
        {
            for (size_t offset = 0; offset < slot->size; ++offset)
                if (slot->pointer[offset] != slot->value)
                    return 91;
            if (!operation)
            {
                free_ex(slot->pointer, heap.bytes);
                memset(slot, 0, sizeof(*slot));
            }
            else if (operation == 1)
            {
                size_t size = (random_value(&seed) >> 12) % 8192 + 1;
                unsigned char *replacement = realloc_ex(slot->pointer, size, heap.bytes);
                if (replacement)
                {
                    size_t preserved = size < slot->size ? size : slot->size;
                    for (size_t offset = 0; offset < preserved; ++offset)
                        if (replacement[offset] != slot->value)
                            return 92;
                    slot->pointer = replacement;
                    slot->size = size;
                    memset(replacement, slot->value, size);
                }
                else
                    for (size_t offset = 0; offset < slot->size; ++offset)
                        if (slot->pointer[offset] != slot->value)
                            return 93;
            }
        }
        else
        {
            size_t size = (random_value(&seed) >> 12) % 4096 + 1;
            slot->pointer = operation ? malloc_ex(size, heap.bytes) : calloc_ex(size, 1, heap.bytes);
            if (!slot->pointer)
                continue;
            if ((uintptr_t)slot->pointer & PTR_MASK)
                return 94;
            if (!operation)
                for (size_t offset = 0; offset < size; ++offset)
                    if (slot->pointer[offset])
                        return 95;
            slot->size = size;
            slot->value = (unsigned char)(step % 255 + 1);
            memset(slot->pointer, slot->value, size);
        }
    }
    for (unsigned int index = 0; index < 32; ++index)
    {
        for (size_t offset = 0; offset < slots[index].size; ++offset)
            if (slots[index].pointer[offset] != slots[index].value)
                return 96;
        free_ex(slots[index].pointer, heap.bytes);
    }
    void *large = malloc_ex(200000, heap.bytes);
    if (!large)
        return 97;
    free_ex(large, heap.bytes);
    free_ex(NULL, heap.bytes);
    return 0;
}

int main(int count, char **arguments)
{
#ifdef _WIN32
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX);
#endif
    if (count != 2 || init_memory_pool(sizeof(heap.bytes), heap.bytes) == (size_t)-1)
        return 70;
    printf("WIDTH %zu %zu\n", sizeof(size_t), sizeof(void *));
    fflush(stdout);
    const char *scenario = arguments[1];
    if (!strncmp(scenario, "stress-", 7))
        return stress((uint32_t)strtoul(scenario + 7, NULL, 10));
    if (!strncmp(scenario, "alias-", 6) || !strncmp(scenario, "contiguous-", 11))
        return check_areas(scenario);
    if (!strcmp(scenario, "calloc-overflow"))
    {
        if (calloc_ex(SIZE_MAX / 2 + 1, 2, heap.bytes) ||
            calloc_ex(SIZE_MAX / 2 + 2, 2, heap.bytes))
            return 101;
    }
    else if (!strcmp(scenario, "malloc-overflow"))
    {
        if (malloc_ex(SIZE_MAX, heap.bytes))
            return 102;
    }
    else if (!strcmp(scenario, "realloc-overflow"))
    {
        unsigned char *allocation = malloc_ex(32, heap.bytes);
        if (!allocation)
            return 71;
        memset(allocation, 0x5a, 32);
        if (realloc_ex(allocation, SIZE_MAX, heap.bytes))
            return 103;
        for (unsigned int index = 0; index < 32; ++index)
            if (allocation[index] != 0x5a)
                return 104;
        free_ex(allocation, heap.bytes);
    }
    else if (!strcmp(scenario, "class-boundary"))
    {
        size_t limit = ((size_t)1 << MAX_FLI) - ((size_t)1 << (MAX_FLI - MAX_LOG2_SLI - 1));
        const size_t sizes[] = {limit, limit + 1, ((size_t)1 << MAX_FLI) - 1,
                               (size_t)1 << MAX_FLI, SIZE_MAX - MEM_ALIGN, SIZE_MAX};
        for (unsigned int index = 0; index < sizeof(sizes) / sizeof(*sizes); ++index)
            if (malloc_ex(sizes[index], heap.bytes))
                return 105;
    }
    else if (!strcmp(scenario, "bit31"))
    {
        for (unsigned int bit = 0; bit < 32; ++bit)
            if (ls_bit((int)(UINT32_C(1) << bit)) != (int)bit)
                return 106;
    }
    else if (!strcmp(scenario, "alignment"))
    {
        for (size_t offset = 1; offset < sizeof(void *); ++offset)
            if (init_memory_pool(65536, heap.bytes + offset) != (size_t)-1)
                return 107;
        if (init_memory_pool(0, heap.bytes) != (size_t)-1 ||
            init_memory_pool(sizeof(heap.bytes), NULL) != (size_t)-1)
            return 108;
    }
    else
        return 72;
    puts("PASS REAL TLSF");
    return 0;
}
'''

CASES = ("calloc-overflow", "malloc-overflow", "realloc-overflow", "class-boundary", "bit31",
         "alignment", "stress-1", "stress-7", "stress-99", "contiguous-before", "contiguous-after")


def no_core_dump():
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


class TLSFRegressionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shlex.split(os.environ.get("CC", "cc"))
        if not shutil.which(cls.compiler[0]):
            raise unittest.SkipTest("C compiler unavailable")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
        cls.area = project_materials_root(ROOT) / "tlsf-regressions" / stamp
        cls.area.mkdir(parents=True)
        cls.original = SOURCE.read_bytes()
        cls.fixture = cls.area / "fixture.c"
        cls.fixture.write_text("#include <stdbool.h>\n" + HARNESS, encoding="utf-8")
        cls.records = []
        cls.positive = {}
        for mode, flags in (("ordinary", []), ("ubsan", ["-fsanitize=undefined", "-fno-sanitize-recover=all"])):
            cls.positive[mode] = cls.compile(mode, SOURCE, flags)

    @classmethod
    def compile(cls, name, source, flags=()):
        binary = cls.area / (name + (".exe" if os.name == "nt" else ".bin"))
        command = [*cls.compiler, "-std=gnu99", "-O1", "-Wall", "-Wextra", "-Werror", "-DHAVE_STDIO_H",
                   "-U_FORTIFY_SOURCE", "-I", str(ROOT / "lib/tlsf/src"), '-DTLSF_SOURCE="' + source.as_posix() + '"',
                   *flags, str(cls.fixture), "-o", str(binary)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        cls.records.append(dict(kind="compile", name=name, command=command, exit_code=result.returncode,
                                stdout=result.stdout, stderr=result.stderr, passed=result.returncode == 0))
        if result.returncode:
            raise AssertionError(result.stderr)
        return binary

    @classmethod
    def execute(cls, binary, scenario, expect_failure=False, prefix=()):
        command = [*prefix, str(binary), scenario]
        result = subprocess.run(command, capture_output=True, text=True, timeout=20,
            preexec_fn=no_core_dump if sys.platform == "linux" else None,
            **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
        passed = result.returncode not in (0, 77) if expect_failure else result.returncode == 0
        cls.records.append(dict(kind="run", command=command, exit_code=result.returncode,
                                stdout=result.stdout, stderr=result.stderr,
                                expected_failure=expect_failure, passed=passed))
        if not passed:
            raise AssertionError(str(command) + ": " + str(result.returncode) + "\n" + result.stderr)
        return result

    @classmethod
    def tearDownClass(cls):
        unchanged = SOURCE.read_bytes() == cls.original
        report = dict(passed=unchanged and all(item["passed"] for item in cls.records),
            source_unchanged=unchanged, source_sha256=hashlib.sha256(cls.original).hexdigest(),
            fixture_sha256=hashlib.sha256(cls.fixture.read_bytes()).hexdigest(), records=cls.records,
            platform=sys.platform, physical_hardware_tested=False)
        (cls.area / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("TLSF evidence:", cls.area, flush=True)

    def test_boundaries_alignment_data_and_both_contiguous_orders(self):
        for mode, binary in self.positive.items():
            for scenario in CASES:
                with self.subTest(mode=mode, scenario=scenario):
                    self.execute(binary, scenario)

    def test_engine_integration_freezes_the_actual_allocator_inputs(self):
        path = ROOT / "lib/espeak/tests/run_native_tests.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        definition = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                          and node.name == "integration_sources")
        namespace = {"ROOT": ROOT, "ESPEAK": ROOT / "lib/espeak"}
        exec(compile(ast.Module(body=[definition], type_ignores=[]), str(path), "exec"), namespace)
        sources = namespace["integration_sources"]()
        self.assertEqual(len(sources), len(set(sources)))
        for required in (SOURCE, ROOT / "lib/tlsf/src/tlsf.h",
                         ROOT / "tools/tests/test_espeak_native_runtime.py"):
            self.assertIn(required, sources)
        self.assertTrue(all(source.is_file() for source in sources))

    @unittest.skipUnless(os.name == "nt", "Win64 LLP64 address truncation requires native Windows")
    def test_distinct_upper_address_bits_never_merge(self):
        for mode, binary in self.positive.items():
            for scenario in ("alias-before", "alias-after"):
                with self.subTest(mode=mode, scenario=scenario):
                    self.execute(binary, scenario)

    def test_original_allocation_and_bitmap_defects_are_causally_rejected(self):
        mutations = (
            ("calloc", b" || nelem > SIZE_MAX / elem_size", b"", "calloc-overflow"),
            ("malloc", b"    if (size > MAX_REQUEST_SIZE)\n        return NULL;\n", b"", "malloc-overflow"),
            ("realloc", b"    if (new_size > MAX_REQUEST_SIZE)\n        return NULL;\n", b"", "realloc-overflow"),
            ("bitmap", b"(unsigned int)value & (0u - (unsigned int)value)", b"value & -value", "bit31"),
            ("sizeclass", b"#define MAX_REQUEST_SIZE (((size_t)1 << MAX_FLI) - ((size_t)1 << (MAX_FLI - MAX_LOG2_SLI - 1)))",
             b"#define MAX_REQUEST_SIZE ((size_t)1 << MAX_FLI)", "class-boundary"),
        )
        normalized = self.original.replace(b"\r\n", b"\n")
        for name, before, after, scenario in mutations:
            with self.subTest(mutation=name):
                self.assertEqual(normalized.count(before), 1)
                mutant = self.area / (name + "-mutant.c")
                mutant.write_bytes(normalized.replace(before, after))
                binary = self.compile(name + "-mutant", mutant, ["-fsanitize=undefined", "-fno-sanitize-recover=all"])
                self.execute(binary, scenario, expect_failure=True)

    @unittest.skipUnless(sys.platform == "linux", "Actual MIPS toolchain/QEMU execution uses WSL")
    def test_actual_32bit_mips_boundaries_and_allocator_regressions(self):
        sdk = project_materials_root(ROOT) / "toolchains/hiby-r1-20261010"
        compiler = sdk / "prefix/bin/mipsel-rockbox-linux-gnu-gcc"
        qemu = sdk / "host/usr/bin/qemu-mipsel-static"
        if not compiler.is_file() or not qemu.is_file():
            self.skipTest("Actual MIPS compiler and SDK QEMU unavailable")
        binary = self.area / "mips32-static.bin"
        command = [str(compiler), "-std=gnu99", "-O1", "-Wall", "-Wextra", "-Werror",
            "-DHAVE_STDIO_H", "-U_FORTIFY_SOURCE", "-mips32r2", "-mhard-float", "-static", "-I", str(ROOT / "lib/tlsf/src"),
            '-DTLSF_SOURCE="' + SOURCE.as_posix() + '"', str(self.fixture), "-o", str(binary)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.records.append(dict(kind="compile", name="actual-mips32", command=command,
            exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr, passed=result.returncode == 0))
        self.assertEqual(result.returncode, 0, result.stderr)
        for scenario in CASES:
            with self.subTest(scenario=scenario):
                executed = self.execute(binary, scenario, prefix=(str(qemu), "-cpu", "24Kf"))
                self.assertIn("WIDTH 4 4", executed.stdout)

    @unittest.skipUnless(os.name == "nt", "Original LLP64 adjacency mutation is Windows-specific")
    def test_original_adjacency_casts_are_causally_rejected(self):
        data = self.original
        for expression in (b"mem_pool", b"ib1", b"lb0", b"lb1->ptr.buffer", b"ib0"):
            before = b"(uintptr_t) " + expression
            self.assertEqual(data.count(before), 1)
            data = data.replace(before, b"(unsigned long) " + expression)
        mutant = self.area / "adjacency-mutant.c"
        mutant.write_bytes(data)
        binary = self.compile("adjacency-mutant", mutant, ["-Wno-error=pointer-to-int-cast",
                              "-Wno-error=void-pointer-to-int-cast"])
        for scenario in ("alias-before", "alias-after"):
            with self.subTest(scenario=scenario):
                self.execute(binary, scenario, expect_failure=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
