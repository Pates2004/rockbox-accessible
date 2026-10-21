import contextlib
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import project_materials as materials
import build_espeak_clipplus as native
import build_espeak_simulator as simulator
import migrate_espeak_simulator as migration
import test_tts_recorder_gui as recorder
import test_tts_targets as targets


ROOT = Path(__file__).resolve().parents[2]


class CentralPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        root = materials.project_materials_root(ROOT)
        cls.results = materials.confined_path(root / 'central-path-tests' / stamp, root)
        cls.results.mkdir(parents=True)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=self.results)
        self.addCleanup(temporary.cleanup)
        self.fixture = Path(temporary.name).resolve()
        self.source = self.fixture / 'source/rockbox'
        self.source.mkdir(parents=True)
        self.work = self.fixture / 'work'
        self.workspace = self.work / 'Workspace/rockbox'
        self.snapshots = self.work / 'Snapshots/rockbox'
        self.installfiles = self.source / 'installfiles'
        self.workspace.mkdir(parents=True)
        self.addCleanup(materials._windows_work_root.cache_clear)
        materials._windows_work_root.cache_clear()

    def patch(self, owner, attribute, *arguments, **keywords):
        patcher = mock.patch.object(owner, attribute, *arguments, **keywords)
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    def unix(self):
        self.patch(materials, 'os', types.SimpleNamespace(name='posix', environ={}))
        self.patch(materials.platform, 'release', return_value='generic-linux')

    def symlink(self, path, destination):
        try:
            path.symlink_to(destination, target_is_directory=destination.is_dir())
        except OSError as error:
            if os.name == 'nt' and getattr(error, 'winerror', None) == 1314:
                self.skipTest('Windows symlink privilege unavailable; WSL exercises this case')
            raise

    def builders(self):
        for builder in (native, simulator):
            self.patch(builder, 'ROOT', self.source)
            self.patch(builder, '_project_materials_root', side_effect=self.material_root)
            self.patch(builder, 'ensure_ignored')
        self.patch(native, 'assert_unused')
        self.patch(simulator, 'assert_not_running')

    def material_root(self, root, category='Workspace'):
        self.assertEqual(Path(root), self.source)
        categories = {name.lower(): name for name in ('Workspace', 'Forme', 'Snapshots', 'Trash')}
        if category.lower() == 'installfiles':
            return self.installfiles
        return self.work / categories[category.lower()] / self.source.name

    def test_d_drive_selection_does_not_depend_on_work_directory(self):
        self.assertEqual(materials._select_windows_drive(['C:\\', 'D:\\']), 'D:')
        self.assertEqual(materials._select_windows_drive(['d:\\', 'C:\\']), 'D:')
        self.assertEqual(materials._select_windows_drive(['C:\\']), 'C:')

    def test_invalid_drive_inventory_cannot_trigger_c_fallback(self):
        for inventory in (None, [], [''], ['D:/'], ['relative'], {'D:\\': True}):
            with self.subTest(inventory=inventory), self.assertRaisesRegex(RuntimeError, 'drive presence'):
                materials._select_windows_drive(inventory)

    def test_generic_unix_requires_explicit_external_configuration(self):
        self.unix()
        with self.assertRaisesRegex(RuntimeError, 'ROCKBOX_WORK_ROOT'):
            materials.project_materials_root(self.source)
        self.assertFalse((self.source / 'Workspace').exists())

    def test_generic_unix_explicit_parameter_and_environment(self):
        self.unix()
        self.assertEqual(materials.project_materials_root(self.source, work_root=self.work), self.workspace)
        materials.os.environ['ROCKBOX_WORK_ROOT'] = str(self.work)
        self.assertEqual(materials.project_materials_root(self.source), self.workspace)

    def test_categories_use_separate_canonical_roots(self):
        self.unix()
        for category in ('Workspace', 'Forme', 'Snapshots', 'Trash'):
            for alias in (category, category.lower(), category.upper()):
                with self.subTest(category=alias):
                    result = materials.project_materials_root(self.source, alias, work_root=self.work)
                    self.assertEqual(result, self.work / category / self.source.name)
                    self.assertIs(type(result), type(self.source))

    def test_invalid_categories_are_rejected_before_drive_lookup(self):
        query = self.patch(materials, '_windows_work_root')
        for category in (None, '', '../Workspace', 'Workspace/other', 'installfiles/..', Path('Workspace'), 'other'):
            with self.subTest(category=category), self.assertRaisesRegex(RuntimeError, 'category'):
                materials.project_materials_root(self.source, category)
        query.assert_not_called()

    def test_installfiles_is_local_without_work_configuration_or_directory_creation(self):
        self.unix()
        query = self.patch(materials, '_windows_work_root')
        self.assertEqual(materials.project_materials_root(self.source, 'installfiles'), self.installfiles)
        self.assertFalse(self.installfiles.exists())
        query.assert_not_called()

    def test_installfiles_preserves_existing_directory_case(self):
        directory = self.source / 'Installfiles'
        directory.mkdir()
        for category in ('installfiles', 'Installfiles', 'INSTALLFILES'):
            with self.subTest(category=category):
                self.assertEqual(materials.project_materials_root(self.source, category), directory)

    def test_installfiles_rejects_ambiguous_case_and_non_directory(self):
        with mock.patch.object(materials.Path, 'iterdir', return_value=iter((
                self.source / 'Installfiles', self.source / 'installfiles'))):
            with self.assertRaisesRegex(RuntimeError, 'Ambiguous'):
                materials.project_materials_root(self.source, 'installfiles')
        self.installfiles.write_bytes(b'not a directory')
        with self.assertRaisesRegex(RuntimeError, 'directory'):
            materials.project_materials_root(self.source, 'installfiles')

    def test_installfiles_rejects_a_link_instead_of_resolving_it(self):
        self.symlink(self.installfiles, self.workspace)
        with self.assertRaisesRegex(RuntimeError, 'link'):
            materials.project_materials_root(self.source, 'installfiles')

    def test_generic_unix_rejects_relative_and_source_nested_destinations(self):
        self.unix()
        for work in ('relative', self.source, self.source / 'nested-work'):
            with self.subTest(work=work), self.assertRaises(RuntimeError):
                materials.project_materials_root(self.source, work_root=work)

    def test_work_root_ancestor_is_allowed_when_destination_is_disjoint(self):
        self.unix()
        destination = self.source.parent / 'Workspace' / self.source.name
        self.assertEqual(materials.project_materials_root(self.source, work_root=self.source.parent), destination)
        self.assertFalse(destination.exists())

    def test_nested_rebuild_checkout_accepts_only_disjoint_category_destinations(self):
        self.unix()
        source = self.workspace / 'source-rebuild-test/rockbox'
        source.mkdir(parents=True)
        for category in ('Forme', 'Snapshots', 'Trash'):
            with self.subTest(category=category):
                self.assertEqual(materials.project_materials_root(source, category, work_root=self.work),
                                 self.work / category / source.name)
        with self.assertRaisesRegex(RuntimeError, 'overlap'):
            materials.project_materials_root(source, work_root=self.work)

    def test_nested_checkout_can_use_disjoint_default_workspace(self):
        self.unix()
        source = self.workspace / 'source-rebuild-test/checkout'
        source.mkdir(parents=True)
        self.assertEqual(materials.project_materials_root(source, work_root=self.work),
                         self.work / 'Workspace/checkout')

    def test_destination_equal_to_source_is_rejected(self):
        self.unix()
        with self.assertRaisesRegex(RuntimeError, 'overlap'):
            materials.project_materials_root(self.workspace, work_root=self.work)

    def test_unix_override_does_not_override_windows_drive_policy(self):
        self.patch(materials.platform, 'release', return_value='microsoft-standard-WSL2')
        self.patch(materials, '_windows_work_root', return_value=self.work)
        self.assertEqual(materials.project_materials_root(self.source, work_root=self.source), self.workspace)

    @unittest.skipIf(os.name == 'nt', 'WSL path syntax requires POSIX pathlib')
    def test_wsl_uses_windows_drive_inventory_and_existing_central_paths(self):
        self.unix()
        self.patch(materials.platform, 'release', return_value='microsoft-standard-WSL2')
        output = self.patch(materials.subprocess, 'check_output',
                            side_effect=[json.dumps(['C:\\', 'D:\\']), '/mnt/d/work\n'])
        self.assertEqual(materials.project_materials_root(Path('/mnt/d/Rockbox/rockbox')),
                         Path('/mnt/d/work/Workspace/rockbox'))
        self.assertEqual(output.call_args_list[1].args[0], ['wslpath', '-u', 'D:/work'])

    @unittest.skipIf(os.name == 'nt', 'WSL path syntax requires POSIX pathlib')
    def test_wsl_c_fallback_requires_missing_d_drive(self):
        self.unix()
        self.patch(materials.platform, 'release', return_value='microsoft-standard-WSL2')
        output = self.patch(materials.subprocess, 'check_output',
                            side_effect=[json.dumps('C:\\'), '/mnt/c/work\n'])
        self.assertEqual(materials.project_materials_root(self.source), Path('/mnt/c/work/Workspace/rockbox'))
        self.assertEqual(output.call_args_list[1].args[0], ['wslpath', '-u', 'C:/work'])

    @unittest.skipIf(os.name == 'nt', 'WSL drive query requires POSIX branch')
    def test_wsl_query_failure_does_not_fall_back_to_source_or_c(self):
        self.unix()
        self.patch(materials.platform, 'release', return_value='microsoft-standard-WSL2')
        output = self.patch(materials.subprocess, 'check_output',
                            side_effect=subprocess.CalledProcessError(1, 'powershell.exe'))
        with self.assertRaises(subprocess.CalledProcessError):
            materials.project_materials_root(self.source)
        self.assertEqual(output.call_count, 1)

    def test_windows_drive_query_failure_is_not_hidden(self):
        self.patch(materials, 'os', types.SimpleNamespace(name='nt', listdrives=mock.Mock(side_effect=PermissionError)))
        with self.assertRaises(PermissionError):
            materials.project_materials_root(self.source)

    @unittest.skipUnless(os.name == 'nt', 'Native Windows drive paths required')
    def test_native_windows_uses_d_without_testing_work_access(self):
        self.patch(materials.os, 'listdrives', return_value=['C:\\', 'D:\\'])
        self.patch(materials.Path, 'exists', side_effect=PermissionError('D: access denied'))
        self.assertEqual(materials._windows_work_root(), Path('D:/work'))

    @unittest.skipIf(os.name == 'nt', 'WSL drive mapping requires POSIX branch')
    def test_wsl_mapping_failure_cannot_fall_back_to_c(self):
        self.unix()
        self.patch(materials.platform, 'release', return_value='microsoft-standard-WSL2')
        output = self.patch(materials.subprocess, 'check_output', side_effect=[
            json.dumps(['C:\\', 'D:\\']), subprocess.CalledProcessError(1, 'wslpath')])
        with self.assertRaises(subprocess.CalledProcessError):
            materials.project_materials_root(self.source)
        self.assertEqual(output.call_count, 2)

    def test_confinement_accepts_central_children_and_rejects_roots_and_escape(self):
        child = self.workspace / 'build'
        self.assertEqual(materials.confined_path(child, self.workspace), child)
        for path in (self.workspace, self.work, self.workspace / '../other/build'):
            with self.subTest(path=path), self.assertRaisesRegex(RuntimeError, 'Unsafe project artifact'):
                materials.confined_path(path, self.workspace)

    def test_symlink_parent_into_allowed_tree_is_rejected(self):
        alias = self.fixture / 'alias'
        self.symlink(alias, self.workspace)
        with self.assertRaisesRegex(RuntimeError, 'Artifact path is a link'):
            materials.confined_path(alias / 'build', self.workspace)

    def test_symlink_to_outside_tree_is_rejected(self):
        self.symlink(self.workspace / 'linked', self.source)
        with self.assertRaisesRegex(RuntimeError, 'Artifact path is a link'):
            materials.confined_path(self.workspace / 'linked/build', self.workspace)
        self.assertFalse((self.source / 'build').exists())

    def test_linked_materials_root_is_rejected(self):
        self.unix()
        work = self.fixture / 'linked-work'
        self.symlink(work, self.work)
        with self.assertRaisesRegex(RuntimeError, 'Artifact path is a link'):
            materials.project_materials_root(self.source, work_root=work)

    def test_linked_project_root_is_rejected_before_resolving_its_name(self):
        self.unix()
        alias = self.fixture / 'linked-project'
        self.symlink(alias, self.source)
        with self.assertRaisesRegex(RuntimeError, 'link'):
            materials.project_materials_root(alias, work_root=self.work)

    def test_linked_category_root_is_rejected(self):
        self.unix()
        self.symlink(self.work / 'Snapshots', self.workspace)
        with self.assertRaisesRegex(RuntimeError, 'link'):
            materials.project_materials_root(self.source, 'Snapshots', work_root=self.work)

    @unittest.skipUnless(os.name == 'nt', 'Native Windows junction required')
    def test_windows_junction_parent_is_rejected(self):
        alias = self.workspace / 'junction'
        subprocess.run(['cmd', '/c', 'mklink', '/J', str(alias), str(self.source)],
                       capture_output=True, check=True)
        with self.assertRaisesRegex(RuntimeError, 'Artifact path is a link'):
            materials.confined_path(alias / 'build', self.workspace)
        self.assertEqual(list(self.source.iterdir()), [])

    @unittest.skipUnless(os.name != 'nt' and 'microsoft' in platform.release().lower(),
                         'WSL NTFS junction interop required')
    def test_wsl_ntfs_junction_parent_is_rejected(self):
        alias = self.workspace / 'junction'
        windows_alias = subprocess.check_output(['wslpath', '-w', str(alias)], text=True).strip()
        windows_source = subprocess.check_output(['wslpath', '-w', str(self.source)], text=True).strip()
        subprocess.run(['cmd.exe', '/c', 'mklink', '/J', windows_alias, windows_source],
                       capture_output=True, check=True)
        with self.assertRaisesRegex(RuntimeError, 'Artifact path is a link'):
            materials.confined_path(alias / 'build', self.workspace)
        self.assertEqual(list(self.source.iterdir()), [])

    def test_both_builders_preserve_local_releases_with_hashes_and_origin(self):
        self.builders()
        for builder, slug in ((native, 'clipzip'), (simulator, 'simwindows')):
            release = self.installfiles / slug
            release.mkdir(parents=True)
            (release / 'user-data.txt').write_bytes(b'synthetic user profile')
            with contextlib.redirect_stdout(io.StringIO()):
                archived = builder.preserve(release, slug)
            self.assertEqual(archived.relative_to(self.snapshots).parts[-2:], ('installfiles', slug))
            self.assertEqual((archived / 'user-data.txt').read_bytes(), b'synthetic user profile')
            record = json.loads((archived.parent.parent / 'preservation.json').read_text(encoding='utf-8'))
            self.assertEqual(record['original_path'], 'installfiles/' + slug)
            self.assertFalse(release.exists())
        self.assertFalse((self.source / 'snapshots').exists())

    def test_both_builders_preserve_central_builds_with_legacy_logical_paths(self):
        self.builders()
        for builder, name in ((native, 'native'), (simulator, 'simulator')):
            build = self.workspace / name
            build.mkdir()
            (build / 'build.log').write_bytes(b'synthetic central build')
            with contextlib.redirect_stdout(io.StringIO()):
                archived = builder.preserve(build, name)
            self.assertEqual(archived.relative_to(self.snapshots).parts[-2:], ('Workspace', name))
            self.assertEqual((archived / 'build.log').read_bytes(), b'synthetic central build')
            record = json.loads((archived.parent.parent / 'preservation.json').read_text(encoding='utf-8'))
            self.assertEqual(record['original_path'], 'Workspace/' + name)
            self.assertFalse(build.exists())

    def test_both_builders_preserve_installfiles_case_in_snapshot_origin(self):
        self.installfiles = self.source / 'Installfiles'
        self.builders()
        for builder, slug in ((native, 'clipzip'), (simulator, 'simwindows')):
            release = self.installfiles / slug
            release.mkdir(parents=True)
            (release / 'user-data.txt').write_bytes(b'synthetic user profile')
            with contextlib.redirect_stdout(io.StringIO()):
                archived = builder.preserve(release, slug)
            self.assertEqual(archived.relative_to(self.snapshots).parts[-2:], ('Installfiles', slug))
            record = json.loads((archived.parent.parent / 'preservation.json').read_text(encoding='utf-8'))
            self.assertEqual(record['original_path'], 'Installfiles/' + slug)

    def test_new_preservation_does_not_rewrite_legacy_frozen_snapshot(self):
        self.builders()
        frozen = self.snapshots / 'legacy-frozen'
        frozen.mkdir(parents=True)
        original = b'{"original_path":"installfiles/simwindows","role":"legacy-label","files":{}}\n'
        (frozen / 'preservation.json').write_bytes(original)
        (frozen / 'source.tar').write_bytes(b'synthetic immutable corresponding sources')
        for builder, slug in ((native, 'clipzip'), (simulator, 'simwindows')):
            release = self.installfiles / slug
            release.mkdir(parents=True)
            (release / 'user-data.txt').write_bytes(b'synthetic user profile')
            with contextlib.redirect_stdout(io.StringIO()):
                builder.preserve(release, slug)
        self.assertEqual((frozen / 'preservation.json').read_bytes(), original)
        self.assertEqual((frozen / 'source.tar').read_bytes(), b'synthetic immutable corresponding sources')

    def test_both_builders_preserve_legacy_build_into_central_snapshots(self):
        self.builders()
        for builder, name in ((native, 'native'), (simulator, 'simulator')):
            build = self.source / 'Workspace' / name
            build.mkdir(parents=True)
            (build / 'build.log').write_bytes(b'synthetic legacy build')
            with contextlib.redirect_stdout(io.StringIO()):
                archived = builder.preserve(build, name)
            self.assertEqual(archived.relative_to(self.snapshots).parts[-2:], ('Workspace', name))
        self.assertFalse((self.source / 'snapshots').exists())

    def test_both_builders_reject_category_roots_and_other_projects(self):
        self.builders()
        for builder in (native, simulator):
            for path in (self.source, self.workspace, self.snapshots, self.installfiles,
                         self.work / 'Workspace', self.work / 'Workspace/other/build',
                         self.workspace / '../other/build'):
                with self.subTest(builder=builder.__name__, path=path), self.assertRaises(RuntimeError):
                    builder.preserve(path, 'recursive')
        self.assertFalse(self.snapshots.exists())

    def test_both_builders_reject_unsafe_labels_without_archiving(self):
        self.builders()
        build = self.workspace / 'build'
        build.mkdir()
        for builder in (native, simulator):
            for label in ('../escape', '', 'nested/label'):
                with self.subTest(builder=builder.__name__, label=label):
                    with self.assertRaisesRegex(RuntimeError, 'Unsafe snapshot label'):
                        builder.preserve(build, label)
        self.assertEqual(list(build.iterdir()), [])
        self.assertFalse(self.snapshots.exists())

    def test_absent_legacy_directories_do_not_require_source_ignore_patterns(self):
        self.patch(simulator, 'ROOT', self.source)
        self.patch(simulator, '_project_materials_root', side_effect=self.material_root)
        check = self.patch(simulator, 'ensure_ignored_directories')
        simulator.ensure_ignored(['Workspace', 'snapshots'])
        self.assertEqual(check.call_args_list, [mock.call(self.workspace.parent, [self.source.name]),
                                               mock.call(self.snapshots.parent, [self.source.name])])

    def test_existing_legacy_directories_are_still_checked(self):
        self.patch(native, '_project_materials_root', side_effect=self.material_root)
        (self.source / 'Workspace').mkdir()
        check = self.patch(native, 'ensure_ignored_directories')
        native.ensure_ignored(self.source, ['Workspace', 'snapshots'])
        self.assertEqual(check.call_args_list, [mock.call(self.source, ['Workspace']),
                                               mock.call(self.workspace.parent, [self.source.name]),
                                               mock.call(self.snapshots.parent, [self.source.name])])

    def test_local_installfiles_git_check_is_required_even_before_creation(self):
        for builder in (native, simulator):
            with self.subTest(builder=builder.__name__):
                with mock.patch.object(builder, 'ROOT', self.source), \
                        mock.patch.object(builder, '_project_materials_root', side_effect=self.material_root), \
                        mock.patch.object(builder, 'ensure_ignored_directories') as check:
                    if builder is native:
                        builder.ensure_ignored(self.source, ['installfiles'])
                    else:
                        builder.ensure_ignored(['installfiles'])
                check.assert_called_once_with(self.source, ['installfiles'])

    def test_central_materials_outside_git_do_not_require_ignore_patterns(self):
        run = self.patch(materials.subprocess, 'run', return_value=mock.Mock(
            returncode=128, stderr='fatal: not a git repository (or any of the parent directories): .git'))
        tracked = self.patch(materials.subprocess, 'check_output')
        materials.ensure_ignored_directories(self.snapshots.parent, [self.source.name])
        tracked.assert_not_called()
        self.assertEqual(run.call_count, 1)

    def test_git_inspection_failure_is_not_treated_as_no_repository(self):
        self.patch(materials.subprocess, 'run', return_value=mock.Mock(returncode=128, stderr='permission denied'))
        with self.assertRaisesRegex(RuntimeError, 'Cannot inspect'):
            materials.ensure_ignored_directories(self.snapshots.parent, [self.source.name])

    def test_central_git_checks_use_actual_relative_path_and_no_index(self):
        run = self.patch(materials.subprocess, 'run', side_effect=[
            mock.Mock(returncode=0, stdout=str(self.work)), mock.Mock(returncode=0)])
        tracked = self.patch(materials.subprocess, 'check_output', return_value=b'')
        materials.ensure_ignored_directories(self.snapshots.parent, [self.source.name])
        self.assertEqual(tracked.call_args.args[0][-1], 'Snapshots/rockbox')
        self.assertEqual(run.call_args.args[0][-2:], ['--', 'Snapshots/rockbox/'])
        self.assertIn('--no-index', run.call_args.args[0])

    def test_gui_helper_accepts_central_workspace_but_confines_fixture_roots(self):
        self.patch(recorder, 'ROOT', self.source)
        self.patch(recorder, '_project_materials_root', side_effect=self.material_root)
        workspace = self.workspace / 'fixture'
        workspace.mkdir()
        self.assertEqual(recorder.contained(workspace, self.source), workspace)
        with self.assertRaisesRegex(RuntimeError, 'escapes'):
            recorder.contained(self.source, workspace)

    def test_target_report_evidence_resolves_separate_category_roots(self):
        self.patch(targets, 'ROOT', self.source)
        self.patch(targets, '_project_materials_root', side_effect=self.material_root)
        for category, name in (('Workspace', 'run/result.log'), ('Snapshots', 'previous/rockboxui')):
            path = self.material_root(self.source, category) / name
            path.parent.mkdir(parents=True)
            path.write_bytes(b'synthetic evidence')
            record = {'path': category + '/' + name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            self.assertEqual(targets.verify_evidence(record), path)
        with self.assertRaisesRegex(RuntimeError, 'Unsafe diagnostic evidence reference'):
            targets.verify_evidence({'path': '../elsewhere', 'sha256': ''})

    def test_migration_rejects_linked_source_before_profile_copy(self):
        self.patch(migration, 'ROOT', self.source)
        self.patch(migration, '_project_materials_root', side_effect=self.material_root)
        previous = self.snapshots / 'previous'
        release = self.installfiles / 'simwindows'
        for directory in (previous, release):
            directory.mkdir(parents=True)
            (directory / 'manifest.json').write_text('{"files": {}}', encoding='utf-8')
        self.symlink(previous / 'simdisk', self.source)
        before = list(self.source.iterdir())
        with self.assertRaisesRegex(RuntimeError, 'link'):
            migration.migration_plan(previous, release)
        self.assertEqual(list(self.source.iterdir()), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
