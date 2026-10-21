import datetime
import json
import os
from pathlib import Path
import shlex
import subprocess
import unittest

from test_tts_coverage import extract_block


import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root as _project_materials_root



ROOT = Path(__file__).resolve().parents[2]


class StartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        cls.results = _project_materials_root(ROOT) / 'sdl-startup-tests' / timestamp
        cls.results.mkdir(parents=True)
        cls.kernel = (ROOT / 'firmware/target/hosted/sdl/kernel-sdl.c').read_text()
        cls.system = (ROOT / 'firmware/target/hosted/sdl/system-sdl.c').read_text()
        (cls.results / 'kernel-functions.h').write_text(
            cls.kernel[cls.kernel.index('static SDL_TimerID tick_timer_id;'):], encoding='utf-8')
        cls.executables = {}
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'sdl2'], text=True))
        for mode in ('native-threads', 'sdl-threads'):
            executable = cls.results / mode
            command = shlex.split(os.environ.get('CC', 'cc')) + [
                '-std=c99', '-g', '-O1', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=undefined', '-fno-sanitize-recover=all',
                '-I', str(cls.results), str(ROOT / 'tools/tests/test_sdl_startup.c'),
                '-o', str(executable)] + flags
            if mode == 'sdl-threads':
                command.append('-DHAVE_SDL_THREADS')
            built = subprocess.run(command, capture_output=True, text=True)
            (cls.results / f'{mode}-build.log').write_text(built.stdout + built.stderr, encoding='utf-8')
            if built.returncode:
                raise AssertionError(built.stderr)
            cls.executables[mode] = executable
        cls.runs = []

    @classmethod
    def tearDownClass(cls):
        (cls.results / 'runs.json').write_text(json.dumps(cls.runs, indent=2), encoding='utf-8')
        print(f'SDL startup evidence: {cls.results}', flush=True)

    def run_case(self, mode, failure):
        process = subprocess.run([str(self.executables[mode]), str(failure)],
                                 capture_output=True, text=True, timeout=15)
        self.runs.append({'mode': mode, 'failure': failure, 'returncode': process.returncode,
                          'stdout': process.stdout, 'stderr': process.stderr})
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)

    def test_initialization_precedes_events(self):
        body = extract_block(self.system, 'void system_init(void)')
        initialized = body.index('if (!sim_kernel_init())')
        self.assertLess(body.index('SDL_InitSubSystem(SDL_INIT_TIMER)'), initialized)
        for operation in ('sdl_window_setup()', 'SDL_CreateThread(', 'SDL_AddEventWatch('):
            self.assertLess(initialized, body.index(operation))
        tick = extract_block(self.kernel, 'void tick_start(')
        self.assertNotIn('sim_kernel_init(', tick)

    def test_native_thread_interrupt_waits_until_enabled(self):
        self.run_case('native-threads', 0)

    def test_sdl_thread_interrupt_waits_until_enabled(self):
        self.run_case('sdl-threads', 0)

    def test_native_thread_allocation_failures(self):
        for failure in range(1, 5):
            with self.subTest(failure=failure):
                self.run_case('native-threads', failure)

    def test_sdl_thread_allocation_failures(self):
        for failure in range(1, 3):
            with self.subTest(failure=failure):
                self.run_case('sdl-threads', failure)


if __name__ == '__main__':
    unittest.main(verbosity=2)
