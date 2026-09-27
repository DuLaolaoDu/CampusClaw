# CampusClaw
一个 Flask + SQLite 的校园知识库：页面登录、教师上传教学材料、按班级隔离数据；用户只能通过网页使用，后端 API 不对外暴露。
快速启动：cp .env.example .env && docker compose up -d，然后浏览器打开 http://localhost:8000

---

## 使用入口（网页）

用户唯一入口是页面（nginx 反向代理，端口 8000）：登录 → 仪表盘（材料列表 / 上传 / 预览 / 下载）→ 教师可切换任教班级 → 登出。浏览器端不调用任何 /api；直接访问 `http://localhost:8000/api/*` 一律返回 404。

## 预置账号

| username   | 初始密码      | role    | class_id  | 任教班级              |
|------------|---------------|---------|-----------|-----------------------|
| teacher    | teacher123    | teacher | class-001 | class-001 + class-002 |
| student1   | student123    | student | class-001 | -                     |
| student2   | student123    | student | class-001 | -                     |
| teacher2   | teacher123    | teacher | class-002 | class-002             |
| student3   | student123    | student | class-002 | -                     |

首次启动自动建表并写入预置数据（5 账号 + 任教关系 + 每班 2 条样本材料）；对已有旧数据库只做幂等补种，不改动任何既有数据。teacher 兼任两个班级，登录后可在仪表盘右上角切换生效班级，用于验证班级隔离。

## 内部 API（仅容器网络内可用）

以下端点仅限容器网络内部调用（外部已被边缘代理屏蔽为 404），供程序化集成与运维验证：

| 方法 | 路径                        | 认证 | 角色    | 说明                            |
|------|-----------------------------|------|---------|---------------------------------|
| POST | /api/auth/login             | 否   | -       | 登录，设 Flask session          |
| POST | /api/auth/logout            | 是   | -       | 清 session                      |
| GET  | /api/health                 | 否   | -       | 健康检查（容器健康检查使用）    |
| POST | /api/materials              | 是   | teacher | 上传纯文本材料（JSON）          |
| POST | /api/materials/file         | 是   | teacher | 上传文件材料（multipart，txt/md/pdf ≤10MB） |
| GET  | /api/materials              | 是   | 所有    | 本班材料列表（生效班级过滤）    |
| GET  | /api/materials/id           | 是   | 所有    | 本班材料详情（含提取正文）      |
| GET  | /api/materials/id/download  | 是   | 所有    | 下载文件材料（跨班/纯文本 404） |

容器内验证示例：

```bash
docker compose exec app python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/api/health').read())"
```

## 文件上传 / 下载

- 页面入口：仪表盘「上传新材料」表单（标题 + 可选附件 + 可选正文，服务端渲染）
- 支持类型：`.txt` / `.md` / `.pdf`，不超过 10MB（框架层与应用层双重限制）
- 双重校验：扩展名白名单 + 魔数（pdf 头 `%PDF-`、文本 UTF-8 解码），不通过返回 415
- pdf 上传时自动提取文本层存入 `content`（pypdf）；扫描件等无文本层不阻塞上传，`content` 为空
- 磁盘存储名为随机 UUID（防路径穿越/同名覆盖），原文件名仅存数据库，不出现在页面/API 中
- 文件与 SQLite 同在 `campusclaw-data` volume（`/app/data/uploads`），重启不丢
- 下载入口：材料条目上的「下载」链接（用户侧路由 `/materials/<id>/download`，生效班级过滤）

## 技术栈

- 后端：Flask 3.x（Python 3.12，服务端渲染 Jinja2）
- 数据库：SQLite 3（raw sqlite3 标准库）
- 密码哈希：bcrypt
- 会话：Flask 内置 session（itsdangerous 签名 Cookie）
- 部署：Docker Compose 双服务（app + nginx 边缘代理）+ SQLite volume 持久化
