# 文件上传功能设计

## Context

现有系统（已归档变更 auth-class-kb-upload）：Flask 3.x + SQLite + 会话认证（`APP_SECRET` 签名 Cookie）+ bcrypt，材料以纯文本（`title` + `content` JSON）入库，班级隔离在 Repository 层强制。Docker Compose 单服务，`campusclaw-data` volume 挂载在 `/app/data`（SQLite 文件所在地）。

本变更为其增加真实文件上传。约束：零新依赖、复用现有 volume、不破坏已持久化的数据库（volume 里已有种子数据）。

## Goals / Non-Goals

- Goals：教师可上传 txt/md/pdf 文件（≤10MB）入本班知识库；本班用户可下载；白名单+魔数双校验；uuid 安全命名；schema 无损迁移
- Non-Goals：内容解析/预览/向量化、白名单外格式、S3、病毒扫描、配额（详见 proposal）

## Decisions

### D1. 端点与请求形式：multipart/form-data，独立于现有 JSON 端点

- `POST /api/materials/file`（新）：`file`（FileStorage）+ `title`（表单字段）。不复用 `POST /api/materials`（保持其 JSON 语义不变，避免兼容性破坏）
- `GET /api/materials/<id>/download`（新）
- 复用现有装饰器链 `@login_required` + `@role_required("teacher")`（上传）；下载仅 `@login_required`

### D2. 类型校验：扩展名白名单 + 魔数，零依赖实现

```
1. 扩展名：Path(file.filename).suffix.lower() in {"txt","md","pdf"}  → 否则 415
2. 读取前 5 字节：
   - pdf  → 必须 == b"%PDF-"
   - txt/md → 整个文件 bytes.decode("utf-8") 成功（文本可能数 MB，一次性解码可接受）
3. 任一失败 → 415，不写盘不写库
```

不引入 python-magic（需要 libmagic 系统库，slim 镜像与 Windows 本地开发都要额外装）。白名单三种类型的判定用标准库足够可靠。

### D3. 大小限制：Flask 框架层 + 应用层双保险

- `Config.MAX_CONTENT_LENGTH = 10 * 1024 * 1024`（Flask 对超限请求自动 413）
- 应用层 `file.seek(0, 2); size = file.tell()` 二次校验（防未来 MAX_CONTENT_LENGTH 被调大后应用层失控），> 10MB → 413
- 错误响应统一 `{"error": "..."}`（与其他端点风格一致）

### D4. 磁盘命名与存储位置：uuid 命名，volume 内 uploads 目录

- `UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(os.path.dirname(DATABASE_PATH) or ".", "uploads"))`——默认与数据库同目录（`/app/data/uploads`），天然落在已有 volume，**compose/Dockerfile 零改动**
- 磁盘名 `uuid4().hex + suffix`：无路径穿越面（不含用户输入）、天然防同名覆盖、防原文件名特殊字符
- 原始文件名仅存 DB `file_orig_name`，下载时作 `download_name`（`send_file` 会按 RFC 处理引号/非 ASCII）
- 启动时 `os.makedirs(UPLOAD_DIR, exist_ok=True)`

### D5. Schema 迁移：PRAGMA 检测 + ALTER TABLE，幂等无损

已有数据库（volume 持久化）不能用 `CREATE TABLE IF NOT EXISTS` 升级。新增 `migrate_schema(conn)`，在 `init_schema` 之后执行：

```python
def migrate_schema(conn):
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(materials)")}
    stmts = [
        ("file_orig_name",  "ALTER TABLE materials ADD COLUMN file_orig_name TEXT"),
        ("file_stored_name","ALTER TABLE materials ADD COLUMN file_stored_name TEXT"),
        ("file_size",       "ALTER TABLE materials ADD COLUMN file_size INTEGER"),
        ("file_mime",       "ALTER TABLE materials ADD COLUMN file_mime TEXT"),
    ]
    for col, sql in stmts:
        if col not in cols:
            conn.execute(sql)
    conn.commit()
```

- 幂等：列已存在则跳过；新库由新 `SCHEMA_SQL` 直接建全列，migrate 自然跳过
- `content` 可空：SQLite `ALTER TABLE` 不能改约束——新库的 `SCHEMA_SQL` 中 `content` 直接去掉 `NOT NULL`；**旧库 content 仍带 NOT NULL**，写文件材料时 `content` 插入空字符串 `""` 而非 NULL（读写层统一约定：文件材料 content 为提取文本或 `""`，查询响应中空串映射为 `null`）。这样旧库无需重建表
- 查询响应统一规范化：`content = row["content"] or None`，新列 `row["file_stored_name"]` 不输出

### D6. Repository 扩展：隔离逻辑复用

`MaterialsRepo` 新增/调整：

```python
@staticmethod
def create_file_for_user(conn, user, title, orig_name, stored_name, size, mime):
    # INSERT，class_id/owner_id 一律取自 user 参数（与文本路径同源，不可绕过）

@staticmethod
def get_for_user(conn, user, material_id):
    # SELECT ... WHERE id=? AND class_id=?  → 下载与单条查询共用，查不到返回 None（端点转 404）
```

下载端点流程：`get_for_user` → None 则 404 → 有 `file_stored_name` 才 send_file，否则 404 → `send_file(path, download_name=orig_name)`。

### D7. 前端最小集成（dashboard.html）

- 上传区（teacher 可见）加 `<input type="file" accept=".txt,.md,.pdf">`；提交改用 `FormData`（有文件时）或原 JSON（无文件时纯文本仍走老端点）
- 列表渲染：文件材料显示 `📄 {file_orig_name} ({size 格式化})` + 下载链接 `<a href="/api/materials/{id}/download">`；文本材料渲染不变
- 错误提示沿用现有红色提示条（415/413/403 均显示服务端 error 文案）

### D8. 内容解析：上传时同步提取，失败降级不阻塞

新增 `app/extract.py`：

```python
def extract_text(filename: str, data: bytes) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext in ("txt", "md"):
        return data.decode("utf-8", errors="ignore")
    if ext == "pdf":
        try:
            import io
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception:
            return ""   # 损坏 pdf / 无文本层 → 空正文，不阻塞上传
    return ""
```

- 依赖选 `pypdf`：纯 Python、零系统依赖（slim 镜像与 Windows 本地开发都免装库），与零依赖原则冲突最小
- 提取失败（损坏结构、扫描件无文本层）捕获一切异常返回 `""`——上传仍 201，正文留空，spec 场景「扫描件无文本层不阻塞上传」由此满足
- `errors="ignore"` 兜底 UTF-8 边界（正常路径已在类型校验时全量解码过一次，此处为防御式）
- 提取结果在落库前写入 `content`，与文件元数据同一条 INSERT，保证原子性
- 提取上限：文件 ≤10MB，pdf 文本量通常远小于原文件，无需额外截断（未来接入向量化时再考虑分块）

### D9. 预览：详情端点 + 前端展开，不做 pdf 版式渲染

- 新增 `GET /api/materials/<id>`：`@login_required` → `get_for_user` → 404/200，输出与列表一致的规范化字段但**含 `content`**（列表为省流量已含 content，实现上直接复用同一规范化函数即可）
- 前端点击列表行 → 展开 `<pre>` 显示 `content`（数据已在列表响应中，点击零额外请求；详情端点供 API 消费者与未来前端使用，并补齐主 spec 已引用的"材料详情端点"场景）
- **不做** pdf.js 版式渲染预览（Non-Goal）：预览即提取文本的纯文本展示；学生与教师同等可预览（读权限）

## Risks / Trade-offs

- **大文本解码占内存**：txt/md 全量 UTF-8 解码，10MB 上限下峰值 ~10-20MB 内存，单用户低并发场景可接受 → 若未来开放并发上传，改为流式分块校验
- **魔数校验非安全边界**：pdf 头部检查不能保证文件无害（恶意 pdf 照样能存）——本系统下载时按原扩展名提供，浏览器执行风险由用户端防护；病毒扫描属 Non-Goal
- **旧库 content NOT NULL 约束残留**：以 `""` 约定绕过，读写层已封装，但直接查库会看到空串而非 NULL → design 已记录约定，可接受
- **无并发去重**：同一文件重复上传产生多份存储 → 符合"不做秒传/配额"的 Non-Goal
- **pdf 提取质量不可控**：pypdf 对复杂排版/双栏/表格的提取结果可能乱序或夹杂噪声；扫描件完全无文本层（content 空）→ 本变更接受"能提取多少存多少"，质量优化与 OCR 属 Non-Goal，向量化变更若依赖提取质量再评估
- **pypdf 新依赖**：纯 Python、无系统库，风险低；锁最低版本 `pypdf>=4.0` 保证 API 稳定

## Migration Plan

1. 部署新版本 → 启动时 `init_schema` + `migrate_schema` 自动完成列扩展
2. 已有 volume 数据无损（种子 2 条文本材料新列为空）
3. 回滚安全：新列多余但无害，旧代码不读它们；已上传的磁盘文件留在 uploads 目录不影响运行

## Open Questions

- 无。
