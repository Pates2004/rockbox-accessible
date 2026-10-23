import argparse
import base64
import datetime
import hashlib
import json
import ntpath
import os
from pathlib import Path
import re
import shutil
import subprocess


import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from project_materials import project_materials_root as _project_materials_root, confined_path, ensure_ignored_directories



ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib/espeak'))
from data_provenance import validate_packaged_data, validate_supplied_data

ENGINE_REVISION = "a14831fd3af6b3df77ef23b854cd05ee05b12851"
TARGETS = {"sansaclipplus": ("clipplus", "Clip+"),
           "sansaclipzip": ("clipzip", "Clip Zip"),
           "hibyr1": ("hibyr1", "HiBy R1")}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contained(path):
    roots = tuple(_project_materials_root(ROOT, category)
                  for category in ("Workspace", "Snapshots", "installfiles"))
    resolved = confined_path(path, ROOT, *roots)
    if resolved in roots:
        raise RuntimeError(f"Artifact path must not be a material root: {resolved}")
    return resolved


def tree_inventory(directory):
    directory = contained(directory)
    entries = {}
    for item in sorted(directory.rglob("*")):
        confined_path(item, directory)
        if not item.is_file() and not item.is_dir():
            raise RuntimeError(f"Non-regular artifact: {item}")
        entries[item.relative_to(directory).as_posix()] = digest(item) if item.is_file() else None
    return entries


def ensure_ignored(names):
    for name in names:
        directory = _project_materials_root(ROOT, name)
        legacy = ROOT / name
        if legacy.exists() and legacy != directory:
            ensure_ignored_directories(ROOT, [name])
        ensure_ignored_directories(directory.parent, [directory.name])


def assert_not_running(path):
    resolved = path.resolve()
    if resolved.suffix.lower() == '.exe':
        assert_windows_not_running(resolved)
    for process in Path("/proc").iterdir():
        if not process.name.isdigit():
            continue
        try:
            if process.stat().st_uid != os.getuid():
                continue
            links = [process / "exe", process / "cwd", *list((process / "fd").iterdir())]
            for link in links:
                try:
                    target = link.resolve(strict=True)
                except (FileNotFoundError, ProcessLookupError):
                    continue
                if target == resolved or resolved in target.parents:
                    raise RuntimeError(f"Process {process.name} is using {resolved}")
        except (FileNotFoundError, ProcessLookupError):
            continue
    if resolved.is_dir() and 'microsoft' in Path('/proc/sys/kernel/osrelease').read_text().lower():
        assert_windows_unused(resolved)


def assert_windows_unused(path):
    windows_path = subprocess.check_output(['wslpath', '-w', str(path)], text=True).strip()
    if not ntpath.isabs(windows_path):
        raise RuntimeError('Cannot resolve the native artifact path')
    payload = base64.b64encode(windows_path.encode('utf-8')).decode('ascii')
    script = r'''
$ErrorActionPreference = 'Stop'
$target = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('PAYLOAD'))
$target = [IO.Path]::GetFullPath($target).TrimEnd('\')
foreach ($process in Get-CimInstance Win32_Process) {
    if (($process.ExecutablePath -and ($process.ExecutablePath -eq $target -or
        $process.ExecutablePath.StartsWith($target + '\', [StringComparison]::OrdinalIgnoreCase))) -or
        ($process.CommandLine -and $process.CommandLine.IndexOf($target, [StringComparison]::OrdinalIgnoreCase) -ge 0)) {
        throw "A Windows process uses $target"
    }
}
foreach ($file in Get-ChildItem -LiteralPath $target -File -Recurse -Force) {
    $handle = [IO.File]::Open($file.FullName, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::None)
    $handle.Dispose()
}
'''.replace('PAYLOAD', payload)
    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded], check=True)


def assert_windows_not_running(path):
    script = "$ErrorActionPreference = 'Stop'; [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); @(Get-CimInstance Win32_Process -Filter \"Name = 'rockboxui.exe'\" | ForEach-Object { if (-not $_.ExecutablePath) { throw 'Cannot inspect simulator executable path' }; $_.ExecutablePath }) | ConvertTo-Json -Compress"
    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    listing = subprocess.check_output(['powershell.exe', '-NoProfile', '-NonInteractive',
                                      '-EncodedCommand', encoded], text=True, encoding='utf-8')
    running = json.loads(listing) if listing.strip() else []
    if isinstance(running, str):
        running = [running]
    if not isinstance(running, list) or any(not isinstance(item, str) or not item for item in running):
        raise RuntimeError('Cannot validate native simulator process paths')
    target = subprocess.check_output(['wslpath', '-w', str(path)], text=True).strip()
    if not ntpath.isabs(target):
        raise RuntimeError('Cannot resolve the native artifact path')
    target = ntpath.normcase(ntpath.normpath(target)).rstrip('\\')
    for executable in running:
        if not ntpath.isabs(executable):
            raise RuntimeError('Cannot validate a native simulator executable path')
        executable = ntpath.normcase(ntpath.normpath(executable))
        if executable == target or executable.startswith(target + '\\'):
            raise RuntimeError(f'Close the native simulator using {path} before replacing its files')


def preserve(path, label):
    path = contained(path)
    if not path.exists():
        return
    if not path.is_dir():
        raise RuntimeError(f"Expected an artifact directory: {path}")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", label):
        raise RuntimeError(f"Unsafe snapshot label: {label}")
    for category in ("Workspace", "Snapshots", "installfiles"):
        directory = _project_materials_root(ROOT, category)
        if path.is_relative_to(directory):
            prefix = directory.name if category == "installfiles" else category
            relative = Path(prefix) / path.relative_to(directory)
            break
    else:
        relative = path.relative_to(ROOT.resolve())
    before = tree_inventory(path)
    assert_not_running(path)
    ensure_ignored(["snapshots"])
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    snapshot = contained(_project_materials_root(ROOT, "Snapshots") / f"{label}-{timestamp}")
    destination = contained(snapshot / relative)
    if snapshot == path or path in snapshot.parents:
        raise RuntimeError(f"Snapshot must be outside the archived directory: {path}")
    snapshot.mkdir(parents=True, exist_ok=False)
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"Moving previous {label} (not copying): {path} -> {destination}", flush=True)
    shutil.move(str(path), str(destination))
    if tree_inventory(destination) != before:
        raise RuntimeError(f"Snapshot integrity failure: {destination}")
    (snapshot / "preservation.json").write_text(json.dumps({
        "original_path": relative.as_posix(), "role": label, "entries": before,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return destination


def run(command, directory, log, environment):
    print("Running: " + " ".join(str(value) for value in command), flush=True)
    with log.open("w", encoding="utf-8") as stream:
        subprocess.run(command, cwd=directory, env=environment, stdout=stream,
                       stderr=subprocess.STDOUT, check=True)


def validate_build_target(build, target):
    for name, pattern in (("Makefile", r"^export MODELNAME\s*=\s*(\S+)\s*$"),
                          ("rockbox-info.txt", r"^Target:\s*(\S+)\s*$")):
        path = build / name
        if not path.is_file():
            raise RuntimeError(f"Cannot verify simulator build target: missing {path}")
        matches = re.findall(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
        if matches != [target]:
            raise RuntimeError(f"Simulator build target mismatch in {path}: expected {target}, found {matches}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=min(os.cpu_count() or 2, 12))
    parser.add_argument("--platform", choices=("linux", "windows"), default="windows")
    parser.add_argument("--target", choices=tuple(TARGETS), default="sansaclipplus")
    parser.add_argument("--sdl-sdk", type=Path,
                        default=_project_materials_root(ROOT) / "toolchains/SDL2-2.32.10/x86_64-w64-mingw32")
    parser.add_argument("--espeak-source", type=Path, default=ROOT.parent / "espeak-1.44.05-source")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--build-only", action="store_true")
    mode.add_argument("--package-only", action="store_true")
    arguments = parser.parse_args()
    if arguments.jobs < 1:
        parser.error("--jobs must be positive")
    source = arguments.espeak_source.resolve()
    provenance = validate_supplied_data(source) if arguments.target == "hibyr1" else None
    ensure_ignored(["Workspace", "installfiles"])
    windows = arguments.platform == "windows"
    target_slug, target_name = TARGETS[arguments.target]
    suffix = "" if arguments.target == "sansaclipplus" else f"-{target_slug}"
    release = contained(_project_materials_root(ROOT, "installfiles") / (f"simwindows{suffix}" if windows else f"{target_slug}-espeak-simulator"))
    if release.exists() and not arguments.build_only:
        raise RuntimeError("An installed simulator already exists. Preserve it with its user data in snapshots before repackaging; the new release must use clean defaults.")
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if revision != ENGINE_REVISION:
        raise RuntimeError(f"Expected supplied eSpeak revision {ENGINE_REVISION}, found {revision}")
    data = source / "espeak-data"
    if not (data / "phondata").is_file() or not (data / "pl_dict").is_file():
        raise RuntimeError("The supplied eSpeak data is incomplete")
    build_name = "build-espeak-windows" if windows else ("build-espeak-simulator" if suffix else "build-espeak")
    build = contained(_project_materials_root(ROOT) / (build_name + suffix))
    executable = build / ("rockboxui.exe" if windows else "rockboxui")
    version = "0ed3734e5e-espeak-r29-" + ("win-" if windows else "") + "alpha7-20261011"
    if arguments.target == "sansaclipzip":
        version = "0ed3734e5e-espeak-r29-clipzip-" + ("win-" if windows else "") + "alpha8-20261011"
    elif arguments.target == "hibyr1":
        version = "0ed3734e5e-espeak-r34-hibyr1-" + ("win-alpha18-20261023" if windows else "alpha15-20261023")
    environment = dict(os.environ, OMP_NUM_THREADS=str(arguments.jobs), VERSION=version)
    sdk = arguments.sdl_sdk.resolve()
    if windows:
        if not (sdk / 'bin/sdl2-config').is_file() or not (sdk / 'lib/libSDL2.a').is_file():
            raise RuntimeError('The Windows x64 SDL2 development SDK is missing; see docs/ESPEAK-WINDOWS-PL.md')
        sdk_version = subprocess.check_output([str(sdk / 'bin/sdl2-config'), '--version'], text=True).strip()
        if sdk_version != '2.32.10' or not (sdk.parent / 'LICENSE.txt').is_file():
            raise RuntimeError('Use the validated SDL2 2.32.10 SDK with its LICENSE.txt')
        environment['PATH'] = str(sdk / 'bin') + os.pathsep + environment['PATH']
        environment['CXX'] = 'x86_64-w64-mingw32-g++'
    if not arguments.package_only:
        preserve(build, f"{target_slug}-windows-development" if windows else f"{target_slug}-development")
        build.mkdir(parents=True, exist_ok=True)
        configuration_arguments = ["bash", str(ROOT / "tools" / "configure"), f"--target={arguments.target}",
                                   "--type=as6" if windows else "--type=s", "--integrated-espeak"]
        if not windows:
            configuration_arguments.append("--sdl-threads")
        run(configuration_arguments, build, build / "configure.log", environment)
        run(["make", f"-j{arguments.jobs}"], build, build / "build.log", environment)
    if arguments.build_only:
        if provenance is not None and validate_supplied_data(source) != provenance:
            raise RuntimeError("Supplied eSpeak data changed during R1 simulator compilation")
        return
    if provenance is not None and validate_supplied_data(source) != provenance:
        raise RuntimeError("Supplied eSpeak data changed before R1 simulator packaging")
    validate_build_target(build, arguments.target)
    assert_not_running(executable)
    symbols = subprocess.check_output(["x86_64-w64-mingw32-nm" if windows else "nm", str(executable)], text=True)
    if " rb_espeak_synth\n" not in symbols or " tts_speak\n" not in symbols:
        raise RuntimeError("The executable does not contain the integrated speech engine")
    disk = release / "simdisk"
    disk.mkdir(parents=True)
    run(["make", "fullinstall", f"RBPREFIX={disk}"], build, build / "install.log", environment)
    destination_data = disk / ".rockbox" / "espeak-data"
    print(f"Installing the exact engine data as a required runtime copy: {destination_data}", flush=True)
    shutil.copytree(data, destination_data)
    languages = disk / ".rockbox" / "langs"
    for catalog in (build / "apps" / "lang").glob("*.vstrings"):
        shutil.copy2(catalog, languages / catalog.name)
    if not windows:
        shutil.copy2(ROOT / "tools" / "run-espeak-simulator.sh", release / "launch.sh")
        shutil.copy2(ROOT / "tools" / "run-espeak-simulator.cmd", release / "Uruchom.cmd")
    shutil.copy2(build / "UI256.bmp", release / "UI256.bmp")
    shutil.copy2(ROOT / "lib" / "espeak" / "License.txt", release / "eSpeak-LICENSE.txt")
    shutil.copy2(ROOT / "lib/espeak/sonic/LICENSE", release / "Sonic-LICENSE.txt")
    shutil.copy2(ROOT / "lib/espeak/sonic/README.md", release / "Sonic-PROVENANCE.md")
    polish_guide = "ESPEAK-HIBYR1-PL.md" if arguments.target == "hibyr1" else (
        "ESPEAK-WINDOWS-PL.md" if windows else "ESPEAK-PL.md")
    shutil.copy2(ROOT / "docs" / polish_guide, release / "CZYTAJ.md")
    if windows:
        english_guide = "ESPEAK-HIBYR1.md" if arguments.target == "hibyr1" else "ESPEAK-WINDOWS.md"
        shutil.copy2(ROOT / "docs" / english_guide, release / "README.md")
        shutil.copy2(sdk.parent / "LICENSE.txt", release / "SDL2-LICENSE.txt")
        for name in ("ESPEAK.md", "ESPEAK-PL.md", "ESPEAK-TARGETS.md", "ESPEAK-TARGETS-PL.md",
                     "ESPEAK-PLUGINS.md", "ESPEAK-PLUGINS-PL.md",
                     "ESPEAK-BOOKMARKS.md", "ESPEAK-BOOKMARKS-PL.md",
                     f"ESPEAK-{target_slug.upper()}.md", f"ESPEAK-{target_slug.upper()}-PL.md"):
            shutil.copy2(ROOT / "docs" / name, release / name)
        if arguments.target == "hibyr1":
            for name in ("HIBY-R1-CONTROLS.md", "HIBY-R1-CONTROLS-PL.md",
                         "HIBY-R1-INSTALL.md", "HIBY-R1-INSTALL-PL.md",
                         "ACCESSIBILITY-TOUCH.md", "ACCESSIBILITY-TOUCH-PL.md",
                         "ACCESSIBILITY-BUTTONS.md", "ACCESSIBILITY-BUTTONS-PL.md",
                         "ACCESSIBILITY-TYPING.md", "ACCESSIBILITY-TYPING-PL.md",
                         "ESPEAK-ROCKBOX.md", "ESPEAK-ROCKBOX-PL.md",
                         "ACCESSIBILITY-LISTS.md", "ACCESSIBILITY-LISTS-PL.md",
                         "ACCESSIBILITY-SCREEN.md", "ACCESSIBILITY-SCREEN-PL.md",
                         "ACCESSIBILITY-SHORTCUT.md", "ACCESSIBILITY-SHORTCUT-PL.md",
                         "HIBY-R1-CONNECTIVITY.md", "HIBY-R1-CONNECTIVITY-PL.md",
                         "ACCESSIBILITY-CURTAIN.md", "ACCESSIBILITY-CURTAIN-PL.md",
                         "INTERFACE-APPEARANCE.md", "INTERFACE-APPEARANCE-PL.md",
                         "HIBY-R1-POWER.md", "HIBY-R1-POWER-PL.md",
                         "HIBY-R1-NETWORK-EMULATION.md", "HIBY-R1-NETWORK-EMULATION-PL.md",
                         "ESPEAK-BLUETOOTH.md", "ESPEAK-BLUETOOTH-PL.md",
                         "ESPEAK-HIBY-USB.md", "ESPEAK-HIBY-USB-PL.md",
                         "RADIO-DYNAMIC.md", "RADIO-DYNAMIC-PL.md"):
                shutil.copy2(ROOT / "docs" / name, release / name)
    configuration = disk / ".rockbox" / "config.cfg"
    configuration.write_text("lang: /.rockbox/langs/polski.lng\ntalk menu: on\ntalk dir: spell\n"
                             "talk file: spell\ntalk dir clip: off\ntalk file clip: off\n"
                             "tts enabled: on\ntts language: system\ntts variant: \ntts rate: 175\n"
                             "tts rate scale: percent\ntts punctuation: none\n"
                             "tts ducking: on\ntts ducking level: 25\n"
                             "tts pitch: 50\ntts volume: 100\ntts range: 50\ntts wordgap: 0\n"
                             "volume: -25\n", encoding="utf-8")
    imports = []
    if windows:
        headers = subprocess.check_output(['x86_64-w64-mingw32-objdump', '-p', str(executable)], text=True)
        imports = sorted(set(re.findall(r'DLL Name:\s+(\S+)', headers)))
        system_libraries = {'advapi32.dll', 'comdlg32.dll', 'dinput8.dll', 'dsound.dll',
            'gdi32.dll', 'imm32.dll', 'kernel32.dll', 'msvcrt.dll', 'ole32.dll',
            'oleaut32.dll', 'setupapi.dll', 'shell32.dll', 'user32.dll', 'version.dll',
            'winmm.dll', 'ws2_32.dll'}
        unexpected = [name for name in imports if name.lower() not in system_libraries]
        if unexpected:
            raise RuntimeError(f'Unpackaged non-system Windows dependencies: {unexpected}')
    if provenance is not None:
        if validate_supplied_data(source) != provenance:
            raise RuntimeError("Supplied eSpeak data changed before R1 simulator publication")
        runtime_data = {item.relative_to(destination_data).as_posix(): digest(item)
                        for item in sorted(destination_data.rglob("*")) if item.is_file()}
        validate_packaged_data(provenance, runtime_data)
    shutil.move(str(executable), str(release / executable.name))
    files = {item.relative_to(release).as_posix(): digest(item)
             for item in sorted(release.rglob("*")) if item.is_file()}
    (release / "manifest.json").write_text(json.dumps({"engine_revision": revision,
        "sonic_revision": "fbf75c3d6d846bad3bb3d456cbc5d07d9fd8c104",
        "version": environment["VERSION"], "plugin_abi": 0xe006,
        "rockbox_revision": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
        "target": arguments.target,
        "kind": f"Native Windows x64 {target_name} simulator; not device firmware" if windows else f"Linux/WSL {target_name} simulator; not device firmware",
        "windows_system_imports": imports, "files": files,
        **({"espeak_data_provenance": provenance} if provenance is not None else {})},
        indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Simulator ready for validation: {release}", flush=True)


if __name__ == "__main__":
    main()
