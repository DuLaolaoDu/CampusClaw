"""Auth blueprint: login/logout endpoints + role / login_required decorators."""
from __future__ import annotations

from functools import wraps

from flask import Blueprint, abort, jsonify, request, session

import bcrypt

from app.db import connect

auth_bp = Blueprint("auth", __name__)


# ---------- Decorators ----------

def login_required(view_func):
    """Mark a view as requiring an active session. Also used as before_request signal."""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            abort(401)
        return view_func(*args, **kwargs)

    wrapper.login_required = True  # type: ignore[attr-defined]
    return wrapper


def role_required(*allowed_roles: str):
    """Require current user role to be in the allowed set. Must run after login_required."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            role = session.get("role")
            if role not in allowed_roles:
                abort(403)
            return view_func(*args, **kwargs)
        wrapper.login_required = True  # still needs login first
        return wrapper
    return decorator


# ---------- Shared credential / session helpers ----------

def verify_credentials(username: str, password: str):
    """Return the users row on success, None on failure. Anti-enumeration:
    always runs a bcrypt compare, never distinguishes missing user vs bad
    password. Shared by API login and page form login."""
    conn = connect()
    try:
        row = conn.execute(
            "SELECT id, username, password_hash, role, class_id FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        bcrypt.checkpw(password.encode("utf-8"), b"$2b$12$CwTycUXWue0Thq9StjUM0uJ8fxhgwmfJ/6zEXAMPLEHASHDOESNTMATCH")
        return None

    try:
        ok = bcrypt.checkpw(password.encode("utf-8"), row["password_hash"].encode("utf-8"))
    except ValueError:
        ok = False
    return row if ok else None


def establish_session(row) -> None:
    """Write login session: user info + effective class (defaults to own class)."""
    session.clear()
    session["user_id"] = row["id"]
    session["username"] = row["username"]
    session["role"] = row["role"]
    session["class_id"] = row["class_id"]
    session["active_class"] = row["class_id"]   # 生效班级：教师可切换，学生恒等于本班


# ---------- Endpoints ----------

@auth_bp.post("/api/auth/login")
def login():
    """POST /api/auth/login {username, password} -> sets session, returns user JSON."""
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""

    if not username or not password:
        return jsonify({"error": "invalid credentials"}), 401

    row = verify_credentials(username, password)
    if row is None:
        return jsonify({"error": "invalid credentials"}), 401

    establish_session(row)

    return jsonify({
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "class_id": row["class_id"],
    }), 200


@auth_bp.post("/api/auth/logout")
@login_required
def logout():
    session.clear()
    return jsonify({"ok": True}), 200


def get_current_user() -> dict:
    """Currently logged-in user info (caller must ensure login).

    effective_class is THE class all isolation queries/writes use:
    teacher → session active_class (switchable within taught classes),
    student → own class_id (locked, switch endpoint rejects with 403)."""
    role = session["role"]
    own_class = session["class_id"]
    if role == "teacher":
        effective = session.get("active_class") or own_class
    else:
        effective = own_class
    return {
        "id": session["user_id"],
        "username": session["username"],
        "role": role,
        "class_id": own_class,
        "effective_class": effective,
    }
