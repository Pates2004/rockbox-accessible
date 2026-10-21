import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_materials import project_materials_root


ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which('perl'), 'Perl is required for genlang cache tests')
class GenlangCacheTests(unittest.TestCase):
    def test_concurrent_reader_never_sees_unfinished_cache(self):
        workspace = project_materials_root(ROOT)
        workspace.mkdir(parents=True, exist_ok=True)
        output = Path(tempfile.mkdtemp(prefix='genlang-cache-', dir=workspace))
        fixture = output / 'fixture.lang'
        fixture.write_text(''.join(
            '<phrase>\n  id: LANG_' + name + '\n  desc: cache fixture\n  user: core\n'
            '  <source>\n    *: "' + name + '"\n  </source>\n'
            '  <dest>\n    *: "' + name + '"\n  </dest>\n'
            '  <voice>\n    *: "' + name + '"\n  </voice>\n</phrase>\n'
            for name in ('FIRST', 'SECOND', 'THIRD')), encoding='utf-8')
        previous = time.time() - 30
        os.utime(fixture, (previous, previous))
        original = ROOT / 'tools/genlang'
        source = original.read_text(encoding='utf-8')
        marker = '    for my $user (keys %users) {\n'
        self.assertEqual(source.count(marker), 1)
        paused = output / 'genlang-paused'
        paused.write_text(source.replace(marker,
            '    open(CACHE_READY, ">$ENV{GENLANG_CACHE_READY}") or die "Cannot signal cache test";\n'
            '    close CACHE_READY;\n'
            '    scalar <STDIN>;\n' + marker), encoding='utf-8')
        ready = output / 'ready'

        def command(script, name):
            return [shutil.which('perl'), '-s', script.as_posix(), '-e=' + fixture.as_posix(),
                    '-t=hibyr1', '-i=124', '-b=' + (output / (name + '.lng')).as_posix(),
                    '-c=' + (output / (name + '.vstrings')).as_posix(), fixture.as_posix()]

        writer = subprocess.Popen(command(paused, 'writer'), stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  env=dict(os.environ, GENLANG_CACHE_READY=str(ready)))
        try:
            deadline = time.monotonic() + 20
            while not ready.exists() and time.monotonic() < deadline and writer.poll() is None:
                time.sleep(0.01)
            self.assertTrue(ready.exists(), 'Writer did not reach controlled cache-publication point')
            reader = subprocess.run(command(original, 'reader'), capture_output=True, timeout=20)
            self.assertEqual(reader.returncode, 0, reader.stderr.decode(errors='replace'))
        finally:
            try:
                writer_stdout, writer_stderr = writer.communicate(b'continue\n', timeout=20)
            except BaseException:
                writer.kill()
                writer.communicate()
                raise
        self.assertEqual(writer.returncode, 0, writer_stderr.decode(errors='replace'))
        self.assertEqual(writer_stdout, b'')
        self.assertEqual(writer_stderr, b'')
        for extension in ('lng', 'vstrings'):
            with self.subTest(extension=extension):
                actual = (output / ('reader.' + extension)).read_bytes()
                expected = (output / ('writer.' + extension)).read_bytes()
                self.assertEqual(struct.unpack_from('>H', actual, 4)[0], 3,
                                 'Reader consumed an incomplete shared English cache')
                self.assertEqual(actual, expected)
        self.assertEqual(len((output / 'english.list').read_text(encoding='utf-8').splitlines()), 3)
        self.assertEqual(list(output.glob('english.list.*')), [])
        print('Retained genlang cache regression evidence:', output)


if __name__ == '__main__':
    unittest.main()
