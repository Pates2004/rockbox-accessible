import datetime
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root


ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "lib/espeak/engine"
UPSTREAM_REVISION = "a14831fd3af6b3df77ef23b854cd05ee05b12851"
sys.path.insert(0, str(ROOT / "lib/espeak"))
from data_provenance import validate_supplied_data


class EspeakR34Tests(unittest.TestCase):
    def test_version(self):
        self.assertIn('"1.44.05-r34 Windows x64"',
                      (ENGINE / "synthdata.cpp").read_text(encoding="utf-8"))

    def test_supplied_provenance(self):
        supplied = ROOT.parent / "espeak-1.44.05-source"
        if not (supplied / ".git").exists():
            self.skipTest("Supplied source checkout unavailable")
        revision = subprocess.check_output(
            ["git", "-C", str(supplied), "rev-parse", "HEAD"], text=True).strip()
        self.assertEqual(revision, UPSTREAM_REVISION)
        manifest = ROOT / "lib/espeak/UPSTREAM.sha256"
        for line in manifest.read_text(encoding="utf-8").splitlines():
            expected, relative = line.split(None, 1)
            with self.subTest(file=relative):
                self.assertEqual(hashlib.sha256((supplied / relative).read_bytes()).hexdigest(), expected)
        data = validate_supplied_data(supplied)
        self.assertEqual(len(data["runtime_data"]), 283)
        self.assertEqual(len(data["dictsource"]), 88)

    def test_portability_guards_retained(self):
        checks = {
            "speak_lib.cpp": ("espeak_stat(filename,&statbuf)",
                              "output_type != AUDIO_OUTPUT_SYNCHRONOUS",
                              "strlen(path) + sizeof(\"/espeak-data\") > sizeof(path_home)",
                              "outbuf_size = ((buf_length * samplerate)/1000) * 2;",
                              "FreeTranslators();", "FreeVoiceList();"),
            "synthdata.cpp": ("espeak_fopen(buf,\"rb\")", "length > 64u * 1024u * 1024u",
                              "table_length < 4", "n_phoneme_tables > N_PHONEME_TABS",
                              "memchr(p + 8, 0, N_PHONEME_TAB_NAME)", "FreeSoundIcons();"),
            "translate.cpp": ("rb_espeak_native_yield();", "charix[j]<=0"),
            "voices.cpp": ("espeak_fopen(buf,\"r\")", "DeleteTranslator(new_translator);",
                           "LoadVoice(variant_name,2) == NULL", "voices_list.Data()"),
            "wavegen.cpp": ("static uint32_t wavephase;", "AddHarmonicWrapped",
                            "wavephase <= INT32_MAX", "rb_espeak_native_yield();",
                            "wavegen_resume = 0;", "wavegen_echo_complete = 0;"),
        }
        for name, required in checks.items():
            source = (ENGINE / name).read_text(encoding="utf-8")
            for expression in required:
                with self.subTest(file=name, guard=expression):
                    self.assertIn(expression, source)
        synthdata = (ENGINE / "synthdata.cpp").read_text(encoding="utf-8")
        short_read = re.search(r"if\(fread\(p,1,length,f_in\) != length\)\s*\{([^}]+)\}",
                               synthdata)
        self.assertIsNotNone(short_read)
        self.assertEqual(short_read.group(1).count("Free(p);"), 1)

    @unittest.skipUnless(os.name == "posix" and shutil.which("g++") and shutil.which("nm"),
                         "POSIX C++ compiler required")
    def test_catalog_storage_ownership_and_native_runtime_dependencies(self):
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        output = project_materials_root(ROOT) / "espeak-r34-20261011" / stamp
        output.mkdir(parents=True)
        source = (ENGINE / "voices.cpp").read_text(encoding="utf-8")
        start = source.index("class VoicePointerList")
        end = source.index("static int n_voices_list", start)
        declarations = source[start:end]
        probe = r'''
#include <stdint.h>
#include <stdlib.h>
#include <limits.h>
#include <assert.h>
typedef struct { int value; } espeak_VOICE;
static int allocations;
static int fail_allocations;
static void *tracked_realloc(void *previous, size_t size)
{
    if (fail_allocations)
        return NULL;
    void *result = realloc(previous, size);
    if (result && !previous)
        ++allocations;
    return result;
}
static void tracked_free(void *memory)
{
    if (memory)
        --allocations;
    free(memory);
}
#define realloc tracked_realloc
#define free tracked_free
''' + declarations + r'''
static VoicePointerList persistent;
int main()
{
    assert(persistent.Data() == NULL);
    assert(persistent.Reserve(0));
    assert(persistent.Reserve(201));
    espeak_VOICE **retained = persistent.Data();
    assert(retained != NULL && allocations == 1);
    assert(!persistent.Reserve(SIZE_MAX));
    assert(persistent.Data() == retained && allocations == 1);
    fail_allocations = 1;
    assert(!persistent.Reserve(1000));
    assert(persistent.Data() == retained && allocations == 1);
    fail_allocations = 0;
    assert(persistent.Reserve(1000));
    assert(allocations == 1);
    {
        VoiceCandidateList temporary;
        assert(temporary.Data() == NULL);
        assert(temporary.Reserve(201));
        assert(allocations == 2);
    }
    assert(allocations == 1);
    persistent.Clear();
    persistent.Clear();
    assert(allocations == 0 && persistent.Data() == NULL);
    return 0;
}
'''
        probe_path = output / "ownership.cpp"
        probe_path.write_text(probe, encoding="utf-8")
        executable = output / "ownership"
        command = ["g++", "-std=c++11", "-O2", "-nostdinc++", "-fno-exceptions", "-fno-rtti",
                   "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                   "-fno-sanitize-recover=all", "-fno-pie", "-no-pie", str(probe_path),
                   "-o", str(executable)]
        subprocess.run(command, capture_output=True, text=True, check=True)
        subprocess.run([str(executable)], capture_output=True, text=True, check=True,
                       env=dict(os.environ, ASAN_OPTIONS="detect_leaks=1:halt_on_error=1"))
        object_path = output / "voices.o"
        subprocess.run(["g++", "-std=c++11", "-O2", "-nostdinc++", "-fno-exceptions",
                        "-fno-rtti", "-fno-threadsafe-statics", "-DRB_ESPEAK_NATIVE=1",
                        "-I" + str(ROOT / "lib/espeak/native/include"), "-c",
                        str(ENGINE / "voices.cpp"), "-o", str(object_path)],
                       capture_output=True, text=True, check=True)
        symbols = subprocess.check_output(["nm", str(object_path)], text=True)
        (output / "voices-symbols.txt").write_text(symbols, encoding="utf-8")
        for forbidden in ("__cxa_atexit", "__cxa_guard", "_GLOBAL__sub_I", "__gxx_personality", " atexit"):
            self.assertNotIn(forbidden, symbols)


if __name__ == "__main__":
    unittest.main()
