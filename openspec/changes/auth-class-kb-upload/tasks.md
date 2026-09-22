## 1. 项目脚手架与依赖

- [ ] 1.1 创建 Flask 项目目录结构（app/__init__.py、app/config.py、app/db.py、app/auth.py、app/materials.py、app/health.py、scripts/seed.py）并执行 `ls -R app scripts` 验证所有预期文件路径存在
- [ ] 1.2 编写 `requirements.txt`（flask>=3.0、passlib[bcrypt]>=1.7）并执行 `pip install -r requirements.txt` 在本地或 Docker 构建中无报错成功
- [ ] 1.3 编写 `Dockerfile`（基于 python:3.12-slim，COPY requirements → pip install → COPY 源码 → EXPOSE 8000 → CMD flask run）并执行 `docker build -t campusclaw:dev .` 验证镜像构建成功、无 WARNING
- [ ] 1.4 编写 `docker-compose.yml`（单服务 app + campusclaw-data volume 挂载 /app/data）并执行 `docker compose config` 验证无语法错误、端口映射 8000、env_file 引用正确
- [ ] 1.5 编写 `.env.example`（APP_SECRET=change-me、DATABASE_PATH=/app/data/campusclaw.db、FLASK_ENV=development）和 `.gitignore`（排除 .env、data/*.db、__pycache__、.pytest_cache、*.pyc），执行 `git status` 确认 .env 和 __pycache__ 不在未追踪列表中
- [ ] 1.6 编写项目根 `README.md`，开头**三行**严格为 design.md README 三行小节定义的内容（`# CampusClaw` → 一句话描述 → 快速启动命令）；执行 `head -3 README.md` 输出完全匹配；正文后续可追加预置账号表格、API 列表、技术栈等章节

## 2. SQLite 数据库层

- [ ] 2.1 实现 `app/db.py`：连接 SQLite（sqlite3.connect，row_factory=sqlite3.Row）、执行两张 CREATE TABLE IF NOT EXISTS 语句（users 与 materials，字段和约束与 design.md 数据模型一致）、执行 `python -c "from app.db import init_schema, connect; connect(); init_schema()"` 验证 SQLite 文件被创建、两张表存在
- [ ] 2.2 在 db.py 中实现 `seed_if_empty()` 函数：查询 users 表行数，为 0 时调用 scripts/seed.py；执行首次启动验证——删除 .db 文件后启动应用 → users 表有 3 条记录（1 teacher + 2 students）
- [ ] 2.3 编写 `scripts/seed.py`：定义 class_id（"class-001"），用 passlib.hash.bcrypt.hash 对预置密码哈希后 INSERT 到 users 表；同时 INSERT 2 条样本 materials（标题/内容参照 design.md 种子数据小节），owner_id 写入 teacher 用户的 id；执行 `python -c "from app.db import connect; r=connect().execute('SELECT username, role, class_id FROM users').fetchall(); m=connect().execute('SELECT id, title, class_id FROM materials').fetchall(); print('users:', r); print('materials:', m)"` 验证 3 条 users + 2 条 materials、class_id 全为 class-001
- [ ] 2.4 确认数据库中 users.password_hash 列无明文：执行 `SELECT username, password_hash FROM users` 后目测所有哈希值符合 bcrypt 格式（`$2b$12$...` 开头，约 60 字符），不包含原始密码 "teacher123" / "student123" 文本

## 3. Flask 配置与会话基础设施

- [ ] 3.1 在 `app/config.py` 中实现从环境变量读取 APP_SECRET、DATABASE_PATH，APP_SECRET 缺失时抛 ValueError；编写单元测试验证缺失时 raise、存在时正确读取
- [ ] 3.2 在 `app/__init__.py` 中实现 Flask app factory：`app = Flask(__name__)`、`app.config["SECRET_KEY"] = config.APP_SECRET`、注册所有 Blueprint；启动 `python -m flask --app app run` 验证 Flask 正常启动、无 "RuntimeError: SECRET_KEY missing"
- [ ] 3.3 实现 `@login_required` 装饰器：检查 session 中是否存在 `user_id`；不存在则 `abort(401)`；编写单元测试验证：未登录访问受保护端点 → 返回 401，已登录（模拟 session）→ 正常通过
- [ ] 3.4 实现 `@role_required(*allowed_roles)` 装饰器：检查 session["role"] 是否在允许列表；不在则 `abort(403)`；编写单元测试验证 student 身份被 @role_required("teacher") 拦截返回 403、teacher 通过

## 4. 认证端点（登录 / 登出）

- [ ] 4.1 实现 `POST /api/auth/login`：查 users 表匹配 username → passlib.verify → 设置 session["user_id"/"role"/"class_id"] → 返回 200 + {id, username, role, class_id}；执行 curl 验证 teacher / teacher123 返回 200 带 role=teacher
- [ ] 4.2 验证错误密码返回 401 且不区分原因：curl teacher + 错密码 → 401；curl 不存在用户 + 任意密码 → 401；检查响应体文本是否完全一致（不泄露哪个字段错）
- [ ] 4.3 实现 `POST /api/auth/logout`：session.clear() → 返回 200；验证：登录后登出 → 后续请求 session 被清 → 再次访问受保护端点返回 401
- [ ] 4.4 验证预置种子账号立即可用：全新部署后不做任何操作，直接 curl 预置 teacher 账号登录 → 200

## 5. 服务端班级隔离（Repository 层强制）

- [ ] 5.1 在 materials.py 中实现 Repository 方法 `list_for_user(user)`：SQL 固定为 `SELECT * FROM materials WHERE class_id = ? ORDER BY created_at DESC`，class_id 参数来自 user.class_id；执行 SQLAlchemy/sqlite3 trace 或打印 SQL 字符串验证 WHERE 条件确实存在
- [ ] 5.2 实现 `get_for_user(user, material_id)`：SQL 固定为 `SELECT * FROM materials WHERE id = ? AND class_id = ?`，两条件缺一不可；验证跨班 id 查询返回 404（通过 Flask test client 或 curl 带他人班的 material id）
- [ ] 5.3 实现 `create_for_user(user, title, content, client_class_id=None)`：SQL 固定写 class_id = user.class_id；编写单元测试：伪造 client_class_id="class-999" 传入 → 实际 INSERT 的 class_id 仍为 user.class_id
- [ ] 5.4 验证隔离不靠前端：用 curl/Burp 直接请求 materials 接口（绕过 UI），A 班 token + B 班的 material id → 404；A 班 token 带 client_class_id="class-B" → 写入的 class_id 仍是 class-A（查库验证）

## 6. 知识库端点与 RBAC

- [ ] 6.1 实现 `GET /api/health`：`{"status": "ok"}` + 200，不查 DB，不加 @login_required；curl http://localhost:8000/api/health → 200 + {"status": "ok"}
- [ ] 6.2 实现 `POST /api/materials`：顺序执行 @login_required → @role_required("teacher") → 参数校验（title/content 必填、非空）→ create_for_user → 返回 201；验证：teacher 登录后上传 → 201；student 登录后上传 → 403；未登录上传 → 401
- [ ] 6.3 实现 `GET /api/materials`：@login_required → list_for_user；验证：教师和学生都能看到本班材料；本班为空时返回 `[]` + 200；A 班 token 查不到 B 班上传的任何记录
- [ ] 6.4 实现 `GET /api/materials/<id>`：@login_required → get_for_user；验证本班 id 返回完整 JSON（含 id, title, owner_id, class_id, created_at）；跨班 id 返回 404；不存在 id 也返回 404
- [ ] 6.5 验证写入后同班立即可查：teacher 上传 A 班材料 → 201 → 同班 student curl list 接口 → 列表包含该材料；他班 token list → 不包含

## 7. Docker Compose 与健康检查

- [ ] 7.1 在 docker-compose.yml 的 app 服务中加上 healthcheck：`test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"]`；执行 `docker compose up -d && docker compose ps` 等待 10 秒后 STATUS 列显示 `healthy`
- [ ] 7.2 验证 SQLite volume 持久化：容器内手动插入一条材料 → `docker compose down` → `docker compose up` → 再次查询材料，那条记录仍在（volume 没被清空）
- [ ] 7.3 验证首次启动种子：全新 `docker compose down -v && docker compose up -d` 后，容器日志中无报错；teacher 账号可以立即登录（说明 seed 已写入）
- [ ] 7.4 验证 APP_SECRET 缺失拒绝启动：临时从 .env 删掉 APP_SECRET → `docker compose down && docker compose up` → 容器立即退出，`docker compose logs` 中可见明确的 SECRET_KEY 缺失报错

## 8. 端到端集成冒烟测试

- [ ] 8.1 完整流程验证（一条 curl 链）：健康检查 → teacher 登录 → 上传材料 A → 同班 student 登录 → list 接口包含 A → 他班 teacher 上传材料 B（需手动插一个他班种子用户）→ A 班 list 不含 B → 全部通过
- [ ] 8.2 验证密码哈希安全性：`docker compose exec app python -c "from app.db import connect; rows=connect().execute('SELECT username, password_hash FROM users').fetchall(); print(rows)"` → 所有哈希值不以原始密码开头、符合 bcrypt `$2b$12$` 格式
- [ ] 8.3 验证班级隔离不靠前端：用 `curl` 直接调用 API 完成 8.1 中的跨班拒绝场景，确认服务端独立工作（无需任何前端页面）

## 9. OpenSpec 规划工件自检

- [ ] 9.1 运行 `openspec validate "auth-class-kb-upload" --type change` → 退出码 0、输出 "Change 'auth-class-kb-upload' is valid"
- [ ] 9.2 运行 `openspec validate "auth-class-kb-upload" --type change --strict` → 退出码 0，strict 模式下无额外报错
- [ ] 9.3 人工核对各工件之间的一致性：proposal.md 的 Impact、design.md 的技术栈、spec 的实现无关表述、tasks 的 Flask/SQLite 栈四处完全对齐，不得出现残留的 FastAPI / PostgreSQL / JWT / Alembic 等字样
