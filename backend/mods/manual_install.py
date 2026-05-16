"""Inspect + install user-uploaded mod / plugin / modpack files.

The marketplace covers the happy path (Modrinth + Hangar). This module
handles everything else: a .jar from CurseForge, a private build, a Spigot
resource the user paid for, a Modrinth pack as an .mrpack file.

We open the archive, sniff the well-known metadata files for each loader
family, and surface what we learned so the UI can show "is this
compatible with your server?" *before* the user commits to placing it on
disk. Drop folder is picked from the detected ``kind``: mods go to
``MC_DATA_PATH/mods/``, plugins to ``MC_DATA_PATH/plugins/``.

Modpacks (.mrpack) report their metadata for browsing, but installing
them is still not supported — the format requires fetching a manifest of
mods + overrides and we draw the line at trusted-source installs only.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import logging
import shutil
import tomllib
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import IO
from urllib.parse import urlparse

import requests
import yaml
from django.conf import settings

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 1024 * 1024 * 1024  # 1 GB — large modpacks can hit this
MAX_MODPACK_FILE_BYTES = 250 * 1024 * 1024  # 250 MB per individual mod
MAX_MODPACK_TOTAL_BYTES = 5 * 1024 * 1024 * 1024  # 5 GB sum of downloads
ACCEPTED_EXTS = {".jar", ".mrpack", ".zip"}

# Files / patterns we refuse to extract from a serverpack zip. They'd
# clobber state the panel already manages (eula, ops, whitelist, the
# active server.properties) or pull in launcher scripts that don't run
# in our container.
_SERVERPACK_DENY_AT_ROOT = {
    "eula.txt",
    "user_jvm_args.txt",
    "server.properties",
    "ops.json",
    "whitelist.json",
    "banned-players.json",
    "banned-ips.json",
    "usercache.json",
    "start.sh", "start.bat", "start.cmd",
    "run.sh", "run.bat", "run.cmd",
    "launcher_profiles.json",
}

# Loader-installer / shim .jars dropped at the root of a CurseForge
# serverpack so the user can run them manually. itzg already installs
# the engine for us — skip these to avoid double installs.
_SERVERPACK_INSTALLER_PREFIXES = (
    "forge-", "neoforge-", "fabric-server-", "fabric-installer",
    "quilt-server-", "quilt-installer", "minecraft_server",
    "paper-", "purpur-",
)
_COPY_CHUNK = 1024 * 1024  # 1 MB at a time when streaming to disk

# Hosts a .mrpack is allowed to reference. Modrinth's CDN covers nearly
# every pack; we also accept GitHub releases (rare but happens for
# privately-maintained mods that aren't on Modrinth) and the Maven host
# Forge / NeoForge use.
_MODPACK_ALLOWED_HOSTS = (
    "cdn.modrinth.com",
    "cdn-raw.modrinth.com",
    "github.com",
    "raw.githubusercontent.com",
    "objects.githubusercontent.com",
    "maven.minecraftforge.net",
    "maven.neoforged.net",
)


@dataclass
class InspectResult:
    """What we learned from looking inside the uploaded archive."""

    kind: str                   # 'mod' | 'plugin' | 'modpack' | 'unknown'
    loaders: list[str] = field(default_factory=list)
    name: str = ""
    version: str = ""
    mc_version_range: str = ""  # raw range string from metadata
    declared_minecraft: list[str] = field(default_factory=list)
    can_install: bool = False   # we know what to do with this file
    install_reason: str = ""    # explanation when can_install is False

    def to_dict(self) -> dict:
        return asdict(self)


class ManualInstallError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Inspection
# ---------------------------------------------------------------------------


def inspect(file_obj: IO[bytes], filename: str) -> InspectResult:
    """Parse a .jar / .mrpack and return its metadata.

    ``file_obj`` is any seekable binary file-like object — typically a
    Django ``UploadedFile`` whose payload lives on disk for files
    larger than ``FILE_UPLOAD_MAX_MEMORY_SIZE``. We open the zip
    directly off it rather than slurping into a ``BytesIO``, so a 1 GB
    modpack doesn't pin 1 GB of RSS.

    Never raises on parse errors — always returns an :class:`InspectResult`
    so the UI can show "we couldn't read this file, install anyway?".
    """
    ext = Path(filename).suffix.lower()
    if ext not in ACCEPTED_EXTS:
        return InspectResult(
            kind="unknown",
            name=Path(filename).stem,
            can_install=False,
            install_reason=f"Only {', '.join(sorted(ACCEPTED_EXTS))} files are accepted.",
        )

    try:
        file_obj.seek(0)
    except (AttributeError, OSError):
        pass

    try:
        z = zipfile.ZipFile(file_obj)
    except zipfile.BadZipFile:
        return InspectResult(
            kind="unknown",
            name=Path(filename).stem,
            can_install=False,
            install_reason="Not a valid JAR / zip archive.",
        )

    names = set(z.namelist())

    # Order matters: NeoForge first (its file co-exists with mods.toml in
    # newer projects), then Forge, then loader-specific JSONs, then plugin
    # YAMLs, then modpack index. The first match wins.
    if "META-INF/neoforge.mods.toml" in names:
        return _parse_forge_toml(z, "META-INF/neoforge.mods.toml", "neoforge")
    if "META-INF/mods.toml" in names:
        return _parse_forge_toml(z, "META-INF/mods.toml", "forge")
    if "fabric.mod.json" in names:
        return _parse_fabric(z)
    if "quilt.mod.json" in names:
        return _parse_quilt(z)
    if "paper-plugin.yml" in names:
        return _parse_bukkit(z, "paper-plugin.yml", paper_native=True)
    if "plugin.yml" in names:
        return _parse_bukkit(z, "plugin.yml", paper_native=False)
    if "modrinth.index.json" in names:
        return _parse_mrpack(z)

    # A plain ``.zip`` (typical CurseForge "serverpack" export) has no
    # central manifest — it's literally the data dir packaged. We treat
    # any zip that has a top-level ``mods/`` tree as a serverpack.
    if ext == ".zip":
        return _parse_serverpack(z, names, filename)

    return InspectResult(
        kind="unknown",
        name=Path(filename).stem,
        can_install=False,
        install_reason="No recognised loader metadata inside the archive.",
    )


def _parse_serverpack(z: zipfile.ZipFile, names: set[str], filename: str) -> InspectResult:
    """Recognise a CurseForge-style serverpack zip.

    Heuristic: a serverpack has a ``mods/`` tree at the root. A
    *modpack* zip from CurseForge instead has only a ``manifest.json``
    that references their API by file-id — we can't install those
    without a CurseForge API key, so we say so explicitly.
    """
    has_mods = any(n.startswith("mods/") and not n.endswith("/") for n in names)
    has_cf_manifest = "manifest.json" in names and not has_mods

    if has_cf_manifest:
        return InspectResult(
            kind="modpack",
            name=Path(filename).stem,
            can_install=False,
            install_reason=(
                "This is a CurseForge modpack-zip (only a manifest.json, no mods bundled). "
                "Install it via the CurseForge launcher to export a *serverpack*, then "
                "upload that here, or grab the .mrpack version from Modrinth."
            ),
        )
    if not has_mods:
        return InspectResult(
            kind="unknown",
            name=Path(filename).stem,
            can_install=False,
            install_reason="ZIP doesn't look like a Minecraft serverpack (no mods/ folder).",
        )

    # Detect loader by what's bundled at the root.
    loaders: list[str] = []
    for n in names:
        bn = n.split("/")[-1] if "/" in n else n
        low = bn.lower()
        if low.startswith("forge-") and low.endswith(".jar"):
            loaders.append("forge")
            break
        if low.startswith("neoforge-") and low.endswith(".jar"):
            loaders.append("neoforge")
            break
        if low.startswith("fabric-server") or "fabric-installer" in low:
            loaders.append("fabric")
            break

    return InspectResult(
        kind="modpack",
        loaders=loaders,
        name=Path(filename).stem,
        version="",
        mc_version_range="",
        can_install=True,
    )


def _parse_forge_toml(z: zipfile.ZipFile, path: str, loader: str) -> InspectResult:
    try:
        data = tomllib.loads(z.read(path).decode("utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        logger.exception("malformed %s", path)
        return InspectResult(kind="mod", loaders=[loader], can_install=True,
                             install_reason="(metadata unreadable)")

    mods = data.get("mods") or []
    first = mods[0] if mods else {}
    mod_id = first.get("modId") or ""
    name = first.get("displayName") or mod_id or ""
    version = str(first.get("version") or "")

    mc_range = ""
    deps = (data.get("dependencies") or {}).get(mod_id) or []
    if isinstance(deps, list):
        for d in deps:
            if isinstance(d, dict) and d.get("modId") == "minecraft":
                mc_range = str(d.get("versionRange") or "")
                break
    return InspectResult(
        kind="mod",
        loaders=[loader],
        name=name,
        version=version,
        mc_version_range=mc_range,
        can_install=True,
    )


def _parse_fabric(z: zipfile.ZipFile) -> InspectResult:
    try:
        data = json.loads(z.read("fabric.mod.json").decode("utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        return InspectResult(kind="mod", loaders=["fabric"], can_install=True,
                             install_reason="(metadata unreadable)")

    name = data.get("name") or data.get("id") or ""
    version = str(data.get("version") or "")
    depends = data.get("depends") or {}
    mc = depends.get("minecraft")
    if isinstance(mc, list):
        mc_range = ", ".join(str(v) for v in mc)
    else:
        mc_range = str(mc) if mc else ""
    return InspectResult(
        kind="mod",
        loaders=["fabric"],
        name=name,
        version=version,
        mc_version_range=mc_range,
        can_install=True,
    )


def _parse_quilt(z: zipfile.ZipFile) -> InspectResult:
    try:
        data = json.loads(z.read("quilt.mod.json").decode("utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        return InspectResult(kind="mod", loaders=["quilt", "fabric"], can_install=True,
                             install_reason="(metadata unreadable)")

    ql = data.get("quilt_loader") or {}
    meta = ql.get("metadata") or {}
    name = meta.get("name") or ql.get("id") or ""
    version = str(ql.get("version") or "")
    mc_range = ""
    depends = ql.get("depends") or []
    if isinstance(depends, list):
        for d in depends:
            if isinstance(d, dict) and d.get("id") == "minecraft":
                v = d.get("versions") or d.get("version")
                if isinstance(v, dict):
                    v = v.get("any") or v.get("all") or ""
                mc_range = str(v) if v else ""
                break
    return InspectResult(
        kind="mod",
        loaders=["quilt", "fabric"],
        name=name,
        version=version,
        mc_version_range=mc_range,
        can_install=True,
    )


def _parse_bukkit(z: zipfile.ZipFile, path: str, *, paper_native: bool) -> InspectResult:
    try:
        data = yaml.safe_load(z.read(path).decode("utf-8", errors="replace")) or {}
    except Exception:  # noqa: BLE001
        return InspectResult(kind="plugin", loaders=["paper", "spigot", "bukkit"],
                             can_install=True, install_reason="(metadata unreadable)")

    name = str(data.get("name") or "")
    version = str(data.get("version") or "")
    api = str(data.get("api-version") or data.get("api_version") or "")
    loaders = (["paper"] if paper_native else ["paper", "spigot", "bukkit"])
    return InspectResult(
        kind="plugin",
        loaders=loaders,
        name=name,
        version=version,
        mc_version_range=f">={api}" if api else "",
        declared_minecraft=[api] if api else [],
        can_install=True,
    )


def _parse_mrpack(z: zipfile.ZipFile) -> InspectResult:
    try:
        data = json.loads(z.read("modrinth.index.json").decode("utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        return InspectResult(kind="modpack", can_install=False,
                             install_reason="Modpack index unreadable.")

    if int(data.get("formatVersion") or 0) != 1:
        return InspectResult(
            kind="modpack", can_install=False,
            install_reason="Unsupported Modrinth pack format (only v1 is implemented).",
        )

    name = str(data.get("name") or "")
    version = str(data.get("versionId") or "")
    deps = data.get("dependencies") or {}
    loaders: list[str] = []
    if "forge" in deps: loaders.append("forge")
    if "neoforge" in deps: loaders.append("neoforge")
    if "fabric-loader" in deps: loaders.append("fabric")
    if "quilt-loader" in deps: loaders.append("quilt")
    mc = str(deps.get("minecraft", ""))
    return InspectResult(
        kind="modpack",
        loaders=loaders,
        name=name,
        version=version,
        mc_version_range=mc,
        declared_minecraft=[mc] if mc else [],
        can_install=True,
    )


# ---------------------------------------------------------------------------
# Compatibility verdict
# ---------------------------------------------------------------------------


def compat_verdict(meta: InspectResult, target_loaders: list[str],
                   mc_version: str) -> dict:
    """Compare detected metadata with the running server.

    Returns ``{loader: 'ok'|'mismatch', mc: 'ok'|'mismatch'|'unknown', overall: 'ok'|'warn'|'block'}``.
    The frontend uses these to colour the badges and decide whether the
    install button stays primary or turns into a yellow "Install anyway".
    """
    # Loader check
    if not meta.loaders or not target_loaders:
        loader_v = "unknown"
    elif any(l in target_loaders for l in meta.loaders):
        loader_v = "ok"
    else:
        loader_v = "mismatch"

    # MC version check
    if not meta.mc_version_range and not meta.declared_minecraft:
        mc_v = "unknown"
    elif not mc_version:
        mc_v = "unknown"
    else:
        if _mc_satisfies(mc_version, meta.mc_version_range, meta.declared_minecraft):
            mc_v = "ok"
        else:
            mc_v = "mismatch"

    if loader_v == "mismatch":
        overall = "block"
    elif mc_v == "mismatch":
        overall = "warn"
    else:
        overall = "ok"
    return {"loader": loader_v, "mc": mc_v, "overall": overall}


def _mc_satisfies(target: str, range_str: str, listed: list[str]) -> bool:
    """Best-effort match. Accepts Maven-style ranges and a few common forms.

    We err on the side of accepting (returning True for ambiguous shapes)
    so unparseable metadata doesn't block valid installs.
    """
    target_tup = _vtuple(target)
    if not target_tup:
        return True  # can't compare → don't block

    # Listed exact set first (Paper api-version, modrinth list).
    for v in listed:
        t = _vtuple(v)
        if t and t == target_tup[:len(t)]:
            return True

    r = (range_str or "").strip()
    if not r:
        return True

    # Maven-style: [1.20.1,1.21) — inclusive low, exclusive high
    if r.startswith(("[", "(")) and r.endswith(("]", ")")):
        inc_low = r[0] == "["
        inc_high = r[-1] == "]"
        body = r[1:-1].strip()
        if "," in body:
            low_s, high_s = (x.strip() for x in body.split(",", 1))
            low_t = _vtuple(low_s) if low_s else None
            high_t = _vtuple(high_s) if high_s else None
            if low_t and target_tup < low_t:
                return False
            if low_t and not inc_low and target_tup == low_t:
                return False
            if high_t and target_tup > high_t:
                return False
            if high_t and not inc_high and target_tup == high_t:
                return False
            return True

    # ">=1.20.1" / "<1.21" / "1.20.x"
    if r.startswith(">="):
        t = _vtuple(r[2:].strip())
        return not t or target_tup >= t
    if r.startswith(">"):
        t = _vtuple(r[1:].strip())
        return not t or target_tup > t
    if r.startswith("<="):
        t = _vtuple(r[2:].strip())
        return not t or target_tup <= t
    if r.startswith("<"):
        t = _vtuple(r[1:].strip())
        return not t or target_tup < t
    if r.endswith(".x"):
        prefix = _vtuple(r[:-2])
        return bool(prefix) and target_tup[: len(prefix)] == prefix

    # Plain "1.20.1"
    t = _vtuple(r)
    if t:
        return target_tup[: len(t)] == t

    return True  # gave up → accept


def _vtuple(s: str) -> tuple[int, ...]:
    parts = (s or "").strip().lstrip("v").split(".")
    out: list[int] = []
    for p in parts:
        digits = "".join(ch for ch in p if ch.isdigit())
        if not digits:
            break
        out.append(int(digits))
    return tuple(out)


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------


def install(file_obj: IO[bytes], filename: str, size: int,
            *, force_kind: str | None = None) -> dict:
    """Write the uploaded file to the right directory + record it in DB.

    Streams the bytes 1 MB at a time so a 1 GB modpack never sits in RAM.
    ``force_kind`` lets the UI explicitly install a file we couldn't
    fully recognise (e.g. a vendor jar with no mods.toml) — the user
    picks "mod" or "plugin" themselves and we trust them.
    """
    if size <= 0:
        raise ManualInstallError("Empty upload.")
    if size > MAX_UPLOAD_BYTES:
        raise ManualInstallError(
            f"File too large (max {MAX_UPLOAD_BYTES // 1024 // 1024} MB)."
        )

    safe_name = Path(filename).name
    if not safe_name or "/" in safe_name or "\\" in safe_name or "\x00" in safe_name:
        raise ManualInstallError("Invalid filename.")
    if Path(safe_name).suffix.lower() not in ACCEPTED_EXTS:
        raise ManualInstallError("Only .jar / .mrpack are accepted.")

    # Modrinth modpack: unpack manifest, fetch every server-side mod from
    # its CDN, then drop the bundled overrides on top.
    if safe_name.lower().endswith(".mrpack"):
        return _install_modpack(file_obj, safe_name, size)

    # CurseForge-style serverpack: a plain zip that mirrors the data dir
    # (``mods/``, ``config/``, …). Extract with a deny-list to skip the
    # bits that fight itzg / the panel.
    if safe_name.lower().endswith(".zip"):
        return _install_serverpack(file_obj, safe_name, size)

    meta = inspect(file_obj, safe_name)
    kind = force_kind or meta.kind
    if kind not in {"mod", "plugin"}:
        raise ManualInstallError(
            "Couldn't tell whether this is a mod or a plugin — pick one explicitly."
        )

    base = Path(settings.MC_DATA_PATH) / ("mods" if kind == "mod" else "plugins")
    base.mkdir(parents=True, exist_ok=True)
    dest = base / safe_name
    tmp = dest.with_suffix(dest.suffix + ".part")

    try:
        file_obj.seek(0)
    except (AttributeError, OSError):
        pass

    with tmp.open("wb") as out:
        shutil.copyfileobj(file_obj, out, length=_COPY_CHUNK)
    tmp.replace(dest)

    # Track it the same way marketplace installs are tracked, so the
    # Installed tab shows it alongside Modrinth/Hangar entries.
    from .models import InstalledMod
    record, _ = InstalledMod.objects.update_or_create(
        provider="manual",
        project_id=safe_name,
        defaults={
            "project_slug": safe_name,
            "title": meta.name or Path(safe_name).stem,
            "version_id": meta.version or "",
            "version_number": meta.version or "",
            "filename": safe_name,
            "file_size": size,
            "kind": kind,
            "loader": (meta.loaders[0] if meta.loaders else ""),
            "mc_version": meta.mc_version_range or "",
        },
    )
    return {
        "id": record.id,
        "filename": safe_name,
        "kind": kind,
        "size": size,
        "meta": meta.to_dict(),
    }


# ---------------------------------------------------------------------------
# Modrinth modpack install
# ---------------------------------------------------------------------------


def _install_modpack(file_obj: IO[bytes], filename: str, size: int) -> dict:
    """Install a Modrinth ``.mrpack`` modpack.

    Format: zip archive containing ``modrinth.index.json`` (a manifest
    listing each mod's URL + hashes) and optional ``overrides/`` /
    ``server-overrides/`` trees of files to drop verbatim into the data
    dir. We:

    1. Parse + validate the manifest (server-side files only, loader +
       mc compat).
    2. Fetch each referenced file in parallel from its CDN — refusing
       URLs outside :data:`_MODPACK_ALLOWED_HOSTS` and validating the
       sha512/sha1 the manifest advertises.
    3. Extract the ``server-overrides`` and ``overrides`` trees,
       rejecting any path that escapes the data dir.
    4. Record a single ``InstalledMod`` row tagged ``manual_modpack`` so
       the Installed tab shows the pack identity.
    """
    from .loader import current_mc_version, detect

    try:
        file_obj.seek(0)
    except (AttributeError, OSError):
        pass
    try:
        z = zipfile.ZipFile(file_obj)
    except zipfile.BadZipFile as exc:
        raise ManualInstallError("Modpack archive is corrupt or unreadable.") from exc

    try:
        manifest = json.loads(z.read("modrinth.index.json").decode("utf-8", errors="replace"))
    except (KeyError, ValueError) as exc:
        raise ManualInstallError("Modpack is missing modrinth.index.json.") from exc

    if int(manifest.get("formatVersion") or 0) != 1:
        raise ManualInstallError("Unsupported modpack format version (need v1).")

    deps = manifest.get("dependencies") or {}
    pack_loader = _modpack_loader(deps)
    if not pack_loader:
        raise ManualInstallError("Modpack manifest doesn't declare a loader.")

    target = detect()
    if target.kind not in ("mod", "plugin"):
        raise ManualInstallError(
            f"Engine ‘{target.loader_label}’ doesn't accept mods/plugins."
        )
    if pack_loader not in (target.loaders or []):
        raise ManualInstallError(
            f"Modpack needs {pack_loader}, your server runs {target.loader_label}."
        )

    pack_mc = str(deps.get("minecraft") or "")
    mc = current_mc_version()
    if pack_mc and mc and pack_mc != mc:
        raise ManualInstallError(
            f"Modpack targets Minecraft {pack_mc}, your server runs {mc}. "
            f"Switch in /runtime first."
        )

    files = manifest.get("files") or []
    server_files: list[dict] = []
    for f in files:
        env = f.get("env") or {}
        if env.get("server", "required") == "unsupported":
            continue
        server_files.append(f)

    total = sum(int(f.get("fileSize") or 0) for f in server_files)
    if total > MAX_MODPACK_TOTAL_BYTES:
        raise ManualInstallError(
            f"Modpack downloads would total {total // 1024 // 1024} MB "
            f"(cap {MAX_MODPACK_TOTAL_BYTES // 1024 // 1024} MB)."
        )

    base = Path(settings.MC_DATA_PATH)

    # 1. Download referenced mods/files in parallel.
    failures: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        results = ex.map(lambda f: _download_modpack_file(f, base), server_files)
        for path, err in results:
            if err:
                failures.append(f"{path}: {err}")
    if failures:
        raise ManualInstallError(
            f"Some files couldn't be installed:\n{chr(10).join(failures[:5])}"
        )

    # 2. Drop the bundled override trees on top.
    extracted = _extract_modpack_overrides(z, base)

    # 3. Track in the Installed tab so the user can see what was applied.
    from .models import InstalledMod
    record, _ = InstalledMod.objects.update_or_create(
        provider="manual_modpack",
        project_id=filename,
        defaults={
            "project_slug": filename,
            "title": str(manifest.get("name") or filename),
            "version_id": str(manifest.get("versionId") or ""),
            "version_number": str(manifest.get("versionId") or ""),
            "filename": filename,
            "file_size": size,
            "kind": target.kind,
            "loader": pack_loader,
            "mc_version": pack_mc,
        },
    )

    return {
        "id": record.id,
        "filename": filename,
        "kind": "modpack",
        "size": size,
        "modpack": {
            "name": str(manifest.get("name") or filename),
            "version": str(manifest.get("versionId") or ""),
            "files_installed": len(server_files),
            "overrides_extracted": extracted,
            "loader": pack_loader,
            "mc_version": pack_mc,
        },
    }


def _modpack_loader(deps: dict) -> str:
    """Translate manifest dependency keys to our canonical loader names."""
    if "forge" in deps: return "forge"
    if "neoforge" in deps: return "neoforge"
    if "fabric-loader" in deps: return "fabric"
    if "quilt-loader" in deps: return "quilt"
    return ""


def _download_modpack_file(entry: dict, base: Path) -> tuple[str, str]:
    """Fetch one file from the manifest. Returns ``(path, error_or_empty)``."""
    rel_path = str(entry.get("path") or "")
    if not rel_path:
        return ("(missing path)", "manifest entry has no path")

    # Path safety: refuse absolute and parent-traversal segments.
    norm = Path(rel_path)
    if norm.is_absolute() or any(part in ("..", "") for part in norm.parts[:-1] if part):
        return (rel_path, "unsafe path")
    if ".." in norm.parts:
        return (rel_path, "unsafe path")

    downloads = entry.get("downloads") or []
    if not downloads:
        return (rel_path, "no download URL")

    expected_size = int(entry.get("fileSize") or 0)
    if expected_size > MAX_MODPACK_FILE_BYTES:
        return (rel_path, f"file > {MAX_MODPACK_FILE_BYTES // 1024 // 1024} MB cap")

    hashes = entry.get("hashes") or {}
    sha512_expected = hashes.get("sha512", "")
    sha1_expected = hashes.get("sha1", "")

    last_err = "no allowed mirror"
    for url in downloads:
        host = (urlparse(url).hostname or "").lower()
        if not any(host == h or host.endswith("." + h) for h in _MODPACK_ALLOWED_HOSTS):
            last_err = f"untrusted host: {host}"
            continue
        try:
            with requests.get(url, stream=True, timeout=60,
                              headers={"User-Agent": "hostcraft/1.0"}) as resp:
                resp.raise_for_status()
                buf = bytearray()
                for chunk in resp.iter_content(chunk_size=128 * 1024):
                    if not chunk:
                        continue
                    buf.extend(chunk)
                    if len(buf) > MAX_MODPACK_FILE_BYTES:
                        return (rel_path,
                                f"download exceeded {MAX_MODPACK_FILE_BYTES // 1024 // 1024} MB cap")
            blob = bytes(buf)
        except requests.RequestException as exc:
            last_err = f"network error: {exc}"
            continue

        # Verify whatever hash the manifest gave us.
        if sha512_expected:
            if hashlib.sha512(blob).hexdigest() != sha512_expected.lower():
                last_err = "sha512 mismatch"
                continue
        elif sha1_expected:
            if hashlib.sha1(blob).hexdigest() != sha1_expected.lower():
                last_err = "sha1 mismatch"
                continue

        dest = base / norm
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.write_bytes(blob)
        tmp.replace(dest)
        return (rel_path, "")

    return (rel_path, last_err)


def _install_serverpack(file_obj: IO[bytes], filename: str, size: int) -> dict:
    """Install a CurseForge-style serverpack zip.

    The zip is essentially a snapshot of ``/data/``: ``mods/``,
    ``config/``, ``defaultconfigs/``, ``kubejs/``, ``scripts/``,
    ``resourcepacks/``, etc. We extract everything *except* the bits
    that would fight the panel:

    - Top-level ``eula.txt``, ``server.properties``, ``ops.json``,
      whitelist / ban lists, JVM args (the panel manages these).
    - ``start.sh`` / ``run.bat`` and friends (we don't drive startup
      ourselves — itzg does).
    - The loader installer .jar at the root (forge-xxx-installer.jar,
      neoforge-xxx, fabric-server-launch.jar, …) — itzg already brings
      the engine matching ``TYPE`` in env.

    Path safety: every entry's destination is validated to stay inside
    the data dir (no ``..``, no absolute paths).
    """
    from .loader import detect

    try:
        file_obj.seek(0)
    except (AttributeError, OSError):
        pass
    try:
        z = zipfile.ZipFile(file_obj)
    except zipfile.BadZipFile as exc:
        raise ManualInstallError("Serverpack zip is corrupt or unreadable.") from exc

    target = detect()
    if target.kind not in ("mod", "plugin"):
        raise ManualInstallError(
            f"Engine ‘{target.loader_label}’ doesn't accept mods."
        )

    base = Path(settings.MC_DATA_PATH)
    extracted = 0
    skipped = 0

    for info in z.infolist():
        if info.is_dir():
            continue

        raw = info.filename.lstrip("/")  # tolerate accidental leading slash
        rel_path = Path(raw)
        # Path safety — reject anything that escapes the data dir.
        if rel_path.is_absolute() or ".." in rel_path.parts:
            skipped += 1
            continue

        # Top-level files (no parent dir) get the deny-list treatment.
        top_level = len(rel_path.parts) == 1
        bn = rel_path.name.lower()
        if top_level:
            if bn in _SERVERPACK_DENY_AT_ROOT:
                skipped += 1
                continue
            if bn.endswith(".jar") and bn.startswith(_SERVERPACK_INSTALLER_PREFIXES):
                skipped += 1
                continue

        # Refuse oversized members — the cap protects against a zip
        # bomb where one tiny compressed entry expands to 100 GB.
        if info.file_size > MAX_MODPACK_FILE_BYTES:
            skipped += 1
            continue

        dest = base / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        with z.open(info) as src, dest.open("wb") as out:
            shutil.copyfileobj(src, out, length=_COPY_CHUNK)
        extracted += 1

    if extracted == 0:
        raise ManualInstallError(
            "Nothing extractable in this zip (everything was deny-listed)."
        )

    from .models import InstalledMod
    record, _ = InstalledMod.objects.update_or_create(
        provider="manual_modpack",
        project_id=filename,
        defaults={
            "project_slug": filename,
            "title": Path(filename).stem,
            "filename": filename,
            "file_size": size,
            "kind": target.kind,
            "loader": (target.loaders[0] if target.loaders else ""),
        },
    )

    return {
        "id": record.id,
        "filename": filename,
        "kind": "modpack",
        "size": size,
        "modpack": {
            "name": Path(filename).stem,
            "version": "",
            "files_installed": extracted,
            "overrides_extracted": 0,
            "skipped_unsafe_or_denied": skipped,
            "loader": (target.loaders[0] if target.loaders else ""),
        },
    }


def _extract_modpack_overrides(z: zipfile.ZipFile, base: Path) -> int:
    """Drop ``overrides/`` and ``server-overrides/`` trees on the data dir.

    Skips ``client-overrides/`` since those are for the client only.
    Returns the number of files extracted.
    """
    count = 0
    for info in z.infolist():
        if info.is_dir():
            continue
        name = info.filename
        prefix = None
        for d in ("server-overrides/", "overrides/"):
            if name.startswith(d):
                prefix = d
                break
        if prefix is None:
            continue
        rel = name[len(prefix):]
        if not rel:
            continue
        # Path safety: no absolute, no parent traversal.
        rel_path = Path(rel)
        if rel_path.is_absolute() or ".." in rel_path.parts:
            continue
        dest = base / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        with z.open(info) as src, dest.open("wb") as dst:
            shutil.copyfileobj(src, dst, length=_COPY_CHUNK)
        count += 1
    return count
