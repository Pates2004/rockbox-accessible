"""Exercise production book-container code against Python zipfile archives."""
import ctypes as c
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import random
import re
import shlex
import struct
import subprocess
import sys
import unittest
import warnings
import zipfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root

ROOT = Path(__file__).resolve().parents[2]
OK, AGAIN, END = 0, 1, 2
INVALID, UNSUPPORTED, CORRUPT, IO_ERROR, STALE, CANCELLED, LIMIT = range(-1, -8, -1)
INPUTS = ["apps/book_archive.c", "apps/book_archive.h", "apps/book_reader.h",
          "firmware/common/inflate.c", "firmware/include/inflate.h",
          "firmware/common/crc32.c", "firmware/include/crc32.h",
          "firmware/common/adler32.c", "firmware/include/adler32.h",
          "firmware/export/system.h", "tools/tests/fixtures/book_archive_fixture.c",
          "tools/tests/test_book_archive.py"]
Read = c.CFUNCTYPE(c.c_int64, c.c_void_p, c.c_uint64, c.c_void_p, c.c_size_t)
Cancel = c.CFUNCTYPE(c.c_bool, c.c_void_p)
Sink = c.CFUNCTYPE(c.c_int, c.c_void_p, c.c_void_p, c.c_size_t)


class IO(c.Structure):
    _fields_ = [("size", c.c_uint64), ("read_at", Read), ("cancelled", Cancel), ("context", c.c_void_p)]


class Archive(c.Structure):
    _fields_ = [("io", IO), ("directory_offset", c.c_uint32),
                ("directory_size", c.c_uint32), ("entries", c.c_uint32)]


class Cursor(c.Structure):
    _fields_ = [("index", c.c_uint32), ("offset", c.c_uint32)]


class Entry(c.Structure):
    _fields_ = [("directory_position", c.c_uint32), ("local_offset", c.c_uint32),
                ("compressed_size", c.c_uint32), ("size", c.c_uint32), ("crc", c.c_uint32),
                ("flags", c.c_uint16), ("method", c.c_uint16), ("version", c.c_uint16),
                ("name", c.c_char * 1024)]


class NonSeekable(io.BytesIO):
    def seek(self, *args):
        raise io.UnsupportedOperation("streaming fixture")


def make_zip(files, method=zipfile.ZIP_DEFLATED, descriptor=False, comment=b""):
    output = NonSeekable() if descriptor else io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(output, "w", compression=method) as archive:
            for name, payload in files:
                archive.writestr(name, payload)
            archive.comment = comment
    return bytearray(output.getvalue())


class BookArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.area = project_materials_root(ROOT) / "book-archive-tests" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        cls.area.mkdir(parents=True, exist_ok=False)
        cls.inputs = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in INPUTS}
        cls.commands = []
        cls.addClassCleanup(cls.report)
        (cls.area / "config.h").write_text("/* Host CRC unit configuration. */\n", encoding="utf-8")
        header = (ROOT / "firmware/export/system.h").read_text(encoding="utf-8")
        minimum = re.search(r"^#define MIN\(a, b\).+$", header, re.MULTILINE).group()
        (cls.area / "system.h").write_text("/* Actual production MIN macro, no target simulation. */\n" + minimum + "\n", encoding="utf-8")
        compiler = shlex.split(os.environ.get("CC", "cc"))
        flags = ["-std=gnu11", "-Wall", "-Wextra", "-Werror", "-O1", "-g",
                 "-I", str(ROOT / "apps"), "-iquote", str(cls.area), "-iquote", str(ROOT / "firmware/include")]
        if os.environ.get("BOOK_ARCHIVE_SANITIZE"):
            flags += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
        sources = [str(ROOT / p) for p in (INPUTS[0], INPUTS[3], INPUTS[5], INPUTS[7], INPUTS[10])]
        binary = cls.area / ("archive.dll" if os.name == "nt" else "archive.so")
        # Bind to Rockbox's actual inflate, not a process-global zlib symbol
        # imported by Python's independent fixture generator.
        cls.run_command(compiler + flags + ["-shared"] + ([] if os.name == "nt" else ["-fPIC", "-Wl,-Bsymbolic"])
                        + sources + ["-o", str(binary)])
        cls.lib = c.CDLL(str(binary))
        cls.lib.book_archive_test_size.argtypes = [c.c_uint]
        cls.lib.book_archive_test_size.restype = c.c_size_t
        for index, data_type in enumerate((IO, Archive, Cursor, Entry)):
            if cls.lib.book_archive_test_size(index) != c.sizeof(data_type):
                raise AssertionError("C/Python ABI mismatch: " + data_type.__name__)
        cls.lib.book_archive_open.argtypes = [c.POINTER(Archive), c.POINTER(IO)]
        cls.lib.book_archive_next.argtypes = [c.POINTER(Archive), c.POINTER(Cursor), c.POINTER(Entry)]
        cls.lib.book_archive_find.argtypes = [c.POINTER(Archive), c.c_char_p, c.POINTER(Entry)]
        cls.lib.book_archive_workspace_size.restype = c.c_size_t
        cls.lib.book_archive_workspace_align.restype = c.c_size_t
        cls.lib.book_archive_stream.argtypes = [c.POINTER(Archive), c.POINTER(Entry), c.c_void_p,
                                               c.c_size_t, c.c_uint64, Sink, c.c_void_p]
        cls.lib.book_archive_test_inflate.argtypes = [c.c_void_p, c.c_int, c.c_void_p, c.c_size_t,
                                                     c.c_void_p, c.c_size_t, c.POINTER(c.c_size_t)]
        cls.asan = None
        if os.environ.get("BOOK_ARCHIVE_ASAN"):
            cls.asan = cls.area / "archive-asan"
            cls.run_command(compiler + flags + ["-DBOOK_ARCHIVE_TEST_EXECUTABLE", "-fsanitize=address,undefined",
                                                "-fno-sanitize-recover=all"] + sources + ["-o", str(cls.asan)])
        print("Book-container evidence:", cls.area, flush=True)

    @classmethod
    def run_command(cls, argv):
        result = subprocess.run(argv, capture_output=True, text=True, timeout=90)
        cls.commands.append(dict(argv=argv, exit=result.returncode, stdout=result.stdout, stderr=result.stderr))
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    @classmethod
    def report(cls):
        after = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in INPUTS}
        (cls.area / "provenance.json").write_text(json.dumps(dict(
            inputs_before=cls.inputs, inputs_after=after, source_stable=cls.inputs == after,
            commands=cls.commands, workspace_size=cls.lib.book_archive_workspace_size() if hasattr(cls, "lib") else None,
            format_adapters_tested=False, physical_tests=False), indent=2) + "\n", encoding="utf-8")

    def setUp(self):
        self.data = bytearray()
        self.calls = 0
        self.short_read = 0
        self.fail = None
        self.cancel = False
        self.output = bytearray()
        self.sink_result = OK
        self.callback_error = None
        self.max_sink = 0

        def read(context, offset, output, size):
            self.calls += 1
            if self.fail is not None:
                return self.fail
            if self.short_read:
                size = min(size, self.short_read)
            data = bytes(self.data[offset:offset + size])
            c.memmove(output, data, len(data))
            return len(data)

        def sink(context, data, size):
            self.max_sink = max(self.max_sink, size)
            self.output.extend(c.string_at(data, size))
            return self.sink_result

        self.reader, self.cancelled, self.sink = Read(read), Cancel(lambda ctx: self.cancel), Sink(sink)
        self.io = IO(0, self.reader, self.cancelled, None)
        self.archive = Archive()
        self.workspace_size = self.lib.book_archive_workspace_size()
        self.workspace = c.create_string_buffer(self.workspace_size + self.lib.book_archive_workspace_align())
        alignment = self.lib.book_archive_workspace_align()
        self.workspace_pointer = (c.addressof(self.workspace) + alignment - 1) // alignment * alignment

    def open(self, data, expected=OK):
        self.data = bytearray(data)
        self.io.size = len(self.data)
        before = bytes(self.archive)
        result = self.lib.book_archive_open(c.byref(self.archive), c.byref(self.io))
        self.assertEqual(result, expected)
        if result != OK:
            self.assertEqual(bytes(self.archive), before)

    def find(self, name=b"word/document.xml", expected=OK):
        out = Entry()
        c.memset(c.byref(out), 0xA5, c.sizeof(out))
        before = bytes(out)
        result = self.lib.book_archive_find(c.byref(self.archive), name, c.byref(out))
        self.assertEqual(result, expected)
        if result != OK:
            self.assertEqual(bytes(out), before)
        return out

    def stream(self, entry, expected=OK, limit=2 * 1024 * 1024, workspace=True):
        self.output.clear()
        result = self.lib.book_archive_stream(c.byref(self.archive), c.byref(entry),
            self.workspace_pointer if workspace else None, self.workspace_size if workspace else 0,
            limit, self.sink, None)
        self.assertEqual(result, expected)
        return bytes(self.output)

    def test_zipfile_roundtrips_all_supported_modes_and_chunk_boundaries(self):
        rng = random.Random(20261025)
        for method in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            for descriptor in (False, True):
                for size in (0, 1, 511, 512, 32767, 32768, 32769, 100003):
                    payload = rng.randbytes(size)
                    self.open(make_zip([("word/document.xml", payload)], method, descriptor))
                    found = self.find()
                    self.assertEqual((found.size, found.crc, found.method), (size, zlib.crc32(payload), method))
                    self.assertEqual(self.stream(found), payload)
                    self.assertLessEqual(self.max_sink, 32768)

    def test_short_reads_and_unicode_case_sensitive_names(self):
        payload = "Zażółć gęślą jaźń".encode()
        self.short_read = 3
        self.open(make_zip([("OPS/żółć.xhtml", payload)]))
        self.assertEqual(self.stream(self.find("OPS/żółć.xhtml".encode())), payload)
        self.find("ops/żółć.xhtml".encode(), END)

    def test_directory_iteration_and_absent_member(self):
        self.open(make_zip([("mimetype", b"application/epub+zip"), ("OPS/ch1.xhtml", b"chapter"), ("empty", b"")]))
        cursor, out = Cursor(), Entry()
        names = []
        while self.lib.book_archive_next(c.byref(self.archive), c.byref(cursor), c.byref(out)) == OK:
            names.append(out.name)
        self.assertEqual(names, [b"mimetype", b"OPS/ch1.xhtml", b"empty"])
        saved = bytes(cursor), bytes(out)
        self.assertEqual(self.lib.book_archive_next(c.byref(self.archive), c.byref(cursor), c.byref(out)), END)
        self.assertEqual((bytes(cursor), bytes(out)), saved)
        self.find(b"absent", END)

    def test_empty_zip_and_comment_search_boundaries(self):
        for size in (0, 511, 512, 513, 65535):
            comment = b"c" * size
            self.open(make_zip([], comment=comment))
            self.find(b"absent", END)
        fake = b"PK\x05\x06" + bytes(18)
        self.open(make_zip([("word/document.xml", b"book")], comment=b"c" * 510 + fake))
        self.assertEqual(self.stream(self.find()), b"book")

    def test_duplicates_long_names_and_nul_names(self):
        self.open(make_zip([("word/document.xml", b"a"), ("word/document.xml", b"b")]))
        self.find(expected=CORRUPT)
        self.open(make_zip([("x" * 1024, b"a")]))
        self.find(b"absent", LIMIT)
        self.open(make_zip([("word/document.xml", b"a")]))
        self.data[self.archive.directory_offset + 46] = 0
        self.find(expected=CORRUPT)

    def test_declared_output_limit_and_workspace_are_checked_before_sink(self):
        self.open(make_zip([("word/document.xml", b"x" * 10000)]))
        found = self.find()
        self.stream(found, LIMIT, limit=9999)
        self.assertFalse(self.output)
        self.stream(found, INVALID, workspace=False)
        self.assertFalse(self.output)
        pointer = self.workspace_pointer + 1
        self.assertEqual(self.lib.book_archive_stream(c.byref(self.archive), c.byref(found), pointer,
            self.workspace_size, 10000, self.sink, None), INVALID)
        self.open(make_zip([("word/document.xml", b"stored")], zipfile.ZIP_STORED))
        self.assertEqual(self.stream(self.find(), workspace=False), b"stored")

    def test_io_cancellation_and_sink_failure(self):
        data = make_zip([("word/document.xml", b"x" * 100003)])
        self.fail = IO_ERROR
        self.open(data, IO_ERROR)
        self.fail, self.cancel = None, True
        self.open(data, CANCELLED)
        self.cancel = False
        self.open(data)
        found = self.find()
        self.cancel = True
        self.stream(found, CANCELLED)
        self.cancel = False
        self.fail = 0
        self.stream(found, CORRUPT)
        self.fail = IO_ERROR
        self.stream(found, IO_ERROR)
        self.fail = None
        for result, expected in ((CANCELLED, CANCELLED), (IO_ERROR, IO_ERROR), (AGAIN, IO_ERROR)):
            self.sink_result = result
            self.stream(found, expected)

    def test_stale_entry_and_corrupt_local_header(self):
        original = make_zip([("word/document.xml", b"book")])
        self.open(original)
        found = self.find()
        found.size += 1
        self.stream(found, STALE)
        found = self.find()
        for offset in (0, 4, 6, 8, 14, 18, 22, 26, 30):
            self.data = bytearray(original)
            self.data[offset] ^= 1
            self.stream(found, CORRUPT)

    def test_crc_payload_size_and_descriptor_failures(self):
        for method in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            self.open(make_zip([("word/document.xml", b"abcdef" * 12000)], method))
            found = self.find()
            data_start = 30 + len(found.name)
            self.data[data_start] ^= 0x80
            self.stream(found, CORRUPT)
            self.open(make_zip([("word/document.xml", b"abc")], method, descriptor=True))
            found = self.find()
            descriptor_offset = 30 + len(found.name) + found.compressed_size
            self.data[descriptor_offset + 4] ^= 1
            self.stream(found, CORRUPT)

    def test_unsupported_profiles_and_unknown_compression(self):
        original = make_zip([("word/document.xml", b"book")])
        eocd = original.rfind(b"PK\x05\x06")
        for offset, value, fmt in ((eocd + 4, 1, "H"), (eocd + 10, 65535, "H"),
                                    (eocd + 12, (1 << 32) - 1, "I")):
            data = bytearray(original)
            struct.pack_into("<" + fmt, data, offset, value)
            self.open(data, UNSUPPORTED)
        self.open(original)
        cd = self.archive.directory_offset
        for local_offset, cd_offset, value in ((6, 8, 1), (8, 10, 99), (4, 6, 45)):
            self.data = bytearray(original)
            struct.pack_into("<H", self.data, local_offset, value)
            struct.pack_into("<H", self.data, cd + cd_offset, value)
            self.stream(self.find(), UNSUPPORTED)

    def test_truncated_and_inconsistent_directory(self):
        original = make_zip([("word/document.xml", b"book")])
        for size in (0, 1, 21, len(original) - 1):
            self.open(original[:size], CORRUPT)
        self.open(original)
        cd = self.archive.directory_offset
        for offset in (cd, cd + 28, cd + 30):
            data = bytearray(original)
            data[offset] ^= 0x40
            self.open(data, CORRUPT)

    def test_unsigned_data_descriptor(self):
        data = make_zip([("word/document.xml", b"book")], descriptor=True)
        descriptor = data.index(b"PK\x07\x08")
        del data[descriptor:descriptor + 4]
        eocd = data.rfind(b"PK\x05\x06")
        offset = struct.unpack_from("<I", data, eocd + 16)[0]
        struct.pack_into("<I", data, eocd + 16, offset - 4)
        self.open(data)
        self.assertEqual(self.stream(self.find()), b"book")

    def test_large_member_and_native_sanitizer_fixture(self):
        payload = ("<p>Large book żółć</p>" * 40000).encode()
        data = make_zip([("word/document.xml", payload)], descriptor=True)
        self.open(data)
        self.assertEqual(self.stream(self.find()), payload)
        self.assertLess(self.workspace_size, 80 * 1024)
        if self.asan:
            source, output = self.area / "large.zip", self.area / "large.xml"
            source.write_bytes(data)
            self.run_command([str(self.asan), str(source), "word/document.xml", str(output)])
            self.assertEqual(output.read_bytes(), payload)

    def test_production_inflater_raw_zlib_gzip_and_short_final_codes(self):
        rng = random.Random(34025)
        for kind, wbits in enumerate((-15, 15, 31)):
            for payload in (b"", b"\xff", b"abc", bytes(range(256)), rng.randbytes(100003),
                            "żółć".encode() * 30000):
                compressor = zlib.compressobj(wbits=wbits)
                data = compressor.compress(payload) + compressor.flush()
                output, written = c.create_string_buffer(len(payload) + 1), c.c_size_t()
                result = self.lib.book_archive_test_inflate(self.workspace_pointer, kind, data,
                    len(data), output, len(payload) + 1, c.byref(written))
                self.assertEqual(result, 0, (kind, len(payload), result))
                self.assertEqual(output.raw[:written.value], payload)
                result = self.lib.book_archive_test_inflate(self.workspace_pointer, kind, data,
                    len(data) - 1, output, len(payload) + 1, c.byref(written))
                self.assertNotEqual(result, 0, (kind, len(payload)))


if __name__ == "__main__":
    unittest.main()
