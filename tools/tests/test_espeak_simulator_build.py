import base64
import datetime
import errno
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from materials_fixtures import materials_resolver


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('simulator_build', ROOT / 'tools/build_espeak_simulator.py')
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def temporary_fixture(prefix):
    workspace = builder.contained(builder._project_materials_root(ROOT) / 'simulator-build-guard-tests')
    workspace.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(prefix=prefix, dir=workspace)


class SimulatorBuildTests(unittest.TestCase):
    def setUp(self):
        temporary = temporary_fixture(prefix='rockbox-simulator-build-')
        self.addCleanup(temporary.cleanup)
        fixture = Path(temporary.name).resolve()
        self.root = fixture / 'source'
        self.root.mkdir()
        self.materials_root = materials_resolver(self.root, fixture / 'materials')
        self.materials = self.materials_root(self.root)
        self.snapshots = self.materials_root(self.root, 'Snapshots')
        self.release_root = self.materials_root(self.root, 'installfiles')
        self.materials.mkdir(parents=True)
        self.patch(builder, 'ROOT', self.root)
        self.patch(builder, '_project_materials_root', self.materials_root)
        self.unused = self.patch(builder, 'assert_not_running')
        self.ignored = self.patch(builder, 'ensure_ignored')
        self.patch(builder, 'print')
        self.build = self.materials / 'build-espeak-simulator-clipzip'

    def patch(self, owner, name, *arguments, **keywords):
        patcher = mock.patch.object(owner, name, *arguments, **keywords)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def write(self, relative, content=b'synthetic fixture'):
        path = self.build / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def prepare_build(self, executable=True):
        if executable:
            self.write('rockboxui', b'synthetic executable')
        self.write('Makefile', b'export MODELNAME=sansaclipzip\n')
        self.write('build.log', b'synthetic build evidence')
        self.write('apps/tts.o', b'synthetic object')
        self.write('simdisk/.rockbox/config.cfg', b'tts rate: 450\n')
        self.write('simdisk/.rockbox/.resume.cfg', b'resume index: 7\n')
        self.write('simdisk/books/private.txt', b'user data to preserve')
        (self.build / 'simdisk/Recordings').mkdir()
        return builder.tree_inventory(self.build)

    def invoke(self, *arguments):
        source = self.root / 'engine'
        for name in ('phondata', 'pl_dict'):
            path = source / 'espeak-data' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'synthetic engine data')
        command = ['builder', '--platform', 'linux', '--target', 'sansaclipzip',
                   '--espeak-source', str(source), *arguments]
        with mock.patch.object(sys, 'argv', command), \
                mock.patch.object(builder.subprocess, 'check_output', return_value=builder.ENGINE_REVISION):
            builder.main()

    def test_archives_entire_build_with_user_data_structure_and_hashes(self):
        before = self.prepare_build()
        destination = builder.preserve(self.build, 'clipzip-development')
        self.assertFalse(self.build.exists())
        self.assertEqual(destination.relative_to(self.snapshots).parts[-2:],
                         ('Workspace', self.build.name))
        self.assertEqual(builder.tree_inventory(destination), before)
        self.assertTrue((destination / 'simdisk/Recordings').is_dir())
        snapshot = destination.parent.parent
        record = json.loads((snapshot / 'preservation.json').read_text(encoding='utf-8'))
        self.assertEqual(record, {'original_path': 'Workspace/' + self.build.name,
                                  'role': 'clipzip-development', 'entries': before})
        self.unused.assert_called_once_with(self.build)
        self.ignored.assert_called_once_with(['snapshots'])

    def test_archives_build_even_after_executable_was_packaged(self):
        before = self.prepare_build(executable=False)
        destination = builder.preserve(self.build, 'clipzip-development')
        self.assertEqual(builder.tree_inventory(destination), before)
        self.assertFalse(self.build.exists())

    def test_missing_build_does_not_create_snapshot_or_check_processes(self):
        self.assertIsNone(builder.preserve(self.build, 'clipzip-development'))
        self.assertFalse(self.snapshots.exists())
        self.unused.assert_not_called()
        self.ignored.assert_not_called()

    def test_running_build_is_untouched_and_no_snapshot_is_created(self):
        before = self.prepare_build()
        self.unused.side_effect = RuntimeError('Process is using the build')
        with self.assertRaisesRegex(RuntimeError, 'Process is using'):
            builder.preserve(self.build, 'clipzip-development')
        self.assertEqual(builder.tree_inventory(self.build), before)
        self.assertFalse(self.snapshots.exists())

    def test_unignored_or_tracked_snapshots_block_archival(self):
        before = self.prepare_build()
        self.ignored.side_effect = RuntimeError('snapshots has tracked files')
        with self.assertRaisesRegex(RuntimeError, 'tracked files'):
            builder.preserve(self.build, 'clipzip-development')
        self.assertEqual(builder.tree_inventory(self.build), before)
        self.assertFalse(self.snapshots.exists())

    def test_existing_snapshot_is_never_overwritten_or_merged(self):
        before = self.prepare_build()
        stamp = datetime.datetime(2026, 10, 9, tzinfo=datetime.timezone.utc)
        snapshot = self.snapshots / 'clipzip-development-20261009T000000000000Z'
        snapshot.mkdir(parents=True)
        marker = snapshot / 'keep.txt'
        marker.write_bytes(b'previous snapshot')
        with mock.patch.object(builder.datetime, 'datetime') as clock:
            clock.now.return_value = stamp
            with self.assertRaises(FileExistsError):
                builder.preserve(self.build, 'clipzip-development')
        self.assertEqual(builder.tree_inventory(self.build), before)
        self.assertEqual(list(snapshot.iterdir()), [marker])
        self.assertEqual(marker.read_bytes(), b'previous snapshot')

    def test_integrity_failure_is_reported_and_archived_data_remains(self):
        before = self.prepare_build()
        with mock.patch.object(builder, 'tree_inventory', side_effect=[before, {}]):
            with self.assertRaisesRegex(RuntimeError, 'Snapshot integrity failure'):
                builder.preserve(self.build, 'clipzip-development')
        destination, = self.snapshots.glob('*/Workspace/' + self.build.name)
        self.assertEqual(builder.tree_inventory(destination), before)
        self.assertFalse(self.build.exists())

    def test_project_root_and_outside_paths_are_rejected(self):
        for path in (self.root, self.root.parent, self.root / '../outside-build'):
            with self.subTest(path=path), self.assertRaisesRegex(RuntimeError, 'Unsafe project artifact'):
                builder.preserve(path, 'clipzip-development')
        self.assertFalse(self.snapshots.exists())

    def test_file_is_rejected_instead_of_archiving_only_the_executable(self):
        executable = self.write('rockboxui')
        with self.assertRaisesRegex(RuntimeError, 'Expected an artifact directory'):
            builder.preserve(executable, 'clipzip-development')
        self.assertTrue(executable.exists())

    def test_unsafe_snapshot_labels_are_rejected(self):
        before = self.prepare_build()
        for label in ('../escape', 'nested/label', '', '/absolute'):
            with self.subTest(label=label), self.assertRaisesRegex(RuntimeError, 'Unsafe snapshot label'):
                builder.preserve(self.build, label)
        self.assertEqual(builder.tree_inventory(self.build), before)

    def test_source_cannot_contain_its_snapshot(self):
        snapshots = self.snapshots
        snapshots.mkdir(parents=True)
        with self.assertRaisesRegex(RuntimeError, 'Unsafe project artifact'):
            builder.preserve(snapshots, 'recursive')
        self.assertEqual(list(snapshots.iterdir()), [])

    def symlink(self, path, target):
        try:
            path.symlink_to(target, target_is_directory=target.is_dir())
        except OSError as error:
            if os.name == 'nt' and getattr(error, 'winerror', None) == 1314:
                self.skipTest('Symlink privilege unavailable; also run on Linux/WSL')
            raise

    def test_link_inside_build_is_rejected_without_moving_user_data(self):
        self.prepare_build()
        user_data = self.build / 'simdisk/books/private.txt'
        link = self.build / 'linked-book.txt'
        self.symlink(link, user_data)
        with self.assertRaisesRegex(RuntimeError, 'Artifact path is a link'):
            builder.preserve(self.build, 'clipzip-development')
        self.assertEqual(user_data.read_bytes(), b'user data to preserve')
        self.assertFalse(self.snapshots.exists())

    def test_linked_build_is_rejected(self):
        self.prepare_build()
        alias = self.build.parent / 'alias'
        self.symlink(alias, self.build)
        with self.assertRaisesRegex(RuntimeError, 'Artifact path is a link'):
            builder.preserve(alias, 'clipzip-development')
        self.assertTrue(self.build.exists())

    def test_linked_snapshot_parent_is_rejected(self):
        before = self.prepare_build()
        other = self.root / 'other'
        other.mkdir()
        self.snapshots.parent.mkdir(parents=True)
        self.symlink(self.snapshots, other)
        with self.assertRaisesRegex(RuntimeError, 'Artifact path is a link'):
            builder.preserve(self.build, 'clipzip-development')
        after = {path.relative_to(self.build).as_posix(): builder.digest(path) if path.is_file() else None
                 for path in self.build.rglob('*')}
        self.assertEqual(after, before)
        self.assertEqual(list(other.iterdir()), [])

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'POSIX FIFO required')
    def test_non_regular_build_entry_is_rejected(self):
        self.prepare_build()
        try:
            os.mkfifo(self.build / 'pipe')
        except OSError as error:
            if error.errno == errno.EOPNOTSUPP:
                self.skipTest('Central filesystem cannot create a FIFO; inventory rejection is tested independently')
            raise
        with self.assertRaisesRegex(RuntimeError, 'Non-regular artifact'):
            builder.preserve(self.build, 'clipzip-development')
        self.assertTrue(self.build.exists())

    def test_non_regular_inventory_entry_is_rejected_before_archival(self):
        self.prepare_build()
        artifact = self.write('special-entry')
        is_file = Path.is_file
        with mock.patch.object(Path, 'is_file', autospec=True,
                               side_effect=lambda path: path != artifact and is_file(path)):
            with self.assertRaisesRegex(RuntimeError, 'Non-regular artifact'):
                builder.preserve(self.build, 'clipzip-development')
        self.assertTrue(artifact.is_file())
        self.assertFalse(self.snapshots.exists())

    def test_build_only_archives_full_tree_then_uses_fresh_build(self):
        before = self.prepare_build(executable=False)
        release = self.release_root / 'clipzip-espeak-simulator'
        release.mkdir(parents=True)
        marker = release / 'user.txt'
        marker.write_bytes(b'existing installed release')
        with mock.patch.object(builder, 'run') as run:
            self.invoke('--build-only')
        destination, = self.snapshots.glob('*/Workspace/' + self.build.name)
        self.assertEqual(builder.tree_inventory(destination), before)
        self.assertEqual(list(self.build.iterdir()), [])
        self.assertEqual(run.call_count, 2)
        self.assertTrue(all(call.args[1] == self.build for call in run.call_args_list))
        self.assertEqual(marker.read_bytes(), b'existing installed release')

    def test_running_build_blocks_build_only_before_configure(self):
        before = self.prepare_build()
        self.unused.side_effect = RuntimeError('running build')
        with mock.patch.object(builder, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'running build'):
                self.invoke('--build-only')
        run.assert_not_called()
        self.assertEqual(builder.tree_inventory(self.build), before)

    def test_package_only_neither_archives_nor_creates_missing_build(self):
        with mock.patch.object(builder, 'preserve') as preserve, mock.patch.object(builder, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'Cannot verify simulator build target'):
                self.invoke('--package-only')
        preserve.assert_not_called()
        run.assert_not_called()
        self.assertFalse(self.build.exists())
        self.assertFalse(self.snapshots.exists())

    def test_linux_zip_build_leaves_native_build_paths_intact(self):
        native_paths = [self.materials / ('build-espeak-' + slug)
                        for slug in ('clipplus', 'clipzip')]
        for directory in native_paths:
            directory.mkdir(parents=True)
            (directory / 'rockbox.elf').write_bytes(b'native firmware fixture')
        with mock.patch.object(builder, 'run') as run:
            self.invoke('--build-only')
        for directory in native_paths:
            self.assertEqual((directory / 'rockbox.elf').read_bytes(), b'native firmware fixture')
        self.assertTrue(all(call.args[1] == self.build for call in run.call_args_list))
        self.assertFalse(self.snapshots.exists())


class SimulatorProcessTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Native Windows process and file guards required')
    def test_windows_guard_accepts_unused_build_and_rejects_locked_user_file(self):
        execute = subprocess.run
        with temporary_fixture(prefix='rockbox-windows-build-') as temporary:
            path = Path(temporary).resolve()
            artifact = path / 'user-book.txt'
            artifact.write_bytes(b'user data')
            with mock.patch.object(builder.subprocess, 'check_output', return_value=str(path)), \
                    mock.patch.object(builder.subprocess, 'run',
                                      side_effect=lambda command, **keywords: execute(
                                          command, capture_output=True, **keywords)):
                builder.assert_windows_unused(path)
                with artifact.open('rb'):
                    with self.assertRaises(subprocess.CalledProcessError):
                        builder.assert_windows_unused(path)

    @unittest.skipUnless(os.name == 'nt', 'Native Windows process guard required')
    def test_windows_process_using_build_in_command_line_blocks_archiving(self):
        execute = subprocess.run
        with temporary_fixture(prefix='rockbox-windows-process-') as temporary:
            path = Path(temporary).resolve()
            process = subprocess.Popen([sys.executable, '-B', '-c', 'import sys; sys.stdin.read()',
                                        str(path / 'artifact.txt')], stdin=subprocess.PIPE)
            try:
                with mock.patch.object(builder.subprocess, 'check_output', return_value=str(path)), \
                        mock.patch.object(builder.subprocess, 'run',
                                          side_effect=lambda command, **keywords: execute(
                                              command, capture_output=True, **keywords)):
                    with self.assertRaises(subprocess.CalledProcessError):
                        builder.assert_windows_unused(path)
            finally:
                process.communicate(timeout=10)

    @unittest.skipUnless(Path('/proc/self/fd').is_dir(), 'Linux/WSL /proc required')
    def test_open_user_file_blocks_archiving_even_without_running_simulator(self):
        with temporary_fixture(prefix='rockbox-open-build-') as temporary:
            path = Path(temporary).resolve()
            artifact = path / 'user-book.txt'
            artifact.write_bytes(b'user data')
            with artifact.open('rb'):
                with self.assertRaisesRegex(RuntimeError, 'Process .* is using'):
                    builder.assert_not_running(path)

    @unittest.skipUnless(Path('/proc/self/fd').is_dir(), 'Linux/WSL /proc required')
    def test_working_directory_blocks_archiving(self):
        with temporary_fixture(prefix='rockbox-cwd-build-') as temporary:
            process = subprocess.Popen([sys.executable, '-B', '-c',
                                        'import sys; sys.stdin.read()'],
                                       cwd=temporary, stdin=subprocess.PIPE)
            try:
                with self.assertRaisesRegex(RuntimeError, 'Process .* is using'):
                    builder.assert_not_running(Path(temporary))
            finally:
                process.communicate(timeout=10)

    def test_windows_guard_checks_all_processes_and_exclusive_file_access(self):
        target = r'D:\Rockbox\rockbox\Workspace\build-espeak-windows-clipzip'
        with mock.patch.object(builder.subprocess, 'check_output', return_value=target), \
                mock.patch.object(builder.subprocess, 'run') as run:
            builder.assert_windows_unused(Path('/project/Workspace/build-espeak-windows-clipzip'))
        command = run.call_args.args[0]
        script = base64.b64decode(command[-1]).decode('utf-16le')
        self.assertIn('Get-CimInstance Win32_Process)', script)
        self.assertIn('$process.CommandLine', script)
        self.assertIn('-Recurse -Force', script)
        self.assertIn('[IO.FileShare]::None', script)
        self.assertIn(base64.b64encode(target.encode('utf-8')).decode('ascii'), script)
        self.assertTrue(run.call_args.kwargs['check'])

    def test_windows_guard_fails_closed_on_locked_file_or_inspection_failure(self):
        with mock.patch.object(builder.subprocess, 'check_output', return_value=r'D:\project\build'), \
                mock.patch.object(builder.subprocess, 'run',
                                  side_effect=subprocess.CalledProcessError(1, 'powershell')):
            with self.assertRaises(subprocess.CalledProcessError):
                builder.assert_windows_unused(Path('/project/build'))

    def test_windows_guard_rejects_unresolved_native_path(self):
        with mock.patch.object(builder.subprocess, 'check_output', return_value='relative/build'), \
                mock.patch.object(builder.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'Cannot resolve'):
                builder.assert_windows_unused(Path('/project/build'))
        run.assert_not_called()


class SnapshotIgnoreTests(unittest.TestCase):
    def setUp(self):
        temporary = temporary_fixture(prefix='rockbox-ignore-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        resolver = materials_resolver(self.root / 'source', self.root / 'materials')
        patcher = mock.patch.object(builder, '_project_materials_root', side_effect=resolver)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.repository = mock.Mock(returncode=0, stdout=str(self.root), stderr='')

    def test_ignored_untracked_snapshots_are_accepted(self):
        with mock.patch.object(builder.subprocess, 'check_output', return_value=b''), \
                mock.patch.object(builder.subprocess, 'run', side_effect=[self.repository, mock.Mock(returncode=0)]):
            builder.ensure_ignored(['snapshots'])

    def test_tracked_snapshots_are_rejected(self):
        with mock.patch.object(builder.subprocess, 'check_output', return_value=b'snapshots/user.txt\0'), \
                mock.patch.object(builder.subprocess, 'run', return_value=self.repository) as run:
            with self.assertRaisesRegex(RuntimeError, 'has tracked files'):
                builder.ensure_ignored(['snapshots'])
        self.assertEqual(run.call_count, 1)

    def test_missing_ignore_or_git_failure_is_rejected(self):
        for returncode in (1, 128):
            with self.subTest(returncode=returncode), \
                    mock.patch.object(builder.subprocess, 'check_output', return_value=b''), \
                    mock.patch.object(builder.subprocess, 'run', side_effect=[self.repository, mock.Mock(returncode=returncode)]):
                with self.assertRaisesRegex(RuntimeError, 'to .gitignore'):
                    builder.ensure_ignored(['snapshots'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
