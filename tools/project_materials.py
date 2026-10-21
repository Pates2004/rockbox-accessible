import functools
import json
import os
from pathlib import Path
import platform
import subprocess


def confined_path(path, *roots, allow_root=False,
                  error="Unsafe project artifact path", link_error="Artifact path is a link"):
    path = Path(path).absolute()
    for candidate in (path, *map(Path, roots)):
        for component in (candidate, *candidate.parents):
            if component.is_symlink() or (hasattr(component, "is_junction") and component.is_junction()):
                raise RuntimeError(f"{link_error}: {component}")
    resolved = path.resolve()
    if not any(root.resolve() in resolved.parents or allow_root and resolved == root.resolve()
               for root in map(Path, roots)):
        raise RuntimeError(f"{error}: {resolved}")
    return resolved


@functools.lru_cache(maxsize=1)
def _windows_work_root():
    if os.name == "nt":
        drives = os.listdrives()
    else:
        listing = subprocess.check_output([
            "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
            "[System.IO.Directory]::GetLogicalDrives() | ConvertTo-Json -Compress",
        ], text=True, encoding="utf-8")
        drives = json.loads(listing)
        if isinstance(drives, str):
            drives = [drives]
    drive = _select_windows_drive(drives)
    if os.name == "nt":
        return Path(drive + "/work")
    mapped = subprocess.check_output(["wslpath", "-u", drive + "/work"], text=True).strip()
    if not mapped or not Path(mapped).is_absolute():
        raise RuntimeError("Cannot map the central Windows work directory into WSL")
    return Path(mapped)


def _select_windows_drive(drives):
    if not isinstance(drives, list) or not drives or any(
            not isinstance(drive, str) or len(drive) != 3 or drive[1:] != ":\\"
            or not drive[0].isascii() or not drive[0].isalpha() for drive in drives):
        raise RuntimeError("Cannot determine Windows drive presence")
    return "D:" if any(item.upper() == "D:\\" for item in drives) else "C:"


def project_materials_root(project_root, category="Workspace", *, work_root=None):
    """Select a project category; current installfiles stay in the source project."""
    categories = {name.lower(): name for name in ("Workspace", "Forme", "Snapshots", "Trash", "installfiles")}
    if not isinstance(category, str) or category.lower() not in categories:
        raise RuntimeError(f"Unknown project material category: {category!r}")
    category = categories[category.lower()]
    source = confined_path(project_root, project_root, allow_root=True)
    if not source.name:
        raise RuntimeError("Project root must name a project directory")
    if category == "installfiles":
        try:
            matches = [path for path in source.iterdir() if path.name.lower() == category]
        except FileNotFoundError:
            matches = []
        if len(matches) > 1:
            raise RuntimeError(f"Ambiguous installfiles directory casing in {source}")
        destination = confined_path(matches[0] if matches else source / category, source)
        if destination.exists() and not destination.is_dir():
            raise RuntimeError(f"Expected an installfiles directory: {destination}")
        return destination
    if os.name == "nt" or "microsoft" in platform.release().lower():
        base = _windows_work_root()
    else:
        configured = work_root if work_root is not None else os.environ.get("ROCKBOX_WORK_ROOT")
        if not configured or not Path(configured).is_absolute():
            raise RuntimeError("Native Unix requires an absolute ROCKBOX_WORK_ROOT or work_root parameter")
        base = Path(configured)
    category_root = confined_path(base / category, base)
    destination = confined_path(category_root / source.name, category_root)
    if destination == source or source in destination.parents or destination in source.parents:
        raise RuntimeError(f"Central materials must not overlap the source project: {destination}")
    return destination


def ensure_ignored_directories(materials_root, names):
    materials_root = Path(materials_root)
    existing = next(path for path in (materials_root, *materials_root.parents) if path.exists())
    repository = subprocess.run(["git", "-C", str(existing), "rev-parse", "--show-toplevel"],
                                capture_output=True, text=True)
    if repository.returncode:
        if repository.returncode == 128 and "not a git repository" in repository.stderr:
            return
        raise RuntimeError(f"Cannot inspect central materials Git repository: {repository.stderr}")
    root = Path(repository.stdout.strip()).resolve()
    confined_path(materials_root, root, allow_root=True)
    for name in names:
        directory = confined_path(materials_root / name, materials_root)
        relative = directory.relative_to(root).as_posix()
        tracked = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z", "--", relative])
        if tracked:
            raise RuntimeError(f"{name} has tracked files; resolve the index before building")
        ignored = subprocess.run(["git", "-C", str(root), "check-ignore", "--no-index", "-q", "--", relative + "/"])
        if ignored.returncode != 0:
            raise RuntimeError(f"Add /{relative}/ to .gitignore before building")
