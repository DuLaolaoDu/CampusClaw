# 设计：hide-api-class-switch-seed

## Context

现状（auth-class-kb-upload + add-file-upload 之后）：Flask 单服务发布 8000 端口，页面与 /api 同源；dashboard.html 依赖浏览器 fetch /api 完成 login 后的一切交互；教师固定 class-001，无切换入口；种子数据全部在 class-001（3 用户 + 2 材料），隔离不可演示。见 proposal.md - Why。

## Goals / Non-Goals

- Goals：/api 对用户不可达（nginx 边缘屏蔽 + 前端 SSR 化）；教师按任教关系切换生效班级；双班种子数据 + 旧 volume 幂等补种
- Non-Goals：CSRF token 机制（SameSite=Lax 默认防护，风险记录在案）、用户注册/管理、HTTPS、nginx 限流/缓存、删除内部 API、内容解析增强/向量化

## Decisions

### D1. 部署拓扑：compose 双服务，nginx 为唯一入口

```yaml
services:
  app:        # Flask，删去 ports，仅内部网络
  edge:       # nginx:alpine（走 daocloud mirror 拉取）
    ports: ["8000:80"]     # 对外 URL 仍是 http://localhost:8000，用户书签不变
    volumes: ["./nginx/default.conf:/etc/nginx/conf.d/default.conf:ro"]
```

nginx 规则（`nginx/default.conf`）：
- `location /api/ { return 404; }` —— 一律 404，不转发、不区分端点存在性
- `location / { proxy_pass http://app:8000; }` —— 页面 + 用户侧下载
- `client_max_body_size 12m;` —— 不低于应用 10MB 上限（余量给 multipart 开销）
- healthcheck 保持容器内直连 `localhost:8000/api/health`，不经过 nginx，不对外发布

备选：Windows 下单文件 bind mount 失败时，改为 `nginx/` 目录 + Dockerfile 构建自定义镜像（COPY conf）。

### D2. 前端 SSR 化：页面路由接管全部浏览器交互

`app/views.py` 扩展为完整页面路由集（均带现有 `@login_required` 语义，未登录 302 登录页——before_request 现有逻辑对非 /api 路径已如此）：

| 路由 | 方法 | 说明 |
|---|---|---|
| `/login` | GET/POST | 登录表单页 / 校验+建会话+redirect |
| `/logout` | POST | 清会话 → redirect /login |
| `/dashboard` | GET | 服务端查询 MaterialsRepo 渲染列表 |
| `/materials` | POST | 页面 multipart 上传（teacher） |
| `/materials/<id>/download` | GET | 用户侧下载（见 D5） |
| `/class/switch` | POST | 教师切换生效班级（见 D3） |

- dashboard.html 重写：Jinja2 循环渲染材料列表；预览用原生 `<details><pre>`（零 JS 展开）；错误用 Flask `flash` + `get_flashed_messages`（PRG 模式，错误不进 URL）；删除全部 fetch JS 与 `__user__` 注入 hack（服务端直接渲染用户信息）；新增 login.html
- 上传表单合一：`<form method=post enctype=multipart/form-data>` 含 title + content(textarea) + file；服务端有附件走文件路径（复用 `_validate_file` + `extract_text`），无附件走文本路径
- 内部 API（/api/auth/*、/api/materials*、/api/health）全部保留、行为不变，仅外部不可达

### D3. 生效班级：session.active_class + teacher_classes 校验

- 新表：`teacher_classes(teacher_id INTEGER NOT NULL REFERENCES users(id), class_id TEXT NOT NULL, UNIQUE(teacher_id, class_id))`；新表用 `CREATE TABLE IF NOT EXISTS` 即可，无需 PRAGMA 迁移
- 登录（页面与 API 同逻辑）：`session["active_class"] = user.class_id`
- `get_current_user()` 注入 `effective_class`：teacher 取 `session["active_class"]`，student 恒取自身 class_id（学生即使构造请求也被 role 校验挡在切换端点外）
- `POST /class/switch`：`@login_required @role_required("teacher")`；目标 ∈ `MaterialsRepo/新 Repo.list_taught_classes(teacher_id)` → 更新 session；否则 403；学生 403；PRG 回 dashboard
- 所有 Repo 方法（create/create_file/list/get）把取值来源从 `user["class_id"]` 改为 `user["effective_class"]`——隔离 WHERE 与写入归属自动跟随切换，跨班 404 语义不变

### D4. 种子扩展：双班预置 + 每次启动幂等补种

预置全集（在现有基础上新增）：

```
users:      teacher2/teacher123 (teacher, class-002)    student3/student123 (student, class-002)
teacher_classes: (teacher→class-001), (teacher→class-002), (teacher2→class-002)
materials:  class-002 样本材料 2 条（owner=teacher2，标题固定含"预置"字样）
```

- `seed_if_empty` 改造为 `seed_preset(conn)` 每次启动执行：users 以 username 判重、teacher_classes 依赖 UNIQUE 判重（INSERT OR IGNORE）、样本材料以固定 title 判重；空库时行为与旧 seed 等价（3+2 原有预置保留不变）
- 旧 volume 升级路径：既有 teacher/student1/student2/材料不动 → 自动补出 teacher2/student3/class-002 材料/任教关系 → teacher 登录即可切换两班演示隔离
- 密码仍 bcrypt 加盐哈希；预置口令沿用文档化约定（teacher2 与 teacher 同密码风格）

### D5. 用户侧下载路由：页面语义

`GET /materials/<id>/download`：login_required → `get_for_user(user, id)`（按生效班级）→ None/纯文本/磁盘缺文件 404 → `send_file(path, download_name=orig_name, as_attachment=True)`。未认证由 before_request 自动 302 登录页（页面路由语义），API 下载路由保留在 /api 侧供内部使用。

### D6. 验证策略调整

- 页面闭环（登录→列表→上传→下载→切换→登出）经 nginx 入口（http://localhost:8000）用 HTTP 验证：表单提交用 curl -F/-d + cookie jar + 断言重定向与 HTML 内容
- 外部 API 屏蔽：入口 curl /api/* 断言 404；宿主机直连 app 端口断言失败
- 内部 API 回归：`docker compose exec app python -c`（容器网络内）登录 + 调 /api 断言行为不变
- 隔离演示：teacher 切到 class-002 → 仅见 class-002 材料 → student3 无法上传/切换 → 跨班 id 访问 404

## Risks / Trade-offs

- **CSRF 未加 token**：表单写路由（上传/切换/登出）依赖 SameSite=Lax Cookie 缓解；教学演示项目接受，记录为后续可加 flask-wtf 的演进项
- **Windows bind mount nginx.conf 可能失败**：回退方案构建自定义 nginx 镜像（D1 备选），不影响行为
- **外部 404 吞掉健康检查**：运维排障需进容器或 `docker compose exec` 查健康；文档写明
- **flash 依赖 session 签名**：APP_SECRET 已强制，无新增密钥面
- **teacher 兼任两班是刻意的演示设定**：真实生产应收紧为独立教师账号；种子语义已在 user-auth 差量中写明
- **旧 dashboard.html 完全废弃**：无兼容包袱（单页应用逻辑整体替换），回滚即回退整个变更

## Migration Plan

1. 部署新版本：app 容器去掉端口发布，edge 容器接入 8000:80
2. 启动时 `teacher_classes` 建表 + `seed_preset` 幂等补种，旧数据零改动
3. 回滚安全：teacher_classes 多余但无害；nginx 配置移除后恢复单服务即可（新列/新表不阻塞旧代码）

## Open Questions

- 无。
