import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shutil


import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from project_materials import project_materials_root as _project_materials_root, confined_path



ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def migration_plan(previous, release):
    snapshots = _project_materials_root(ROOT, 'Snapshots')
    releases = _project_materials_root(ROOT, 'installfiles')
    previous = confined_path(previous, snapshots, error='Unsafe user-data migration path').resolve(strict=True)
    release = confined_path(release, releases, error='Unsafe user-data migration path').resolve(strict=True)
    if snapshots not in previous.parents:
        raise RuntimeError('The previous release must be a preserved project snapshot')
    if release.parent != releases:
        raise RuntimeError('The current release must be directly inside installfiles')
    manifest = json.loads(confined_path(previous / 'manifest.json', previous).read_text(encoding='utf-8'))['files']
    current_manifest = json.loads(confined_path(release / 'manifest.json', release).read_text(encoding='utf-8'))['files']
    plan = []
    disk = confined_path(previous / 'simdisk', previous)
    pending_config = disk / '.rockbox/config.cfg.new'
    pending_resume = disk / '.rockbox/.resume.cfg.new'
    for source in sorted(disk.rglob('*')):
        confined_path(source, previous, link_error='Refusing a user-data symlink or junction')
        if not source.is_file():
            continue
        relative = source.relative_to(previous).as_posix()
        if relative == 'simdisk/.rockbox/config.cfg' and pending_config.exists():
            continue
        if relative == 'simdisk/.rockbox/.resume.cfg' and pending_resume.exists():
            continue
        if manifest.get(relative) == digest(source):
            continue
        destination_relative = relative
        if relative in ('simdisk/.rockbox/config.cfg.new', 'simdisk/.rockbox/.resume.cfg.new'):
            destination_relative = relative[:-4]
        destination = confined_path(release / destination_relative, release)
        if previous not in source.resolve().parents or release not in destination.parents:
            raise RuntimeError('Unsafe user-data migration path')
        if destination.exists() and destination_relative not in (
                'simdisk/.rockbox/config.cfg', 'simdisk/.rockbox/.resume.cfg'):
            if digest(destination) != digest(source):
                raise RuntimeError(f'User data conflicts with a new package asset: {relative}')
            continue
        if destination.exists() and current_manifest.get(destination_relative) != digest(destination):
            raise RuntimeError(f'Refusing to replace an already modified profile: {destination}')
        plan.append((source, destination, digest(source)))
    return plan


def migrate(previous, release):
    plan = migration_plan(previous, release)
    release = release.resolve(strict=True)
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    report_path = confined_path(_project_materials_root(ROOT) / 'maintenance' / f'profile-migration-{timestamp}.json',
                               _project_materials_root(ROOT))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {'previous': str(previous), 'release': str(release), 'files': [], 'passed': False}
    print('Copying only user-owned data from the recovery snapshot; the snapshot remains intact.')
    try:
        for source, destination, expected in plan:
            confined_path(source, previous)
            confined_path(destination, release)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            if digest(destination) != expected:
                raise RuntimeError(f'User-data integrity failure: {destination}')
            report['files'].append({'source': str(source), 'destination': str(destination),
                                    'sha256': expected})
        for directory in (previous / 'simdisk').rglob('*'):
            confined_path(directory, previous)
            if directory.is_dir():
                destination = confined_path(release / directory.relative_to(previous), release)
                destination.mkdir(parents=True, exist_ok=True)
        report['passed'] = True
    finally:
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Preserved {len(plan)} user-data files; evidence: {report_path}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--previous', required=True, type=Path)
    parser.add_argument('--release', type=Path, default=_project_materials_root(ROOT, 'installfiles') / 'simwindows')
    arguments = parser.parse_args()
    from build_espeak_simulator import assert_not_running
    assert_not_running(arguments.release)
    assert_not_running(arguments.previous)
    migrate(arguments.previous, arguments.release)


if __name__ == '__main__':
    main()
