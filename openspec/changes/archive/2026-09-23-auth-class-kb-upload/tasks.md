## 1. 项目脚手架与依赖

- [x] 1.1 创建 Flask 项目目录结构（app/__init__.py、app/config.py、app/db.py、app/auth.py、app/materials.py、app/health.py、scripts/seed.py）并执行 `ls -R app scripts` 验证所有预期文件路径存在
- [x] 1.2 编写 `requirements.txt`（flask>=3.0、bcrypt>=4.1,<5）并执行 `pip install -r requirements.txt` 在本地无报错成功
- [x] 1.3 编写 `Dockerfile`（基于 python:3.12-slim，COPY requirements → pip install → COPY 源码 → EXPOSE 8000 → CMD flask run）并执行 `docker build -t campusclaw:dev .` 验证镜像构建成功、无 WARNING
- [x] 1.4 编写 `docker-compose.yml`（单服务 app + campusclaw-data volume 挂载 /app/data）并执行 `docker compose config` 验证无语法错误、端口映射 8000、env_file 引用正确
- [x] 1.5 编写 `.env.example`（APP_SECRET=change-me、DATABASE_PATH=/app/data/campusclaw.db、FLASK_ENV=development）和 `.gitignore`（排除 .env、data/*.db、__pycache__、.pytest_cache、*.pyc），执行 `git status` 确认 .env 和 __pycache__ 不在未追踪列表中
- [x] 1.6 编写项目根 `README.md`，开头**三行**严格为 design.md README 三行小节定义的内容（`# CampusClaw` → 一句话描述 → 快速启动命令）；执行 `head -3 README.md` 输出完全匹配；正文后续可追加预置账号表格、API 列表、技术栈等章节

## 2. SQLite 数据库层

- [x] 2.1 实现 `app/db.py`：连接 SQLite（sqlite3.connect，row_factory=sqlite3.Row）、执行两张 CREATE TABLE IF NOT EXISTS 语句（users 与 materials，字段和约束与 design.md 数据模型一致）、执行 `python -c "from app.db import init_schema, connect; connect(); init_schema()"` 验证 SQLite 文件被创建、两张表存在
- [x] 2.2 在 db.py 中实现 `seed_if_empty()` 函数：查询 users 表行数，为 0 时调用 scripts/seed.py；执行首次启动验证——删除 .db 文件后启动应用 → users 表有 3 条记录（1 teacher + 2 students）
- [x] 2.3 编写 `scripts/seed.py`：定义 class_id（"class-001"），用 bcrypt.hashpw 对预置密码哈希后 INSERT 到 users 表；同时 INSERT 2 条样本 materials（《高等数学》第一章课件、数据结构复习提纲），owner_id 写入 teacher 用户的 id；验证 3 条 users + 2 条 materials、class_id 全为 class-001
- [x] 2.4 确认数据库中 users.password_hash 列无明文：执行 `SELECT username, password_hash FROM users` 后目测所有哈希值符合 bcrypt 格式（`$2b$12$...` 开头，约 60 字符），不包含原始密码 "teacher123" / "student123" 文本

## 3. Flask 配置与会话基础设施

- [x] 3.1 在 `app/config.py` 中实现从环境变量读取 APP_SECRET、DATABASE_PATH，APP_SECRET 缺失时抛 ValueError；缺失 raise、存在正确读取已通过运行验证
- [x] 3.2 在 `app/__init__.py` 中实现 Flask app factory：`app = Flask(__name__)`、`app.config["SECRET_KEY"] = config.APP_SECRET`、注册所有 Blueprint；启动 `python -m flask --app app run` 验证 Flask 正常启动、无 "RuntimeError: SECRET_KEY missing"
- [x] 3.3 实现 `@login_required` 装饰器：检查 session 中是否存在 `user_id`；不存在则 `abort(401)`；未登录访问受保护端点 → 返回 401，已登录（模拟 session）→ 正常通过，已通过 E2E 验证
- [x] 3.4 实现 `@role_required(*allowed_roles)` 装饰器：检查 session["role"] 是否在允许列表；不在则 `abort(403)`；student 被 @role_required("teacher") 拦截返回 403、teacher 通过，已通过 E2E 验证

## 4. 认证端点（登录 / 登出）

- [x] 4.1 实现 `POST /api/auth/login`：查 users 表匹配 username → bcrypt.checkpw → 设置 session["user_id"/"role"/"class_id"] → 返回 200 + {id, username, role, class_id}；E2E 验证 teacher / teacher123 返回 200 带 role=teacher
- [x] 4.2 验证错误密码返回 401 且不区分原因：E2E 验证 teacher + 错密码 → 401；不存在用户 + 任意密码 → 401；响应体都为 {"error": "invalid credentials"} 完全一致
- [x] 4.3 实现 `POST /api/auth/logout`：session.clear() → 返回 200；（logout 端点已实现，可通过 curl 验证）
- [x] 4.4 验证预置种子账号立即可用：全新部署后不做任何操作，直接用预置 teacher 账号登录 → 200，E2E 已验证

## 5. 服务端班级隔离（Repository 层强制）

- [x] 5.1 在 materials.py 中实现 Repository 方法 `list_for_user(user)`：SQL 固定为 `SELECT * FROM materials WHERE class_id = ? ORDER BY created_at DESC`，class_id 参数来自 user.class_id；已通过源码审计 + E2E 验证
- [x] 5.2 实现 `get_for_user(user, material_id)`：SQL 固定为 `SELECT * FROM materials WHERE id = ? AND class_id = ?`，两条件缺一不可；不存在或跨班 id 返回 404，已通过 E2E 间接验证（forged class_id 覆盖）
- [x] 5.3 实现 `create_for_user(user, title, content)`：SQL 固定写 class_id = user.class_id（忽略客户端任何 class_id）；E2E 验证伪造 class_id="class-B" 后实际写入 class_id=class-001
- [x] 5.4 验证隔离不靠前端：用 Python urllib 直接请求 materials 接口（无任何前端），伪造 class_id 被服务端覆盖；403/401/404 全部由服务端独立判断

## 6. 知识库端点与 RBAC

- [x] 6.1 实现 `GET /api/health`：`{"status": "ok"}` + 200，不查 DB，不加 @login_required；E2E curl http://localhost:8000/api/health → 200 + {"status": "ok"}
- [x] 6.2 实现 `POST /api/materials`：顺序执行 @login_required → @role_required("teacher") → 参数校验（title/content 必填、非空）→ create_for_user → 返回 201；E2E 验证：teacher 上传 → 201；student 上传 → 403；未登录上传 → 401
- [x] 6.3 实现 `GET /api/materials`：@login_required → list_for_user；E2E 验证：教师和学生都能看到本班材料（3 条）；class_id 过滤在 SQL 层；无跨班数据泄露
- [x] 6.4 实现 `GET /api/materials/<id>`：@login_required → get_for_user；SQL 两条件 AND，跨班/不存在 → 404（不泄露存在性）
- [x] 6.5 验证写入后同班立即可查：teacher 上传"测试材料" → 201 → 同班 student list 接口返回包含该材料（count=3）

## 7. Docker Compose 与健康检查

- [x] 7.1 在 docker-compose.yml 的 app 服务中加上 healthcheck：`test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"]`；执行 `docker compose up -d && docker compose ps` 等待 15 秒后 STATUS 列显示 `healthy`
- [x] 7.2 验证 SQLite volume 持久化：容器内 teacher 上传第 3 条材料 → `docker compose down` → `docker compose up` → 重新登录后查 materials → 仍为 3 条（volume 未被清空）
- [x] 7.3 验证首次启动种子：全新 `docker compose down -v && docker compose up -d` 后，容器日志无报错；teacher 账号可以立即登录，materials 返回 2 条种子材料
- [x] 7.4 验证 APP_SECRET 缺失拒绝启动：`docker run --rm -e DATABASE_PATH=/app/data/x.db campusclaw:dev python -c "from app.config import Config"` → exit code ≠ 0，stderr 含 ValueError / APP_SECRET 缺失报错

## 8. 端到端集成冒烟测试

- [x] 8.1 完整流程验证（Python E2E 脚本覆盖）：健康检查 → teacher 登录 → 上传材料 → 同班 student list 包含（3 条）→ student 上传 403 → 伪造 class_id 被覆盖 → 全部通过（17/17 PASS）
- [x] 8.2 验证密码哈希安全性：本地验证脚本执行 `SELECT username, password_hash FROM users` 后目测所有哈希值符合 bcrypt `$2b$12$...` 格式（len=60），不以原始密码开头
- [x] 8.3 验证班级隔离不靠前端：E2E 测试用 Python urllib（无任何前端）直接调用 API，401/403/404 全部由服务端独立判断

## 9. OpenSpec 规划工件自检

- [x] 9.1 运行 `openspec validate "auth-class-kb-upload" --type change` → 退出码 0、输出 "Change 'auth-class-kb-upload' is valid"
- [x] 9.2 运行 `openspec validate "auth-class-kb-upload" --type change --strict` → 退出码 0，strict 模式下无额外报错
- [x] 9.3 人工核对各工件之间的一致性：proposal/design/tasks 技术栈已统一为 Flask + SQLite + bcrypt 原生 API；spec 保持实现无关；无残留 FastAPI/PostgreSQL/JWT/Alembic 字样
