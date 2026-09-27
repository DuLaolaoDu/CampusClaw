# Proposal: hide-api-class-switch-seed

## Why

用户（浏览器端）目前可以直接访问 Flask 的 8000 端口并调用全部 /api 端点，前端页面也完全依赖浏览器 fetch /api，API 与页面无边界；同时教师固定属于 class-001，没有任何切换班级的入口；种子数据全部集中在 class-001，班级隔离根本无法演示验证。

## What Changes

- **BREAKING** 浏览器前端不再调用任何 `/api/*` 端点：登录/登出/上传/列表/预览全部改为 Jinja2 服务端渲染 + 表单 POST + 重定向（`web-ui`）
- **BREAKING** Flask 容器不再向宿主机发布端口；新增 nginx 边缘服务作为唯一用户入口，仅放行页面路由与用户侧下载路由，外部请求 `/api/*` 一律 404（`edge-proxy`）
- 新增 `teacher_classes` 任教关系表；教师只能切换到自己任教的班级，生效班级存服务端 session，学生永远锁定本班（`rbac` / `class-isolation`）
- 班级隔离的"当前班级"语义升级为"生效班级"：教师 = 当前选中的任教班级，学生 = 自身 class_id；服务端查询/写入仍强制使用生效班级（`class-isolation`）
- 种子数据扩展到两个班级（teacher 兼任 class-002、新增 teacher2/student3 与 class-002 样本材料），对已初始化的旧 volume 做幂等补种，不覆盖现有数据（`user-auth` / `knowledge-base`）
- 材料下载增加用户侧页面路由（如 `GET /materials/<id>/download`），API 下载路由保留为内部端点（`knowledge-base`）

## Capabilities

### New Capabilities

- `web-ui`: 服务端渲染的页面与表单交互——登录页、仪表盘（材料列表/上传表单/预览/下载链接）、教师班级切换控件；浏览器零 fetch /api 依赖
- `edge-proxy`: nginx 边缘代理——唯一对外入口；页面与用户侧下载可达，`/api/*` 外部不可达（404），健康检查走容器内部直连

### Modified Capabilities

- `class-isolation`: "当前用户 class_id"升级为"生效班级"（教师可切换任教班级、学生固定本班），服务端 WHERE/写入强制语义不变
- `rbac`: 新增班级切换端点的角色约束（仅 teacher，且仅限任教班级；student 403）
- `user-auth`: 种子数据覆盖两个班级 + 对已初始化数据库的幂等补种；登录/登出保留 API 端点的同时增加页面表单路由
- `knowledge-base`: 用户上传/下载入口改为页面路由（API 保留为内部端点）；"立即可见/班级归属/扩展预留"语义不变

## Impact

- docker-compose 从单服务变双服务（app + nginx），对外端口语义变化（**BREAKING**：直连 8000 的 Flask API 不再可达）
- 前端模板与 JS 重写为服务端渲染（**BREAKING**：现有 fetch 驱动的 dashboard.html 逻辑废弃）
- 旧 volume 无损：teacher_classes 建表 + 种子补种均幂等，既有用户/材料数据不动
- 建立在已实施但未归档的 add-file-upload 变更之上（文件上传/下载/解析功能保留）
