"""Flask app factory: wires config, db, blueprints, and before_request hooks."""
from __future__ import annotations

from flask import Flask, abort, redirect, session

from app.config import Config
from app.db import connect, init_schema, seed_preset, ensure_upload_dir


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = Config.APP_SECRET
    app.config["DATABASE_PATH"] = Config.DATABASE_PATH
    app.config["MAX_CONTENT_LENGTH"] = Config.MAX_FILE_SIZE  # multipart >10MB → 413

    # --- DB init + uploads dir (runs once at import time) ---
    conn = connect()
    init_schema(conn)
    seed_preset(conn)
    conn.close()
    ensure_upload_dir()

    # --- Register blueprints ---
    from app.auth import auth_bp
    from app.materials import materials_bp
    from app.health import health_bp
    from app.views import views_bp

    app.register_blueprint(views_bp)     # 最先注册：页面路由（无 /api 前缀）
    app.register_blueprint(auth_bp)
    app.register_blueprint(materials_bp)
    app.register_blueprint(health_bp)

    # --- before_request: enforce login_required on protected blueprints ---
    @app.before_request
    def _enforce_auth():
        from flask import request

        # 公共端点 —— 精确匹配或明确前缀（注意：不要再加 "/" 到前缀里，否则 startswith("/") 匹配一切）
        EXACT_PUBLIC = {"/", "/favicon.ico", "/login", "/logout"}
        PREFIX_PUBLIC = (
            "/api/health",
            "/api/auth/login",
            "/api/auth/logout",   # POST 登出，需要 session 但它自己处理
        )

        if request.path in EXACT_PUBLIC:
            return None
        if any(request.path.startswith(p) for p in PREFIX_PUBLIC):
            return None

        # Unmatched URL → let Flask return 404 normally
        if request.endpoint is None:
            return None

        view_func = app.view_functions.get(request.endpoint)
        if view_func is None:
            return None

        # View decorated with @login_required → check session
        if getattr(view_func, "login_required", False):
            if not session.get("user_id"):
                # 页面路由（非 /api）→ 302 直达登录页；API 端点 → 401 JSON
                if request.path.startswith("/api/"):
                    abort(401)
                return redirect("/login")

    return app
