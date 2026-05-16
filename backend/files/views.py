"""File manager endpoints rooted at settings.MC_DATA_PATH.

Every path that crosses the API boundary goes through `_safe_resolve()` to
prevent path traversal — clients can only see and touch what's inside
MC_DATA_PATH.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from django.conf import settings
from django.http import FileResponse
from django.utils.translation import gettext as _
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


# Cap text editor preview at 5 MB — Monaco starts to choke past that and the
# user almost certainly wants `download` (binary) for anything bigger anyway.
MAX_TEXT_PREVIEW_SIZE = 5 * 1024 * 1024


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _data_root() -> Path:
    return Path(settings.MC_DATA_PATH).resolve()


def _safe_resolve(rel: str) -> Path:
    """Resolve `rel` against MC_DATA_PATH and reject anything that escapes it."""
    root = _data_root()
    candidate = (root / rel.lstrip("/")).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PermissionDenied(_("Path escapes the managed directory.")) from exc
    return candidate


def _entry(p: Path) -> dict:
    try:
        st = p.lstat()
        is_dir = p.is_dir()
        return {
            "name": p.name,
            "is_dir": is_dir,
            "size": 0 if is_dir else st.st_size,
            "modified": st.st_mtime,
        }
    except OSError:
        return {"name": p.name, "is_dir": False, "size": 0, "modified": 0}


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


class ListView(APIView):
    """GET /api/files/?path=mods → list directory contents."""

    def get(self, request: Request) -> Response:
        rel = request.query_params.get("path", "") or ""
        target = _safe_resolve(rel)
        if not target.exists():
            return Response({"detail": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
        if not target.is_dir():
            return Response({"detail": _("Not a directory.")}, status=status.HTTP_400_BAD_REQUEST)

        try:
            children = list(target.iterdir())
        except PermissionError:
            return Response({"detail": _("Permission denied.")}, status=status.HTTP_403_FORBIDDEN)

        children.sort(key=lambda p: (not p.is_dir(), p.name.lower()))
        return Response({"path": rel, "entries": [_entry(p) for p in children]})


class ReadView(APIView):
    def get(self, request: Request) -> Response:
        rel = request.query_params.get("path") or ""
        if not rel:
            return Response({"detail": _("Missing path.")}, status=status.HTTP_400_BAD_REQUEST)
        target = _safe_resolve(rel)
        if not target.is_file():
            return Response({"detail": _("Not a file.")}, status=status.HTTP_404_NOT_FOUND)
        size = target.stat().st_size
        if size > MAX_TEXT_PREVIEW_SIZE:
            return Response(
                {"detail": _("File too large for editor preview."), "size": size},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )
        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return Response(
                {"detail": _("Binary file — use download instead.")},
                status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            )
        return Response({"path": rel, "content": content, "encoding": "utf-8", "size": size})


class WriteView(APIView):
    def put(self, request: Request) -> Response:
        rel = request.query_params.get("path") or ""
        if not rel:
            return Response({"detail": _("Missing path.")}, status=status.HTTP_400_BAD_REQUEST)
        content = request.data.get("content", "")
        if not isinstance(content, str):
            return Response(
                {"detail": _("Content must be a string.")}, status=status.HTTP_400_BAD_REQUEST
            )
        target = _safe_resolve(rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return Response(_entry(target))


class DownloadView(APIView):
    def get(self, request: Request):
        rel = request.query_params.get("path") or ""
        if not rel:
            return Response({"detail": _("Missing path.")}, status=status.HTTP_400_BAD_REQUEST)
        target = _safe_resolve(rel)
        if not target.is_file():
            return Response({"detail": _("Not a file.")}, status=status.HTTP_404_NOT_FOUND)
        return FileResponse(target.open("rb"), as_attachment=True, filename=target.name)


class UploadView(APIView):
    parser_classes = [MultiPartParser]

    def post(self, request: Request) -> Response:
        rel = request.query_params.get("path", "") or ""
        target_dir = _safe_resolve(rel)
        target_dir.mkdir(parents=True, exist_ok=True)
        if not target_dir.is_dir():
            return Response(
                {"detail": _("Upload target is not a directory.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        uploaded = []
        for f in request.FILES.values():
            safe_name = Path(f.name).name
            if not safe_name or safe_name in (".", ".."):
                continue
            dest = target_dir / safe_name
            with dest.open("wb") as out:
                for chunk in f.chunks():
                    out.write(chunk)
            uploaded.append(_entry(dest))
        return Response({"uploaded": uploaded})


class MkdirView(APIView):
    def post(self, request: Request) -> Response:
        rel = request.query_params.get("path", "") or ""
        if not rel:
            return Response({"detail": _("Missing path.")}, status=status.HTTP_400_BAD_REQUEST)
        target = _safe_resolve(rel)
        target.mkdir(parents=True, exist_ok=True)
        return Response(_entry(target))


class DeleteView(APIView):
    def delete(self, request: Request) -> Response:
        rel = request.query_params.get("path") or ""
        if not rel:
            return Response({"detail": _("Missing path.")}, status=status.HTTP_400_BAD_REQUEST)
        target = _safe_resolve(rel)
        if target == _data_root():
            return Response(
                {"detail": _("Refusing to delete the data root.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not target.exists():
            return Response({"detail": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MoveView(APIView):
    def post(self, request: Request) -> Response:
        src = (request.data.get("from") or "").strip()
        dst = (request.data.get("to") or "").strip()
        if not src or not dst:
            return Response(
                {"detail": _("`from` and `to` are required.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        src_path = _safe_resolve(src)
        dst_path = _safe_resolve(dst)
        if not src_path.exists():
            return Response({"detail": _("Source not found.")}, status=status.HTTP_404_NOT_FOUND)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        src_path.rename(dst_path)
        return Response(_entry(dst_path))
