## Context

CampusClaw 是 greenfield 校园教学辅助项目，尚无现有代码。本次变更从零搭建：身份认证、RBAC、班级隔离和知识库四项能力。用户约束包括 Docker Compose 部署、`GET /health` 端点、密码哈希存储、密钥仅服务端环境变量。技术栈指定为 **Flask + SQLite**（轻量、教学项目足够、单文件易迁移）。

## Goals / Non-Goals

**Goals:**
- Flask + SQLite 单服务架构，Docker Compose 一键启动
- Flask session（签名 Cookie）做会话，bcrypt 做密码哈希，密钥仅环境变量
- 三层权限：认证（你是谁？）→ 授权（你能做什么？）→ 隔离（你能看谁的数据？），全部在服务端强制执行
- 教师上传的材料写入 SQLite 后立即可在本班查询
- `GET /health` 返回 200 OK
- 首次启动种子脚本自动写入班级、教师、学生预置数据

**Non-Goals:**
- 不实现检索问答、RAG、embedding、向量数据库
- 不集成 LLM、聊天助手、智能问答
- 不实现作业提交、批改、成绩管理
- 不实现 SSO（OAuth/CAS）、多租户、多实例 HA、负载均衡
- 不实现自注册、材料编辑删除版本管理
- 不实现前端 UI（只提供 REST API）
- 不引入 Alembic/Flyway 等迁移工具（首次启动自动建表即可）

## Decisions

### 技术栈

| 组件 | 选型 | 理由 | 备选 |
|------|------|------|------|
| 后端框架 | **Flask 3.x** | 教学场景轻量够用；session/flash/Blueprint 开箱即用；学习成本低 | FastAPI（更现代但偏重）、Django（太重） |
| 数据库 | **SQLite 3** | 单文件、零配置、Docker 内直接挂载卷；教学演示无需独立 db 服务 | PostgreSQL（生产更强但多一容器）、文件系统（无查询能力） |
| 访问方式 | **raw sqlite3 标准库** | 避免额外 ORM 依赖；SQL 直写清晰易教 | Flask-SQLAlchemy（功能强但多一层抽象） |
| 密码哈希 | **passlib[bcrypt]** | 成熟稳定；Windows 本地开发无额外依赖 | argon2（更安全但 Windows 编译复杂） |
| 会话 | **Flask 内置 session**（itsdangerous 签名 Cookie） | 无状态 cookie、无需 Redis；Flask 自带；密钥从 APP_SECRET 读 | JWT（无状态但需要额外库）、Session+Redis（多一依赖） |
| 种子执行 | **应用启动时自动检测** | db 文件不存在 → 运行 seed；否则跳过 | 独立初始化命令（需要手动操作） |

### 目录结构

```
app/
  __init__.py          # Flask app factory、session 配置、before_request 注册
  config.py            # 环境变量读取（APP_SECRET、DATABASE_PATH）
  db.py                # 数据库连接、建表、seed 检测
  auth.py              # /api/auth/login + /api/auth/logout、@login_required、@role_required
  materials.py         # /api/materials 三个端点 + Repository（list_for_user / get_for_user / create_for_user）
  health.py            # GET /health
scripts/
  seed.py              # 预置数据写入（users + materials 样本）
Dockerfile             # python:3.12-slim
docker-compose.yml     # 单 app 服务 + volume 持久化 db
requirements.txt       # flask、passlib[bcrypt]、itsdangerous
.env.example           # APP_SECRET、DATABASE_PATH
README.md              # 项目说明，开头三行为项目名 + 一句话描述 + 快速启动
```

### 会话机制

```
登录流程：
  POST /api/auth/login {username, password}
    → 查 users 表匹配 username
    → passlib.verify(password, stored_hash)
    → Flask session["user_id"] = id
    → Flask session["role"]  = role
    → Flask session["class_id"] = class_id
    → 返回 200 + {id, username, role, class_id}

后续请求：
  Flask 自动读取签名 Cookie → session 反序列化
  → before_request: 若端点标记 login_required 且 session 无 user_id → abort(401)
  → 路由装饰器 @role_required("teacher") 检查 session["role"] → 非 teacher → abort(403)

登出：
  POST /api/auth/logout → session.clear() → 返回 200
```

session 存储在浏览器签名 Cookie 中，服务端无状态；密钥 `APP_SECRET` 缺失时 Flask 在 startup 报错（`RuntimeError: SECRET_KEY missing`）。

### 服务端班级隔离（Repository 层强制）

Repository 的**每个**查询方法都强制注入 `class_id` 过滤条件，不管路由层是否传了 class_id：

```python
# 伪代码 — 体现强制覆盖
def create_for_user(self, user, title, content, client_supplied_class_id=None):
    final_class_id = user.class_id            # 永远用服务端的
    assert client_supplied_class_id is None or client_supplied_class_id == user.class_id
    # ↑ 可选：拒绝客户端伪造；或静默覆盖都可以，此处选覆盖
    conn.execute("INSERT INTO materials (class_id, owner_id, title, content) VALUES (?, ?, ?, ?)",
                 (user.class_id, user.id, title, content))

def list_for_user(self, user):
    return conn.execute(
        "SELECT * FROM materials WHERE class_id = ? ORDER BY created_at DESC",
        (user.class_id,)
    ).fetchall()

def get_for_user(self, user, material_id):
    row = conn.execute(
        "SELECT * FROM materials WHERE id = ? AND class_id = ?",
        (material_id, user.class_id)
    ).fetchone()
    if row is None:
        abort(404)   # 跨班访问 → 看起来像不存在，不泄露存在性
    return row
```

关键原则：**class_id 永远来自服务端 session，不信任请求体或 query string 传入值。**

### 上传数据流

```
浏览器
  │
  │  POST /api/materials  {title, content}
  │  Cookie: session=<Flask 签名>
  ▼
Flask 路由
  │
  ├─ before_request:  解析 session → current_user
  │                    session 缺失 → 401 Unauthorized
  │
  ├─ @role_required("teacher")   session["role"] != "teacher" → 403 Forbidden
  │
  ├─ 参数校验: title/content 必填 → 缺失 → 400 Bad Request
  │
  ▼
Repository.create_for_user(current_user, title, content)
  │  (class_id 从 current_user.class_id 取，忽略客户端任何 class_id 字段)
  ▼
SQLite: INSERT INTO materials (class_id, owner_id, title, content, created_at) VALUES (...)
  │
  ▼
返回 201 Created + {id, title, class_id, owner_id, created_at}
```

### 数据模型

```sql
-- SQLite 方言（无 UUID，用 INTEGER 自增或 TEXT 存 uuid4）

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    UNIQUE NOT NULL,
    password_hash TEXT    NOT NULL,         -- bcrypt 哈希，约 60 字符
    role          TEXT    NOT NULL CHECK (role IN ('teacher', 'student')),
    class_id      TEXT    NOT NULL,         -- TEXT 存 uuid4()，逻辑班级标识
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS materials (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id   TEXT    NOT NULL,            -- 写入时强制等于 current_user.class_id
    owner_id   INTEGER NOT NULL REFERENCES users(id),
    title      TEXT    NOT NULL,
    content    TEXT    NOT NULL,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_materials_class ON materials(class_id);
```

### Docker Compose 结构

因为 SQLite 是单文件，只需一个 app 服务：

```yaml
services:
  app:
    build: .
    image: campusclaw:dev
    container_name: campusclaw-app
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - campusclaw-data:/app/data     # SQLite db 文件持久化
    command: python -m flask run --host 0.0.0.0 --port 8000

volumes:
  campusclaw-data:
```

`.env.example`：
```
APP_SECRET=change-me-to-a-random-32-byte-string
DATABASE_PATH=/app/data/campusclaw.db
FLASK_ENV=development
```

`Dockerfile`：
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "-m", "flask", "run", "--host", "0.0.0.0", "--port", "8000"]
```

首次容器启动流程：
1. `db.connect(DATABASE_PATH)` → 打开 SQLite 文件（不存在则创建）
2. `db.init_schema()` → 执行两张 CREATE TABLE IF NOT EXISTS
3. `db.seed_if_empty()` → 检测 users 表行数为 0 → 调用 `scripts/seed.py` 写入 1 班级 + 1 教师 + 2 学生
4. Flask 监听 0.0.0.0:8000

### GET /health

```python
@app.get("/api/health")
def health():
    return {"status": "ok"}, 200
```

要求：
- 无需认证（不加 `@login_required`）
- 不走数据库（避免 db 断连影响 health）
- 响应码 200，响应体任意 JSON（推荐 `{"status": "ok"}`）
- 健康检查用于 Docker/Compose `healthcheck` 配置

### API 汇总

| 方法 | 路径 | 认证 | 角色 | class_id 过滤 | 说明 |
|------|------|------|------|--------------|------|
| POST | /api/auth/login | 否 | - | - | 登录，设 session |
| POST | /api/auth/logout | 是 | - | - | 清 session |
| GET  | /api/health | 否 | - | - | 健康检查 |
| POST | /api/materials | 是 | teacher | 自动注入 current_user.class_id | 上传材料 |
| GET  | /api/materials | 是 | teacher/student | WHERE class_id = current_user.class_id | 列表 |
| GET  | /api/materials/\<id\> | 是 | teacher/student | WHERE class_id = current_user.class_id AND id = ? | 详情 |

### 种子数据（users + materials 双表预置）

`scripts/seed.py` 通过 passlib 对预置密码 bcrypt 哈希后写入 users 表，并同步写入 materials 表的样本材料。所有密码哈希值在首次容器启动时生成，**绝不明文写入任何文件**。

**预置 users（class_id 统一为 `"class-001"`）：**
| username | 初始密码 | role | class_id |
|----------|----------|------|----------|
| `teacher` | `teacher123` | teacher | class-001 |
| `student1` | `student123` | student | class-001 |
| `student2` | `student123` | student | class-001 |

**预置 materials（teacher 账号上传，class_id = "class-001"）：**
| title（样本） | content（样本） | owner_id | class_id |
|--------------|----------------|----------|----------|
| 《高等数学》第一章课件 | 本章节讲解极限、导数、积分的基本概念与典型例题... | teacher 的 user id | class-001 |
| 数据结构复习提纲 | 线性表、栈与队列、树与图、排序与查找算法要点... | teacher 的 user id | class-001 |

这样首次部署后，教师/学生登录即可直接 GET `/api/materials` 查到两条样本材料，立即可验证：教师上传 → 同班可见 → 班级隔离。

### README 三行

项目根 `README.md` **开头三行**固定为以下内容（不含空行，紧接着是正文其余部分）：

```
# CampusClaw
一个 Flask + SQLite 的校园知识库后端：账号密码登录、教师上传教学材料、按班级隔离数据。
快速启动：cp .env.example .env && docker compose up -d && curl http://localhost:8000/api/health
```

- 第 1 行：项目名（H1 标题）
- 第 2 行：一句话描述（覆盖认证、上传、隔离三个核心特性）
- 第 3 行：快速启动命令（复制环境变量 → 启动 Compose → 健康检查）

预置账号表格、API 端点列表、技术栈说明作为 README 正文的后续章节，不在这三行中。

## Risks / Trade-offs

- **[SQLite 并发写入限制]** → 教学场景写操作极少（上传材料），单用户同时上传概率可忽略；如遇 "database is locked" 可加短重试；生产换 PostgreSQL 是标准路径
- **[Flask session Cookie 跨站问题]** → 开发阶段 SameSite=Lax 够用；生产部署需调整 Cookie 属性或换后端 session 存储
- **[种子账号密码公开硬编码在源码]** → 仅限开发/演示镜像使用，生产部署时必须手动删除或换正式用户数据；README 提醒改密码
- **[无数据库 schema 版本管理]** → 教学项目两张表，schema 演进频繁时可人工删库重建；后续可引入 Alembic

## Migration Plan

无需历史数据迁移（greenfield）。部署步骤：
1. 编写所有源码文件 + Dockerfile + docker-compose.yml + requirements.txt + .env.example + scripts/seed.py
2. 创建 `.env`（从 `.env.example` 复制，填入随机 `APP_SECRET`）
3. `docker compose up -d` → 自动建表 + 种子
4. `curl http://localhost:8000/api/health` → 200 + `{"status": "ok"}`
5. 登录 → 上传 → 同班可见 / 跨班不可见，端到端验证

**Rollback**：`docker compose down -v` 删掉卷和容器即可，无其他数据残留。

## Open Questions

- 无
