from pathlib import Path


def materials_resolver(source_root, work_root):
    source = Path(source_root)
    central = Path(work_root)
    categories = {name.casefold(): name for name in ("Workspace", "Forme", "Snapshots", "Trash")}

    def resolve(project_root, category="Workspace", *, work_root=None):
        if category.casefold() == "installfiles":
            existing = [path for path in source.iterdir()
                        if path.name.casefold() == "installfiles"] if source.exists() else []
            if len(existing) > 1:
                raise RuntimeError("Ambiguous synthetic release directories")
            return existing[0] if existing else source / "installfiles"
        base = central if work_root is None else Path(work_root)
        return base / categories[category.casefold()] / source.name

    return resolve
