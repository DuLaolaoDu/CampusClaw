# Tasks: hide-api-class-switch-seed

## 1. 数据层：任教关系与生效班级

- [x] 1.1 `app/db.py`：SCHEMA_SQL 增加 `teacher_classes(teacher_id, class_id, UNIQUE)` 表；`seed_if_empty` 改造为 `seed_preset(conn)`（每次启动跑，按自然键判重幂等补种）；verify: 临时旧库副本启动后 `PRAGMA` 确认新表存在且旧行未动
- [x] 1.2 `scripts/seed.py`：补 class-002 预置（teacher2/teacher123、student3/student123、2 条 class-002 样本材料）与 3 条 teacher_classes 关系；判重插入（INSERT OR IGNORE / username 判重）；verify: 对含旧数据的库执行两次，行数不变；空库执行产出全量预置
- [x] 1.3 `app/auth.py` `get_current_user()`：注入 `effective_class`（teacher 取 session active_class，student 恒取自身 class_id）；login 时初始化 `session["active_class"] = user.class_id`；verify: 单元断言教师/学生的 effective_class 来源
- [x] 1.4 `app/materials.py` Repo：`create_for_user/create_file_for_user/list_for_user/get_for_user` 的 class_id 来源改为 `user["effective_class"]`；新增 `list_taught_classes(teacher_id)` 与 `switch_class(teacher_id, target)` 校验辅助；verify: 单元断言切换后 list/create 归属新班、跨班 get 仍 None

## 2. 页面路由：SSR 化交互

- [x] 2.1 `app/views.py` 新增 `GET/POST /login`、`POST /logout`（未登录访问受保护页面 302 语义沿用 before_request）；新增 `templates/login.html`（表单 + 统一错误提示）；verify: curl 提交正确/错误凭据断言 302→/dashboard 与回显错误
- [x] 2.2 `app/views.py` 重写 `GET /dashboard`：服务端查 `MaterialsRepo.list_for_user` 渲染；重写 `templates/dashboard.html`：Jinja2 列表循环、`<details><pre>` 预览、文件条目（📄 原名 + 大小 + 下载链接）、flash 错误条、删除全部 fetch JS 与 `__user__` hack；verify: HTML 源码无 `/api` 引用且含材料数据
- [x] 2.3 `app/views.py` 新增 `POST /materials` 页面上传（teacher；multipart 合一表单：有附件复用 `_validate_file`+`extract_text`，无附件走文本校验；成功 PRG 回 dashboard，失败 flash 错误）；verify: curl -F 上传 txt/pdf 成功入列表，缺标题/超限/伪装文件 flash 提示且零写入
- [x] 2.4 `app/views.py` 新增 `GET /materials/<int:id>/download`（用户侧下载：生效班级过滤、404 语义、未登录 302）；verify: 本班 200 字节一致、跨班/纯文本 404、未登录 302
- [x] 2.5 `app/views.py` 新增 `POST /class/switch`（teacher only；目标 ∈ 任教关系 → 更新 session.active_class → PRG；否则 403）；dashboard 渲染教师班级切换下拉框（仅任教班级）、学生不渲染；verify: teacher 切换后列表切换、student 请求 403、非任教班 403

## 3. 边缘代理：nginx 入口

- [x] 3.1 新增 `nginx/default.conf`：`location /api/ { return 404; }`、其余 `proxy_pass http://app:8000`、`client_max_body_size 12m`；verify: `docker run` 语法测试或 nginx -t
- [x] 3.2 `docker-compose.yml`：app 删除 ports（仅内部网络）；新增 edge 服务（nginx:alpine，`8000:80`，挂载 conf，depends_on app，healthcheck wget localhost）；verify: `docker compose config` 校验通过
- [x] 3.3 Windows bind mount 失败时回退：`nginx/Dockerfile` 构建自定义镜像 COPY conf（design D1 备选）；verify: 仅在 3.2 挂载失败时执行并记录（挂载一次成功，未触发此备选）

## 4. 端到端验证（容器内，经 nginx 入口）

- [x] 4.1 重建并启动：`docker compose build && up -d`，app 与 edge 均 healthy；宿主机 `curl http://localhost:8000/login` 200；verify: `docker compose ps` 双 (healthy)
- [x] 4.2 外部屏蔽断言：入口 `curl /api/materials`、`/api/health`（带与不带 Cookie）均 404；宿主机直连 app 内部端口失败；verify: 六条 curl 断言
- [x] 4.3 页面闭环（cookie jar + HTML 断言）：登录 teacher → dashboard 含 class-001 材料 → 表单上传 txt → 列表出现 → 下载字节一致 → 切换 class-002 → 列表仅 class-002 → 切回 → 登出回登录页；verify: 全链路断言
- [x] 4.4 RBAC/隔离断言：student1 无上传控件且无切换控件、直接 POST /materials 与 /class/switch 均被拒（302 登录或 403 语义按路由）、student3 可登录看 class-002 材料、跨班 material id 详情/下载 404、伪造 class_id 表单被覆盖；verify: 断言清单
- [x] 4.5 旧 volume 无损迁移：up 后原 2 条 class-001 文本材料与原账号不动；teacher2/student3 出现且可登录；重复 down/up 行数不变；verify: `docker exec` 查 SQL 计数
- [x] 4.6 内部 API 回归：容器网络内 `docker compose exec app` 登录 /api、上传 /api、下载 /api 行为与之前一致（auth/rbac/隔离/文件上传语义不变）；verify: 原 17 项检查容器内复跑 PASS

## 5. 文档与收尾

- [x] 5.1 README：入口改为 http://localhost:8000（nginx）、补预置账号表（双班 5 账号）、页面使用说明、内部 API 标注"仅容器网络内可用"+ 容器内 curl 示例；verify: Select-String 匹配 teacher2 与 edge
- [x] 5.2 全量回归：既有登录/登出/文本与文件上传/班级隔离/健康检查行为不变；verify: 4.3-4.6 全 PASS
- [x] 5.3 `openspec validate hide-api-class-switch-seed --type change --strict` 通过
