## Why

CampusClaw 目前尚未具备用户身份体系和数据隔离能力。教师无法安全地上传教学材料，学生也无法基于班级边界访问资源——任何人都可能看到他人的资料，或未授权地修改内容。本次变更为平台补上认证、授权、隔离和知识库四条支柱，使教师上传的教学材料仅限本班可见、且只有教师角色能写入。

## What Changes

- 新增账号密码登录流程，未登录访问受保护页面时返回 401 并引导至登录页
- 密码哈希存储（bcrypt/argon2），禁止明文持久化；密钥仅存服务端环境变量
- 引入角色模型（teacher / student），上传接口对 student 返回 403 Forbidden
- 引入班级数据边界：所有材料读写在服务端按 `class_id` 过滤，跨班访问返回 404/403
- 教师上传的材料写入知识库表/集合，本班材料列表接口可查到该记录
- 容器化部署：Docker Compose 启动整个应用栈
- 提供健康检查端点 `GET /health`
- 首次启动时通过种子脚本自动写入预置班级、教师、学生账号，以及本班样本材料 2~3 条（登录即可直接验证列表/隔离）
- 项目根目录提供 README.md，开头三行为项目名、一句话描述、快速启动命令

## Non-Goals

- **检索问答**：本项目不实现向量检索、RAG、知识库问答等功能，材料以文本形式存储和检索，不做 embedding 或相似度匹配
- **对话助手**：不集成任何 LLM（包括 OpenAI、本地模型、开源模型等），不提供聊天、智能问答、自动摘要等 AI 功能
- **作业提交与批改**：不实现作业发布、学生提交、自动/人工批改、成绩管理等功能
- **SSO / 生产级 HA**：不实现 OAuth、CAS、企业 SSO 等第三方单点登录；不部署为多实例高可用集群、不做负载均衡或数据库主从
- **自注册 / 开放注册**：用户由种子脚本或管理员预置，不开放自助注册入口
- **材料编辑 / 删除 / 版本管理**：上传后不可修改或删除，同一文件多次上传生成多条独立记录
- **前端 UI**：仅提供 REST API，前端界面在后续独立工作中实现

## Capabilities

### New Capabilities

- `user-auth`: 登录、密码哈希校验、会话令牌签发、认证拦截
- `rbac`: teacher / student 角色、基于角色的端点访问控制、student 调用上传接口被拒绝
- `class-isolation`: 用户-班级关联、服务端 `class_id` 过滤、跨班访问拒绝（不靠前端隐藏按钮）
- `knowledge-base`: 教学材料上传端点、持久化存储、按班级查询列表、仅 teacher 角色可写

### Modified Capabilities

无（项目为 greenfield）

## Impact

- **技术栈（变更）**：后端 **Flask**（Python 3.12）；数据库 **SQLite 3**（通过 Flask-SQLAlchemy 或 sqlite3 标准库）；ORM 使用轻量封装或 raw SQL；密码哈希用 passlib[bcrypt]；会话使用 Flask 内置 session 或 itsdangerous 签名 Cookie
- **数据模型**：`users` 表（id, username, password_hash, role, class_id, created_at）、`materials` 表（id, class_id, owner_id, title, content, created_at），共两张表，无额外 schema 迁移工具（首次启动自动建表）
- **API 端点**：`POST /api/auth/login`、`GET /api/auth/logout`、`GET /api/health`、`POST /api/materials`（需 teacher）、`GET /api/materials`（按当前用户 class_id 过滤）、`GET /api/materials/<id>`
- **中间件 / Hook**：Flask `before_request` 钩子做认证拦截；装饰器（`@login_required`、`@role_required("teacher")`）做授权；Repository 查询方法自动附加 class_id 过滤
- **预置数据**：`scripts/seed.py` 在应用首次启动时创建 1 班级、1 教师、2 学生账号（密码 bcrypt 哈希），同时预置 2 条样本材料写入 materials 表；首次登录即可直接查询本班材料列表
- **README**：项目根 `README.md` 开头三行为项目名、一句话描述、快速启动命令（`docker compose up -d`）
- **部署**：`Dockerfile`（python:3.12-slim）+ `docker-compose.yml`（单服务 app，SQLite 直接用容器内文件，挂载 volume 持久化）
- **环境变量**：`APP_SECRET`（Flask session 签名密钥，必须设）、可选 `FLASK_ENV`
