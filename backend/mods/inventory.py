"""Reconcile the InstalledMod table against the on-disk /mods + /plugins.

Two operations:

- :func:`scan` returns every .jar under both folders, marking which ones
  are tracked (the panel installed them) vs untracked (the user dropped
  them in via the file manager or copied from outside).

- :func:`enrich` joins ``InstalledMod`` rows with their on-disk presence
  so the UI can render an "installed but missing on disk" warning.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from django.conf import settings

from .models import InstalledMod


@dataclass
class JarFile:
    folder: str        # 'mods' | 'plugins'
    filename: str
    size: int


def _walk(folder: str) -> list[JarFile]:
    base = Path(settings.MC_DATA_PATH) / folder
    if not base.is_dir():
        return []
    out: list[JarFile] = []
    for p in base.iterdir():
        if not p.is_file() or p.suffix.lower() != ".jar":
            continue
        try:
            out.append(JarFile(folder=folder, filename=p.name, size=p.stat().st_size))
        except OSError:
            continue
    return sorted(out, key=lambda j: j.filename.lower())


def list_disk() -> list[JarFile]:
    return _walk("mods") + _walk("plugins")


def list_tracked() -> list[dict]:
    """Returned in the same shape the frontend cards expect."""
    rows = list(InstalledMod.objects.all().order_by("-installed_at"))
    disk_index = {(j.folder, j.filename) for j in list_disk()}

    out: list[dict] = []
    for r in rows:
        folder = "mods" if r.kind == "mod" else "plugins"
        out.append({
            "id": r.id,
            "provider": r.provider,
            "project_id": r.project_id,
            "project_slug": r.project_slug,
            "title": r.title,
            "icon_url": r.icon_url,
            "project_url": r.project_url,
            "version_id": r.version_id,
            "version_number": r.version_number,
            "filename": r.filename,
            "file_size": r.file_size,
            "kind": r.kind,
            "loader": r.loader,
            "mc_version": r.mc_version,
            "installed_at": r.installed_at.isoformat() if r.installed_at else None,
            "present_on_disk": (folder, r.filename) in disk_index,
        })
    return out


def list_untracked() -> list[dict]:
    """Files that exist on disk but weren't installed via the panel."""
    tracked = {
        ("mods" if r.kind == "mod" else "plugins", r.filename)
        for r in InstalledMod.objects.all()
    }
    return [asdict(j) for j in list_disk() if (j.folder, j.filename) not in tracked]
