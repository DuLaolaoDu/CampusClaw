# 文件上传功能

## Why

当前教师"上传材料"只能把文本粘贴进 `content` 字段（JSON body），无法上传真实文件。实际教学材料多为 txt / md / pdf 文件，粘贴会丢失格式与排版（pdf 根本无法粘贴）。需要支持真正的文件上传，同时不能破坏已有的三条安全基线：仅教师可传、班级隔离、密码/会话机制不变。

## What Changes

- 新增 `POST /api/materials/file`（multipart/form-data）：教师上传文件（`file` + `title` 字段），写入文件系统与数据库
- 新增 `GET /api/materials/<id>/download`：本班用户可下载本班文件材料
- **文件类型白名单**：仅允许 `txt`、`md`、`pdf` 三种扩展名，并做魔数校验（pdf 校验 `%PDF-` 头，txt/md 校验 UTF-8 可解码）；白名单外一律 415
- **大小限制**：单文件 ≤ 10 MB（Flask `MAX_CONTENT_LENGTH` + 应用层二次校验），超限 413
- **安全存储**：磁盘文件名改为 `uuid4().hex + 白名单扩展`（防路径穿越、防同名覆盖、防原文件名注入），原始文件名仅存数据库；存储目录 `data/uploads/`（位于已有的 `campusclaw-data` volume，容器重启持久，无需改 compose）
- **数据模型无损迁移**：`materials` 表新增 4 列（`file_orig_name` / `file_stored_name` / `file_size` / `file_mime`），`content` 放宽为可空（文件材料的正文为提取文本，解析失败为空；旧库 NOT NULL 残留以空串约定绕过）；用 `PRAGMA table_info` 检测 + `ALTER TABLE ADD COLUMN`，已有数据（种子 2 条）不受影响
- **下载端点同样强制班级隔离**：先按 `class_id` 查记录（复用 `get_for_user` 模式），跨班/不存在统一 404，再 `send_file`
- 前端 dashboard 上传区新增文件选择控件（teacher 可见），列表中文件材料显示文件名/大小并带下载链接（student 也可下载）
- **上传时自动内容解析**：txt/md 的 UTF-8 文本即正文；pdf 用 `pypdf` 提取文本层写入 `content`——解析成功后文件材料的正文可被检索/预览；解析失败（如扫描件无文本层）不阻塞上传，`content` 留空
- **材料详情/预览端点**：`GET /api/materials/<id>` 返回单条记录含 `content`（本班隔离，跨班 404），前端点击材料展开预览提取文本

## Capabilities

### New Capabilities

- `file-upload`：文件上传与下载——类型白名单、大小限制、安全存储命名、下载鉴权与班级隔离、上传时内容提取、材料详情/预览

### Modified Capabilities

- `knowledge-base`：材料记录可关联文件（新字段出现在列表/详情响应中）；文本材料与文件材料均可携带 `content` 正文（文件材料的正文来自自动解析）

## Non-Goals

- 不做 pdf **版式渲染**预览（不引入 pdf.js，预览展示提取出的纯文本）
- 不做**向量化 / embedding / RAG 检索**——体量大（embedding 选型、向量存储、检索端点），另立独立变更
- 不支持白名单外格式：docx / pptx / xlsx / 图片 / 音视频 / 压缩包
- 不做 OCR（扫描件无文本层时 content 留空，不做图像文字识别）
- 不做文件编辑、删除、版本管理、替换
- 不做断点续传、分片上传、秒传
- 不做对象存储（S3/OSS）——本地 volume 存储
- 不做病毒扫描 / 沙箱检测
- 不做学生上传（沿用现有 RBAC：仅 teacher）
- 不做配额管理（每班/每人空间限额）

## Impact

**Affected specs:** `knowledge-base`（MODIFIED：材料字段扩展 + content 语义）、新增 `file-upload`

**Affected code:**

- `app/db.py`：`SCHEMA_SQL` 更新 + 新增 `migrate_schema(conn)` 轻量迁移函数（PRAGMA 检测列缺失 → ALTER TABLE）
- `app/materials.py`：新增 `upload_material_file` / `download_material` / `get_material_detail` 端点；`MaterialsRepo` 新增 `create_file_for_user`、`get_for_user`；列表/详情 SELECT 增加新列
- `app/extract.py`（新增）：文本提取模块——txt/md UTF-8 解码、pdf `pypdf` 逐页提取、失败降级返回空串
- `app/config.py`：新增 `UPLOAD_DIR`、`MAX_FILE_SIZE`（10 MB）、`ALLOWED_EXTENSIONS` 配置
- `app/templates/dashboard.html`：上传区加 `<input type="file">`、列表渲染文件元数据 + 下载链接 + 点击展开预览正文
- `requirements.txt`：新增 `pypdf`（纯 Python，slim 镜像无系统依赖）
- `Dockerfile` / `docker-compose.yml`：**无需改动**（volume 已挂载 `/app/data`，uploads 建在其下；pip install -r 自动带上 pypdf）
- `README.md`：补充文件上传/下载/预览 API 说明
- 依赖：仅新增 `pypdf`（魔数校验仍用标准库实现，不引入 python-magic）
