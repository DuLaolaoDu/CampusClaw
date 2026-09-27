"""Materials blueprint — endpoints + Repository with server-side class_id enforcement."""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from flask import Blueprint, abort, jsonify, request, send_file

from app.auth import get_current_user, login_required, role_required
from app.config import Config
from app.db import connect, get_upload_dir
from app.extract import extract_text

materials_bp = Blueprint("materials", __name__)

_MIME = {"txt": "text/plain", "md": "text/markdown", "pdf": "application/pdf"}

_SELECT_COLS = (
    "id, class_id, owner_id, title, content, "
    "file_orig_name, file_stored_name, file_size, file_mime, created_at"
)


def _normalize(row: dict) -> dict:
    """Public API shape: file_stored_name is never exposed; empty-string
    content (legacy NOT NULL convention for file materials) reads as null."""
    return {
        "id": row["id"],
        "class_id": row["class_id"],
        "owner_id": row["owner_id"],
        "title": row["title"],
        "content": row["content"] or None,
        "file_orig_name": row["file_orig_name"],
        "file_size": row["file_size"],
        "file_mime": row["file_mime"],
        "created_at": row["created_at"],
    }


# ---------- Repository (server-side class_id FORCE) ----------

class MaterialsRepo:
    """Every method ignores client-supplied class_id and uses
    user.effective_class (teacher: switchable taught class / student: own class)."""

    @staticmethod
    def create_for_user(user: dict, title: str, content: str) -> dict:
        class_id = user["effective_class"]  # always from server session
        owner_id = user["id"]
        conn = connect()
        try:
            cur = conn.execute(
                "INSERT INTO materials (class_id, owner_id, title, content) VALUES (?, ?, ?, ?)",
                (class_id, owner_id, title, content),
            )
            mid = cur.lastrowid
            conn.commit()
            row = conn.execute(
                f"SELECT {_SELECT_COLS} FROM materials WHERE id = ?",
                (mid,),
            ).fetchone()
        finally:
            conn.close()
        return _normalize(dict(row))

    @staticmethod
    def create_file_for_user(
        user: dict, title: str, content: str,
        orig_name: str, stored_name: str, size: int, mime: str,
    ) -> dict:
        class_id = user["effective_class"]  # always from server session
        owner_id = user["id"]
        conn = connect()
        try:
            cur = conn.execute(
                "INSERT INTO materials "
                "(class_id, owner_id, title, content, file_orig_name, file_stored_name, file_size, file_mime) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (class_id, owner_id, title, content, orig_name, stored_name, size, mime),
            )
            mid = cur.lastrowid
            conn.commit()
            row = conn.execute(
                f"SELECT {_SELECT_COLS} FROM materials WHERE id = ?",
                (mid,),
            ).fetchone()
        finally:
            conn.close()
        return _normalize(dict(row))

    @staticmethod
    def list_for_user(user: dict) -> list[dict]:
        class_id = user["effective_class"]
        conn = connect()
        try:
            rows = conn.execute(
                f"SELECT {_SELECT_COLS} FROM materials WHERE class_id = ? ORDER BY created_at DESC",
                (class_id,),
            ).fetchall()
        finally:
            conn.close()
        return [_normalize(dict(r)) for r in rows]

    @staticmethod
    def get_for_user(user: dict, material_id: int) -> dict | None:
        """Single material by id within the user's effective class; None if
        invisible (cross-class or missing) — callers convert to 404. Returns
        the raw row (includes file_stored_name for download); normalize with
        _normalize() before exposing in API responses."""
        class_id = user["effective_class"]
        conn = connect()
        try:
            row = conn.execute(
                f"SELECT {_SELECT_COLS} FROM materials WHERE id = ? AND class_id = ?",
                (material_id, class_id),
            ).fetchone()
        finally:
            conn.close()
        return dict(row) if row is not None else None

    # ---------- Teaching relations (server-side truth for class switching) ----------

    @staticmethod
    def taught_classes(teacher_id: int) -> list[str]:
        """Classes a teacher may switch to — sole source of truth."""
        conn = connect()
        try:
            rows = conn.execute(
                "SELECT class_id FROM teacher_classes WHERE teacher_id = ? ORDER BY class_id",
                (teacher_id,),
            ).fetchall()
        finally:
            conn.close()
        return [r["class_id"] for r in rows]

    @staticmethod
    def teacher_can_access(teacher_id: int, class_id: str) -> bool:
        """Whether class_id is within the teacher's taught relations."""
        conn = connect()
        try:
            row = conn.execute(
                "SELECT 1 FROM teacher_classes WHERE teacher_id = ? AND class_id = ?",
                (teacher_id, class_id),
            ).fetchone()
        finally:
            conn.close()
        return row is not None


# ---------- File validation (extension whitelist + magic number + size) ----------

def _validate_file(file) -> tuple[str, int] | None:
    """Return (error_message, http_status) on failure, None when acceptable.
    Never writes to disk or DB. Zero-dependency magic checks:
    pdf must start with %PDF-, txt/md must fully decode as UTF-8."""
    filename = file.filename or ""
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in Config.ALLOWED_EXTENSIONS:
        return "unsupported file type (allowed: txt, md, pdf)", 415

    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > Config.MAX_FILE_SIZE:
        return "file too large (max 10MB)", 413

    if ext == "pdf":
        if file.read(5) != b"%PDF-":
            return "invalid pdf file", 415
        file.seek(0)
    else:
        data = file.read()
        file.seek(0)
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return "invalid text file (must be UTF-8)", 415
    return None


# ---------- Endpoints ----------

@materials_bp.post("/api/materials")
@login_required
@role_required("teacher")
def upload_material():
    user = get_current_user()
    body = request.get_json(silent=True) or {}
    title = (body.get("title") or "").strip()
    content = (body.get("content") or "").strip()

    if not title or not content:
        return jsonify({"error": "title and content are required"}), 400

    m = MaterialsRepo.create_for_user(user, title, content)
    return jsonify(m), 201


@materials_bp.post("/api/materials/file")
@login_required
@role_required("teacher")
def upload_file_material():
    """multipart/form-data: file + title. content is extracted server-side."""
    user = get_current_user()
    title = (request.form.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400

    file = request.files.get("file")
    if file is None or not file.filename:
        return jsonify({"error": "file is required"}), 400

    err = _validate_file(file)
    if err:
        return jsonify({"error": err[0]}), err[1]

    data = file.read()
    ext = Path(file.filename).suffix.lower()
    orig_name = Path(file.filename).name      # strip any client path components
    stored_name = uuid.uuid4().hex + ext      # no user input in disk name
    content = extract_text(file.filename, data)

    upload_dir = get_upload_dir()
    os.makedirs(upload_dir, exist_ok=True)
    with open(os.path.join(upload_dir, stored_name), "wb") as f:
        f.write(data)

    m = MaterialsRepo.create_file_for_user(
        user, title, content or "",           # "" 遵从旧库 content NOT NULL 约定
        orig_name, stored_name, len(data), _MIME[ext.lstrip(".")],
    )
    return jsonify(m), 201


@materials_bp.get("/api/materials")
@login_required
def list_materials():
    user = get_current_user()
    items = MaterialsRepo.list_for_user(user)
    return jsonify(items), 200


@materials_bp.get("/api/materials/<int:material_id>")
@login_required
def get_material(material_id: int):
    user = get_current_user()
    m = MaterialsRepo.get_for_user(user, material_id)
    if m is None:
        abort(404)   # cross班 or 不存在 — 统一 404, 不泄露存在性
    return jsonify(_normalize(m)), 200


@materials_bp.get("/api/materials/<int:material_id>/download")
@login_required
def download_material(material_id: int):
    user = get_current_user()
    m = MaterialsRepo.get_for_user(user, material_id)
    if m is None or not m["file_stored_name"]:
        abort(404)   # 跨班 / 不存在 / 纯文本材料 — 统一 404
    path = os.path.join(get_upload_dir(), m["file_stored_name"])
    if not os.path.isfile(path):
        abort(404)
    return send_file(path, download_name=m["file_orig_name"], as_attachment=True)
