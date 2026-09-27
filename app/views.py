"""Views blueprint: server-rendered pages — the ONLY user-facing entry.

Browser interactions are form POST + redirect (PRG); pages contain zero
/api calls. Internal API endpoints live in auth/materials/health
blueprints and are reachable only inside the container network.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from flask import (Blueprint, abort, flash, jsonify, redirect,
                   render_template, request, send_file, session)

from app.auth import (establish_session, get_current_user, login_required,
                      role_required, verify_credentials)
from app.db import get_upload_dir
from app.extract import extract_text
from app.materials import MaterialsRepo, _MIME, _validate_file

views_bp = Blueprint("views", __name__)


# ---------- Templates helpers ----------

@views_bp.app_template_filter("filesize")
def filesize_filter(n):
    """Human readable size: 1024→1.0 KB etc. None → ''."""
    if n is None:
        return ""
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 / 1024:.1f} MB"


@views_bp.app_errorhandler(413)
def request_too_large(_e):
    """Multipart over Flask MAX_CONTENT_LENGTH: API clients keep JSON 413,
    page uploads go back to the dashboard with a flash message (PRG)."""
    if request.path.startswith("/api/"):
        return jsonify({"error": "file too large (max 10MB)"}), 413
    flash("文件超过 10MB 限制", "error")
    return redirect("/dashboard")


# ---------- Login / logout (page form routes) ----------

@views_bp.get("/")
def index():
    """根路径：未登录 → 登录页；已登录 → 仪表盘。"""
    if session.get("user_id"):
        return redirect("/dashboard")
    return redirect("/login")


@views_bp.get("/login")
def login_page():
    if session.get("user_id"):
        return redirect("/dashboard")
    return render_template("login.html")


@views_bp.post("/login")
def login_submit():
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    row = verify_credentials(username, password) if username and password else None
    if row is None:
        # 防枚举：不存在/密码错误统一文案
        flash("用户名或密码错误", "error")
        return redirect("/login")
    establish_session(row)
    return redirect("/dashboard")


@views_bp.post("/logout")
def logout_submit():
    session.clear()
    return redirect("/login")


# ---------- Dashboard (server-rendered list + upload form + switcher) ----------

@views_bp.get("/dashboard")
@login_required
def dashboard():
    user = get_current_user()
    materials = MaterialsRepo.list_for_user(user)
    taught = (MaterialsRepo.taught_classes(user["id"])
              if user["role"] == "teacher" else [])
    return render_template(
        "dashboard.html",
        user=user,
        materials=materials,
        taught_classes=taught,
    )


@views_bp.post("/materials")
@login_required
@role_required("teacher")
def upload_material_page():
    """Unified multipart form: text-only (title+content) or with attachment
    (title+file, content auto-extracted). Validation failures re-enter the
    dashboard with a flash message and cause zero writes."""
    user = get_current_user()
    title = (request.form.get("title") or "").strip()
    content = (request.form.get("content") or "").strip()
    file = request.files.get("file")

    if not title:
        flash("标题不能为空", "error")
        return redirect("/dashboard")

    if file is not None and file.filename:
        err = _validate_file(file)
        if err:
            flash(err[0], "error")
            return redirect("/dashboard")

        data = file.read()
        ext = Path(file.filename).suffix.lower()
        orig_name = Path(file.filename).name      # strip any client path parts
        stored_name = uuid.uuid4().hex + ext      # no user input in disk name
        extracted = extract_text(file.filename, data)

        upload_dir = get_upload_dir()
        os.makedirs(upload_dir, exist_ok=True)
        with open(os.path.join(upload_dir, stored_name), "wb") as f:
            f.write(data)

        MaterialsRepo.create_file_for_user(
            user, title, extracted or "",         # "" 遵从旧库 content NOT NULL 约定
            orig_name, stored_name, len(data), _MIME[ext.lstrip(".")],
        )
    else:
        if not content:
            flash("正文不能为空（无附件时必须填写内容）", "error")
            return redirect("/dashboard")
        MaterialsRepo.create_for_user(user, title, content)

    flash("上传成功", "ok")
    return redirect("/dashboard")


# ---------- User-side download ----------

@views_bp.get("/materials/<int:material_id>/download")
@login_required
def download_material_page(material_id: int):
    """Browser-facing download: effective-class filtered, 404 for
    cross-class / missing / text-only materials."""
    user = get_current_user()
    m = MaterialsRepo.get_for_user(user, material_id)
    if m is None or not m["file_stored_name"]:
        abort(404)
    path = os.path.join(get_upload_dir(), m["file_stored_name"])
    if not os.path.isfile(path):
        abort(404)
    return send_file(path, download_name=m["file_orig_name"], as_attachment=True)


# ---------- Teacher class switching ----------

@views_bp.post("/class/switch")
@login_required
@role_required("teacher")
def switch_class():
    """Teachers only. Target must be in teacher_classes (server-side truth);
    otherwise 403 and session stays untouched."""
    user = get_current_user()
    target = (request.form.get("class_id") or "").strip()
    if target and MaterialsRepo.teacher_can_access(user["id"], target):
        session["active_class"] = target
        return redirect("/dashboard")
    abort(403)
