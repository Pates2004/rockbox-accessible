"""Run the actual shared book core with synthetic, on-demand publications.

No format parser, simulator UI, PDF renderer or physical player is mocked into
existence. Python builds an independent navigation oracle and CRC record.
"""
import ctypes as c
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import shlex
import struct
import subprocess
import sys
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root

ROOT = Path(__file__).resolve().parents[2]
NONE = (1 << 32) - 1
OK, AGAIN, END = 0, 1, 2
INVALID, UNSUPPORTED, CORRUPT, IO_ERROR, STALE, CANCELLED = range(-1, -7, -1)
HEADING, PAGE, PHRASE, PARAGRAPH, SENTENCE, WORD, CHARACTER = [1 << n for n in range(7)]
TEXT, AUDIO, VISUAL = 1, 2, 4
INPUTS = ["apps/book_reader.c", "apps/book_reader.h", "firmware/common/crc32.c",
          "firmware/include/crc32.h", "tools/tests/fixtures/book_reader_fixture.c",
          "tools/tests/test_book_reader.py"]


class Position(c.Structure):
    _fields_ = [("resource", c.c_uint32), ("anchor", c.c_uint32),
                ("text_offset", c.c_uint64), ("audio_resource", c.c_uint32),
                ("audio_ms", c.c_uint64), ("flags", c.c_uint32)]


class Info(c.Structure):
    _fields_ = [("identity", c.c_ubyte * 32), ("revision", c.c_ubyte * 32),
                ("resource_count", c.c_uint32), ("entry_count", c.c_uint32),
                ("units", c.c_uint32)]


class Entry(c.Structure):
    _fields_ = [("parent", c.c_uint32), ("units", c.c_uint32),
                ("heading_level", c.c_uint16), ("position", Position)]


ReadEntry = c.CFUNCTYPE(c.c_int, c.c_void_p, c.c_uint32, c.POINTER(Entry))


class Source(c.Structure):
    _fields_ = [("info", Info), ("read_entry", ReadEntry), ("context", c.c_void_p)]


class Job(c.Structure):
    _fields_ = [("source", c.POINTER(Source)), ("snapshot", Source),
                ("candidate", c.c_uint32), ("remaining", c.c_uint32),
                ("unit", c.c_uint32), ("heading_level", c.c_uint16),
                ("direction", c.c_int), ("edge", c.c_int), ("status", c.c_int),
                ("found_index", c.c_uint32), ("found", Entry)]


def position(flags=TEXT, offset=0):
    return Position(0, 3, offset if flags & TEXT else 0,
                    1 if flags & AUDIO else NONE, 1234 if flags & AUDIO else 0, flags)


def entry(units=HEADING, level=1, parent=NONE):
    return Entry(parent, units, level if units & HEADING else 0, position())


class BookReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.area = project_materials_root(ROOT) / "book-reader-tests" / (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        cls.area.mkdir(parents=True, exist_ok=False)
        cls.before = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in INPUTS}
        cls.commands = []
        cls.addClassCleanup(cls.report)
        # crc32.c only needs these optional tuning defines. This private host
        # configuration is not a generated player configuration or target test.
        (cls.area / "config.h").write_text("/* Host CRC unit fixture. */\n", encoding="utf-8")
        compiler = shlex.split(os.environ.get("CC", "cc"))
        flags = ["-std=c99", "-Wall", "-Wextra", "-Werror", "-pedantic-errors", "-O1", "-g",
                 "-I", str(ROOT / "apps"), "-iquote", str(cls.area),
                 "-iquote", str(ROOT / "firmware/include")]
        if os.environ.get("BOOK_READER_SANITIZE"):
            flags += ["-fsanitize=undefined", "-fno-sanitize-recover=all"]
        sources = [str(ROOT / p) for p in (INPUTS[0], INPUTS[2], INPUTS[4])]
        binary = cls.area / ("book.dll" if os.name == "nt" else "book.so")
        cls.run_command(compiler + flags + ["-shared"] + ([] if os.name == "nt" else ["-fPIC"])
                        + sources + ["-o", str(binary)])
        cls.lib = c.CDLL(str(binary))
        cls.lib.book_test_size.argtypes = [c.c_uint]
        cls.lib.book_test_size.restype = c.c_size_t
        for n, data_type in enumerate((Position, Info, Entry, Source, Job)):
            if cls.lib.book_test_size(n) != c.sizeof(data_type):
                raise AssertionError(f"C/Python ABI mismatch: {data_type.__name__}")
        cls.lib.book_nav_begin.argtypes = [c.POINTER(Job), c.POINTER(Source), c.c_uint32,
                                          c.c_uint32, c.c_uint16, c.c_int, c.c_int]
        cls.lib.book_nav_step.argtypes = [c.POINTER(Job), c.c_uint32,
                                         c.POINTER(c.c_uint32), c.POINTER(Entry)]
        cls.lib.book_nav_cancel.argtypes = [c.POINTER(Job)]
        cls.lib.book_nav_cancel.restype = None
        cls.lib.book_position_valid.argtypes = [c.POINTER(Info), c.POINTER(Position)]
        cls.lib.book_position_valid.restype = c.c_bool
        cls.lib.book_position_encode.argtypes = [c.POINTER(Info), c.POINTER(Position),
                                                 c.c_void_p, c.c_size_t]
        cls.lib.book_position_decode.argtypes = [c.POINTER(Info), c.c_void_p, c.c_size_t,
                                                 c.POINTER(Position)]
        if os.environ.get("BOOK_READER_ASAN"):
            executable = cls.area / "book-asan"
            cls.run_command(compiler + flags + ["-DBOOK_TEST_EXECUTABLE", "-fsanitize=address,undefined",
                                                "-fno-sanitize-recover=all"] + sources + ["-o", str(executable)])
            cls.run_command([str(executable)])
        print("Book-reader evidence:", cls.area, flush=True)

    @classmethod
    def run_command(cls, argv):
        result = subprocess.run(argv, capture_output=True, text=True, timeout=90)
        cls.commands.append(dict(argv=argv, exit=result.returncode,
                                 stdout=result.stdout, stderr=result.stderr))
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    @classmethod
    def report(cls):
        after = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in INPUTS}
        (cls.area / "provenance.json").write_text(json.dumps(dict(
            inputs_before=cls.before, inputs_after=after, source_stable=after == cls.before,
            commands=cls.commands, sizes={t.__name__: c.sizeof(t) for t in (Position, Info, Entry, Source, Job)},
            adapters="synthetic on-demand navigation only", physical_test=False), indent=2) + "\n", encoding="utf-8")

    def setUp(self):
        self.entries = [entry(HEADING, 1), entry(PAGE), entry(HEADING, 2, 0),
                        entry(PHRASE), entry(HEADING, 1), entry(PAGE)]
        self.calls = []
        self.error = None
        self.provider = lambda i: self.entries[i]

        def read(context, index, out):
            self.calls.append(index)
            try:
                result = self.provider(index)
                if isinstance(result, int):
                    return result
                out[0] = result
                return OK
            except Exception as error:
                self.error = error
                return IO_ERROR

        self.callback = ReadEntry(read)
        info = Info()
        info.identity[:] = range(32)
        info.revision[:] = range(32, 64)
        info.resource_count, info.entry_count = 3, len(self.entries)
        info.units = HEADING | PAGE | PHRASE
        self.source = Source(info, self.callback, None)
        self.job = Job()

    def tearDown(self):
        self.assertIsNone(self.error)

    def begin(self, origin=NONE, unit=HEADING, level=0, direction=1, wrap=0):
        return self.lib.book_nav_begin(c.byref(self.job), c.byref(self.source), origin, unit,
                                       level, direction, wrap)

    def step(self, budget=1):
        index, out = c.c_uint32(0x12345678), Entry()
        c.memset(c.byref(out), 0xA5, c.sizeof(out))
        before = bytes(out)
        result = self.lib.book_nav_step(c.byref(self.job), budget, c.byref(index), c.byref(out))
        if result != OK:
            self.assertEqual(index.value, 0x12345678)
            self.assertEqual(bytes(out), before)
        return result, index.value, out

    def finish(self, budget=3):
        for _ in range(100001):
            result, index, out = self.step(budget)
            if result != AGAIN:
                return result, index, out
        self.fail("Navigation did not terminate")

    def test_levels_and_repeatable_result(self):
        self.assertLessEqual(c.sizeof(Job), 512)
        self.assertEqual(self.begin(origin=0, level=1), AGAIN)
        self.assertEqual(self.finish()[:2], (OK, 4))
        self.assertEqual(self.step()[:2], (OK, 4))
        self.assertEqual(self.calls, [1, 2, 3, 4])
        self.assertEqual(self.begin(origin=4, level=2, direction=-1), AGAIN)
        self.assertEqual(self.finish()[:2], (OK, 2))

    def test_every_unit_and_visual_audio_targets(self):
        self.source.info.units = 127
        for unit in (HEADING, PAGE, PHRASE, PARAGRAPH, SENTENCE, WORD, CHARACTER):
            for flags in (TEXT, AUDIO, VISUAL, TEXT | AUDIO, TEXT | VISUAL):
                item = entry(unit, 65535)
                item.position = position(flags)
                self.provider = lambda i: item
                self.begin(unit=unit)
                result, index, found = self.step()
                self.assertEqual((result, index, found.position.flags), (OK, 0, flags))

    def test_stop_wrap_and_single_entry(self):
        self.assertEqual(self.begin(origin=4), AGAIN)
        self.assertEqual(self.finish()[0], END)
        self.assertEqual(self.begin(origin=4, wrap=1), AGAIN)
        self.assertEqual(self.finish()[:2], (OK, 0))
        self.assertEqual(self.begin(origin=0, direction=-1), END)
        self.assertEqual(self.step()[0], END)
        self.assertEqual(self.begin(origin=0, direction=-1, wrap=1), AGAIN)
        self.assertEqual(self.finish()[:2], (OK, 4))
        self.source.info.entry_count = 1
        for direction in (-1, 1):
            self.assertEqual(self.begin(origin=0, wrap=1, direction=direction), END)

    def test_empty_index_and_unsupported_units(self):
        self.source.info.entry_count = 0
        self.assertEqual(self.begin(), END)
        self.assertEqual(self.step()[0], END)
        self.assertEqual(self.begin(unit=WORD), UNSUPPORTED)
        self.assertEqual(self.calls, [])

    def test_invalid_request_and_zero_budget_preserve_job(self):
        self.begin()
        saved = bytes(self.job)
        for options in (dict(origin=99), dict(unit=0), dict(unit=HEADING | PAGE),
                        dict(unit=128), dict(unit=PAGE, level=1), dict(direction=0), dict(wrap=3)):
            self.assertEqual(self.begin(**options), INVALID)
            self.assertEqual(bytes(self.job), saved)
        self.assertEqual(self.step(0)[0], INVALID)
        self.assertEqual(bytes(self.job), saved)
        self.assertEqual(self.finish()[:2], (OK, 0))

    def test_large_generated_index_is_bounded_and_cancellable(self):
        self.source.info.entry_count = 100000
        self.provider = lambda i: entry(HEADING if i == 99999 else 0)
        self.assertEqual(self.begin(), AGAIN)
        for n in range(50):
            self.assertEqual(self.step(7)[0], AGAIN)
            self.assertEqual(len(self.calls), (n + 1) * 7)
        self.lib.book_nav_cancel(c.byref(self.job))
        self.assertEqual(self.step()[0], CANCELLED)
        self.assertEqual(len(self.calls), 350)
        self.begin(origin=99997)
        self.assertEqual(self.finish()[:2], (OK, 99999))

    def test_retry_and_io_failures(self):
        self.provider = lambda i: AGAIN
        self.begin()
        for _ in range(3):
            self.assertEqual(self.step(10)[0], AGAIN)
        self.assertEqual(self.calls, [0, 0, 0])
        self.provider = lambda i: self.entries[i]
        self.assertEqual(self.finish()[:2], (OK, 0))
        for error in (IO_ERROR, CORRUPT, END, INVALID, 999):
            self.provider = lambda i: error
            self.begin()
            expected = IO_ERROR if error == IO_ERROR else CORRUPT
            self.assertEqual(self.step()[0], expected)
            count = len(self.calls)
            self.assertEqual(self.step()[0], expected)
            self.assertEqual(len(self.calls), count)

    def test_source_changes_before_and_during_read(self):
        for field in ("identity", "revision", "resource_count", "entry_count", "units"):
            self.begin()
            old = bytes(self.source.info)
            if field in ("identity", "revision"):
                getattr(self.source.info, field)[0] ^= 1
            else:
                setattr(self.source.info, field, getattr(self.source.info, field) + 1)
            calls = len(self.calls)
            self.assertEqual(self.step()[0], STALE)
            self.assertEqual(len(self.calls), calls)
            c.memmove(c.byref(self.source.info), old, len(old))
        def changing(index):
            self.source.info.revision[1] ^= 1
            return self.entries[index]
        self.provider = changing
        self.begin()
        self.assertEqual(self.step()[0], STALE)

    def test_source_callback_and_context_changes_invalidate_job(self):
        self.begin()
        self.source.context = 1
        self.assertEqual(self.step()[0], STALE)
        self.assertEqual(self.calls, [])
        self.source.context = None
        self.begin()
        alternate = ReadEntry(lambda context, index, out: IO_ERROR)
        self.source.read_entry = alternate
        self.assertEqual(self.step()[0], STALE)
        self.assertEqual(self.calls, [])

    def test_corrupt_entries_are_rejected_before_result(self):
        for bad in (Entry(0, HEADING, 1, position()), entry(HEADING, 0),
                    Entry(NONE, PAGE, 1, position()), entry(128),
                    Entry(NONE, HEADING, 1, Position(99, 0, 0, NONE, 0, TEXT))):
            self.provider = lambda i: bad
            self.begin()
            self.assertEqual(self.step()[0], CORRUPT)

    def test_uint32_endpoints_do_not_overflow(self):
        self.source.info.entry_count = NONE
        self.provider = lambda i: entry()
        self.assertEqual(self.begin(origin=NONE - 1), END)
        self.assertEqual(self.begin(origin=NONE - 1, wrap=1), AGAIN)
        self.assertEqual(self.step()[:2], (OK, 0))
        self.begin(direction=-1)
        self.assertEqual(self.step()[:2], (OK, NONE - 1))

    def test_random_navigation_matches_independent_list_oracle(self):
        rng = random.Random(20261025)
        self.entries = [entry(rng.choice((HEADING, PAGE, PHRASE, 0)), rng.randint(1, 6))
                        for _ in range(517)]
        self.source.info.entry_count = len(self.entries)
        for _ in range(600):
            origin = rng.choice([NONE] + list(range(len(self.entries))))
            unit, level = rng.choice((HEADING, PAGE, PHRASE)), rng.randint(0, 6)
            if unit != HEADING:
                level = 0
            direction, wrap = rng.choice((-1, 1)), rng.choice((0, 1))
            candidates = list(range(len(self.entries)))
            if direction == -1:
                candidates.reverse()
            if origin != NONE:
                split = candidates.index(origin)
                candidates = candidates[split + 1:] + (candidates[:split] if wrap else [])
            expected = next((i for i in candidates if self.entries[i].units & unit and
                             (not level or self.entries[i].heading_level == level)), None)
            self.begin(origin, unit, level, direction, wrap)
            result, found, _ = self.finish(rng.randint(1, 13))
            self.assertEqual(result, END if expected is None else OK)
            if expected is not None:
                self.assertEqual(found, expected)

    def golden(self, pos):
        data = struct.pack("<4sHH32s32sIIQIQI", b"RBKP", 1, 108,
                           bytes(self.source.info.identity), bytes(self.source.info.revision),
                           pos.resource, pos.anchor, pos.text_offset, pos.audio_resource,
                           pos.audio_ms, pos.flags)
        return data + struct.pack("<I", zlib.crc32(data))

    def decode(self, data, expected=OK):
        out = Position()
        c.memset(c.byref(out), 0xA5, c.sizeof(out))
        saved = bytes(out)
        result = self.lib.book_position_decode(c.byref(self.source.info), data, len(data), c.byref(out))
        self.assertEqual(result, expected)
        if result != OK:
            self.assertEqual(bytes(out), saved)
        return out

    def test_independent_record_and_all_media_modes(self):
        for flags in range(1, 8):
            pos = position(flags, (1 << 63) + 123)
            if flags & AUDIO:
                pos.audio_ms = (1 << 64) - 1
            self.assertTrue(self.lib.book_position_valid(c.byref(self.source.info), c.byref(pos)))
            expected = self.golden(pos)
            record = c.create_string_buffer(120)
            self.assertEqual(self.lib.book_position_encode(c.byref(self.source.info), c.byref(pos), record, 120), OK)
            self.assertEqual(record.raw, expected + bytes(12))
            restored = self.decode(expected)
            for name, _ in Position._fields_:
                self.assertEqual(getattr(restored, name), getattr(pos, name))

    def test_record_damage_truncation_version_and_revision(self):
        original = self.golden(position())
        for size in range(108):
            self.decode(original[:size], CORRUPT)
        self.decode(original + b"x", CORRUPT)
        for index in range(108):
            damaged = bytearray(original)
            damaged[index] ^= 1
            self.decode(bytes(damaged), CORRUPT)
        for index, value, expected in ((4, 2, UNSUPPORTED), (5, 1, UNSUPPORTED),
                                        (8, 99, STALE), (40, 99, STALE), (6, 99, CORRUPT),
                                        (72, 99, CORRUPT), (100, 0, CORRUPT), (100, 128, CORRUPT)):
            data = bytearray(original)
            data[index] = value
            data[104:] = struct.pack("<I", zlib.crc32(data[:104]))
            self.decode(bytes(data), expected)

    def test_invalid_positions_cannot_overwrite_record(self):
        for pos in (Position(3, 0, 0, NONE, 0, TEXT), Position(0, 0, 0, NONE, 0, 0),
                    Position(0, 0, 1, NONE, 0, VISUAL), Position(0, 0, 0, 3, 0, AUDIO),
                    Position(0, 0, 0, 1, 0, TEXT), Position(0, 0, 0, NONE, 1, TEXT)):
            self.assertFalse(self.lib.book_position_valid(c.byref(self.source.info), c.byref(pos)))
            record = c.create_string_buffer(b"x" * 108, 108)
            self.assertEqual(self.lib.book_position_encode(c.byref(self.source.info), c.byref(pos), record, 108), INVALID)
            self.assertEqual(record.raw, b"x" * 108)
        pos = position()
        record = c.create_string_buffer(b"x" * 108, 108)
        self.assertEqual(self.lib.book_position_encode(c.byref(self.source.info), c.byref(pos), record, 107), INVALID)
        self.assertEqual(record.raw, b"x" * 108)


if __name__ == "__main__":
    unittest.main()
