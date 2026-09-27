# Tasks: add-file-upload

## 1. 配置与存储层

- [x] 1.1 `app/config.py` 新增 `UPLOAD_DIR`（默认与 DATABASE_PATH 同目录下 `uploads/`）、`MAX_FILE_SIZE = 10 * 1024 * 1024`、`ALLOWED_EXTENSIONS = {"txt", "md", "pdf"}`；verify: `python -c "from app.config import Config; print(Config.UPLOAD_DIR, Config.MAX_FILE_SIZE)"`
- [x] 1.2 `app/db.py`：`SCHEMA_SQL` 中 `materials` 的 `content` 去掉 `NOT NULL`，补 4 个文件列（`file_orig_name TEXT` / `file_stored_name TEXT` / `file_size INTEGER` / `file_mime TEXT`）；新增 `migrate_schema(conn)`（design D5 的 PRAGMA + ALTER 实现）；`init_schema` 后调用；启动时 `os.makedirs(UPLOAD_DIR, exist_ok=True)`；verify: 用旧库文件副本启动，`python -c` 执行 `PRAGMA table_info(materials)` 确认 4 新列存在且旧行完好
- [x] 1.3 迁移无损验证：对已含 2 条种子材料的 volume 数据库执行迁移，确认旧记录 `content` 原样、新列为空；verify: `python -c` 查询 `SELECT id, title, file_orig_name FROM materials` 输出 2 行且 file_orig_name 为 None
- [x] 1.4 `requirements.txt` 加 `pypdf>=4.0` 并本地安装；verify: `python -c "import pypdf; print(pypdf.__version__)"`

## 2. 类型、大小校验与内容提取

- [x] 2.1 `app/materials.py` 新增 `_validate_file(file)`：扩展名白名单（小写比对）→ 415；pdf 读前 5 字节比对 `%PDF-`、txt/md 全量 UTF-8 解码 → 失败 415；`file.seek` 取字节数 > 10MB → 413；verify: pytest 或脚本分别构造合法 pdf（`b"%PDF-1.4 ..."`）、伪装 pdf（`b"MZ..."`）、非法 UTF-8 bytes、超限 bytes，断言返回码 415/413
- [x] 2.2 `Config.MAX_CONTENT_LENGTH` 生效确认：超过 10MB 的 multipart 请求被 Flask 拒绝为 413；verify: curl 上传 11MB 文件（`fsutil file createnew` / python 生成）断言 413
- [x] 2.3 新增 `app/extract.py` 的 `extract_text(filename, data)`（design D8 代码）：txt/md UTF-8 文本即正文；pdf 用 pypdf 逐页提取拼接；一切异常捕获返回 `""`；verify: 脚本断言——txt 输入返回原文、用 pypdf 生成的简单 pdf 返回含预期文字、`b"%PDF-1.4 truncated"` 损坏串返回 `""` 且不抛异常

## 3. 上传与下载端点

- [x] 3.1 `app/materials.py` 新增 `POST /api/materials/file`：装饰器链 `@login_required @role_required("teacher")`；`title` 非空校验 400；校验通过后调用 `extract_text` 得正文，磁盘名 `uuid4().hex + suffix` 写入 `UPLOAD_DIR`，`MaterialsRepo.create_file_for_user` 落库（class_id/owner_id 取会话用户，content 为提取文本或 `""`）；返回 201 + 规范化 JSON（不含 file_stored_name）；verify: teacher 会话 curl -F 上传合法 pdf → 201，详情 content 含 pdf 文字
- [x] 3.2 新增 `MaterialsRepo.create_file_for_user` 与 `get_for_user`（`WHERE id=? AND class_id=?`，None 表示不可见）；现有文本创建路径改用同一规范化输出；verify: 单元断言 get_for_user 跨 class_id 返回 None
- [x] 3.3 新增 `GET /api/materials/<id>/download`：`@login_required` → `get_for_user` → None 或非文件材料 404 → `send_file(path, download_name=file_orig_name)`；verify: 本班下载 200 且 Content-Disposition 含原文件名；跨班/未登录/文本材料分别 404/401/404
- [x] 3.4 新增 `GET /api/materials/<id>` 详情端点：`@login_required` → `get_for_user` → 404/200，输出含 `content` 与文件元数据、不含 `file_stored_name`；verify: 本班 200 含提取正文；跨班 404；未登录 401
- [x] 3.5 RBAC 与隔离回归：student 上传文件 403（磁盘零写入 `ls data/uploads | wc -l` 前后一致）；未登录 multipart 401；客户端伪造 `class_id` 表单字段被服务端覆盖；verify: curl 三连断言
- [x] 3.6 同名与恶意文件名：两次上传同名 `讲义.pdf` 产生两个不同 uuid 磁盘文件；上传名 `../../evil.txt` 磁盘名不含路径分隔符且 201；verify: `ls data/uploads` 检查

## 4. 列表响应规范化

- [x] 4.1 `GET /api/materials` 输出新字段：文件材料含 `file_orig_name/file_size/file_mime`、`content` 为提取文本或 null；文本材料三者均 null、`content` 正常；所有记录不含 `file_stored_name`；verify: teacher 列表 JSON 逐字段断言

## 5. 前端集成（dashboard.html）

- [x] 5.1 上传区加 `<input type="file" accept=".txt,.md,.pdf">`（teacher 可见）；提交逻辑：有文件走 FormData 到 `/api/materials/file`，无文件保持 JSON 老端点；415/413/400 显示服务端 error 文案；verify: 浏览器上传 pdf → 列表即时出现新记录
- [x] 5.2 列表渲染文件材料：`📄 原文件名 (大小格式化)` + 下载链接；点击材料行展开 `<pre>` 预览 `content` 提取正文（数据已在列表响应中，零额外请求）；student 登录可见下载/预览、无上传区；verify: student1 登录点击下载成功、展开预览显示文本且无上传控件

## 6. 端到端验证（容器内）

- [x] 6.1 重建镜像并 `docker compose up -d`，等 healthy；verify: `docker compose ps` STATUS 含 (healthy)
- [x] 6.2 旧 volume 无损迁移：up 后旧 2 条文本材料仍可查；verify: teacher 列表 ≥2 条旧记录
- [x] 6.3 全链路 curl：teacher 上传 2MB pdf → 201 → 详情 content 含提取文字 → 列表含记录 → student 下载 200 + 预览正文 → student 上传 403 → 超限 413 → 伪装 pdf 415；verify: 七条 curl 断言全部通过
- [x] 6.4 持久化：`docker compose down && up -d` 后刚上传的文件仍可下载；verify: 重复下载 200 且字节数一致

## 7. 文档与收尾

- [x] 7.1 README 补文件上传/下载 API 说明与 curl 示例；verify: `Select-String -Path README.md -Pattern "materials/file"` 有匹配
- [x] 7.2 全量回归：登录/登出/文本上传/班级隔离既有行为不变；verify: 既有 17 项 E2E 检查全 PASS
- [x] 7.3 `openspec validate add-file-upload --type change --strict` 通过
