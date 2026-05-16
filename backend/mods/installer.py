"""Download + place a mod/plugin file into the Minecraft data dir.

Validation:
- The download URL must come from the provider's known download host
  (Modrinth's CDN or Hangar). We refuse anything else to avoid SSRF.
- We stream + size-cap the download (50 MB) to avoid disk-fill DoS.
- We verify the file hash against what the provider advertised, when one
  is available (Modrinth → sha512, Hangar → sha256). When the hash is
  absent, we accept the file but record that the install was unverified.
- The destination filename is the basename of what the provider gave us.
  We refuse anything that contains slashes / null / backslashes.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import requests
from django.conf import settings

from .loader import Target, detect
from .models import InstalledMod
from .providers import ProviderError, VersionInfo, hangar, modrinth

log = logging.getLogger(__name__)

MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB
DOWNLOAD_TIMEOUT = 60

ALLOWED_HOSTS = (
    "cdn.modrinth.com",
    "cdn-raw.modrinth.com",
    "hangar.papermc.io",
    "hangarcdn.papermc.io",
    "papermc.io",
)


class InstallError(Exception):
    pass


@dataclass
class InstallResult:
    record: InstalledMod
    bytes_written: int
    verified: bool


def install(provider: str, project_id: str, version_id: str | None = None) -> InstallResult:
    target = detect()
    if target.kind not in ("mod", "plugin"):
        raise InstallError(
            f"Server type ‘{target.loader_label}’ doesn't accept mods or plugins."
        )

    try:
        version = _pick_version(provider, project_id, version_id, target)
    except _NoCompatVersion as exc:
        raise InstallError(str(exc)) from exc
    if version is None:
        raise InstallError(
            "No version available for this project."
        )

    # Modpacks ship as .mrpack archives that need a separate installer
    # (extract index, fetch each declared mod, apply overrides). Refuse
    # them here so users can't trigger a half-broken install — they can
    # still browse via the search UI and follow the project link.
    if version.filename.lower().endswith(".mrpack"):
        raise InstallError(
            "Modpack install is not supported yet. Open the project on Modrinth "
            "to follow the recommended setup, or install the underlying mods individually."
        )

    _validate_url(version.file_url)
    _validate_filename(version.filename)

    blob, written = _download(version.file_url)
    if version.file_hash and version.hash_algo:
        _verify_hash(blob, version.file_hash, version.hash_algo)
        verified = True
    else:
        verified = False

    dest_dir = Path(settings.MC_DATA_PATH) / target.folder
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / version.filename

    # Atomic-ish write: stage, then rename
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(blob)
    tmp.replace(dest)

    record = _upsert_record(provider, version, target, project_id)

    return InstallResult(record=record, bytes_written=written, verified=verified)


def uninstall(record_id: int) -> str:
    """Remove the on-disk file + DB row. Returns the filename that was removed."""
    record = InstalledMod.objects.get(pk=record_id)
    target = detect()
    folder = record.kind == "mod" and "mods" or "plugins"
    if target.folder and target.folder != folder:
        # Server type changed since install. We still try the recorded folder.
        folder = "plugins" if record.kind == "plugin" else "mods"
    f = Path(settings.MC_DATA_PATH) / folder / record.filename
    if f.exists():
        f.unlink()
    record.delete()
    return record.filename


class _NoCompatVersion(Exception):
    """Raised when no version of a project supports the running MC."""


def _pick_version(provider: str, project_id: str, version_id: str | None,
                  target: Target) -> VersionInfo | None:
    if provider == "modrinth":
        candidates = modrinth.versions(
            project_id,
            loaders=target.loaders or None,
            mc_versions=None,  # we already filtered by loader; MC version match below
        )
    elif provider == "hangar":
        candidates = hangar.versions(project_id)
    else:
        raise ProviderError(f"Unknown provider: {provider}")

    if not candidates:
        return None

    if version_id is not None:
        return next((v for v in candidates if v.version_id == version_id), None)

    # No version specified → newest compatible.
    from .loader import current_mc_version
    mc = (current_mc_version() or "").upper()
    if mc:
        compat = [
            v for v in candidates
            if (not v.mc_versions or mc in [m.upper() for m in v.mc_versions])
            and (not target.loaders or any(l in target.loaders for l in v.loaders) or not v.loaders)
        ]
        if compat:
            return compat[0]
        # No compat version. Compute a friendly range from what *is* supported
        # so the UI can tell the user "needs MC X to Y".
        supported = sorted({m for v in candidates for m in (v.mc_versions or [])
                            if _looks_like_release(m)},
                           key=_version_sort_key)
        if supported:
            raise _NoCompatVersion(
                f"This project doesn't support Minecraft {mc.lower()}. "
                f"Supported range: {supported[0]} → {supported[-1]}."
            )
        raise _NoCompatVersion(
            f"This project doesn't list Minecraft {mc.lower()} as supported."
        )

    return candidates[0]


def _looks_like_release(v: str) -> bool:
    parts = v.split(".")
    return all(p.isdigit() for p in parts) and 2 <= len(parts) <= 4


def _version_sort_key(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split(".") if p.isdigit())


def _validate_url(url: str) -> None:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise InstallError("Refusing non-HTTPS download URL.")
    host = parsed.hostname or ""
    if not any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS):
        raise InstallError(f"Refusing download from untrusted host: {host}")


def _validate_filename(filename: str) -> None:
    if not filename or "/" in filename or "\\" in filename or "\x00" in filename:
        raise InstallError("Invalid filename from provider.")
    lower = filename.lower()
    if not (lower.endswith(".jar") or lower.endswith(".mrpack")):
        raise InstallError("Only .jar / .mrpack files are accepted.")


def _download(url: str) -> tuple[bytes, int]:
    try:
        with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT,
                          headers={"User-Agent": "hostcraft/1.0"}) as resp:
            resp.raise_for_status()
            buf = bytearray()
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                buf.extend(chunk)
                if len(buf) > MAX_FILE_BYTES:
                    raise InstallError(
                        f"Download exceeded {MAX_FILE_BYTES // (1024 * 1024)} MB limit."
                    )
            return bytes(buf), len(buf)
    except requests.RequestException as exc:
        raise InstallError(f"Download failed: {exc}") from exc


def _verify_hash(blob: bytes, expected: str, algo: str) -> None:
    if algo == "sha512":
        digest = hashlib.sha512(blob).hexdigest()
    elif algo == "sha256":
        digest = hashlib.sha256(blob).hexdigest()
    else:
        return  # unknown algo → skip
    if digest.lower() != expected.lower():
        raise InstallError(f"Hash mismatch ({algo}). Refusing to install.")


def _upsert_record(provider: str, v: VersionInfo, target: Target, project_id: str) -> InstalledMod:
    record, _ = InstalledMod.objects.update_or_create(
        provider=provider,
        project_id=project_id,
        defaults={
            "project_slug": v.project_id,  # modrinth's slug; hangar uses owner/slug
            "title": v.name,
            "version_id": v.version_id,
            "version_number": v.version_number,
            "filename": v.filename,
            "file_hash": v.file_hash or "",
            "hash_algo": v.hash_algo or "",
            "file_size": v.file_size,
            "kind": target.kind,
            "loader": target.loaders[0] if target.loaders else "",
            "mc_version": v.mc_versions[0] if v.mc_versions else "",
        },
    )
    return record
