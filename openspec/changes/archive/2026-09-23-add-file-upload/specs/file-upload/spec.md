# file-upload 文件上传与下载

## ADDED Requirements

### Requirement: 教师可以上传文件到本班知识库

系统 SHALL 提供 `POST /api/materials/file`（multipart/form-data，字段 `file` + `title`），仅 `teacher` 角色可调用，成功后返回 `201` 并创建一条文件类型材料记录。`class_id` 与 `owner_id` SHALL 由服务端从会话推导，不信任客户端字段。

#### Scenario: 教师上传 pdf 成功

- **WHEN** 已登录 teacher 提交 multipart 请求，`title="高等数学讲义"`，`file` 为有效的 2MB pdf 文件
- **THEN** 响应 `201`，JSON 含 `id`、`title`、`class_id="class-001"`、`file_orig_name`、`file_size=2097152`、`file_mime`，且不含 `file_stored_name`
- **AND** 磁盘 `data/uploads/` 出现一个以 uuid 命名的文件，数据库记录 `file_stored_name` 与之对应

#### Scenario: 学生上传文件被拒绝

- **WHEN** 已登录 student 提交同样的 multipart 请求
- **THEN** 响应 `403`，磁盘与数据库零写入

#### Scenario: 未登录上传被拒绝

- **WHEN** 未携带会话 Cookie 提交 multipart 请求
- **THEN** 响应 `401`

#### Scenario: 标题缺失被拒绝

- **WHEN** teacher 上传合法文件但 `title` 为空或缺失
- **THEN** 响应 `400`

### Requirement: 文件类型白名单

系统 SHALL 仅接受扩展名为 `txt`、`md`、`pdf`（大小写不敏感）的文件，并且 SHALL 通过内容校验确认类型：pdf 必须以 `%PDF-` 开头，txt/md 必须能以 UTF-8 解码。扩展名与内容校验任一不通过 SHALL 返回 `415`，不落盘、不写库。

#### Scenario: 白名单扩展名成功

- **WHEN** 上传 `notes.TXT`（大写扩展名）且内容为 UTF-8 文本
- **THEN** 响应 `201`

#### Scenario: 非白名单扩展名被拒

- **WHEN** 上传 `恶意.exe` 或 `photo.jpg`
- **THEN** 响应 `415`，`data/uploads/` 无新文件

#### Scenario: 扩展名伪装被拒

- **WHEN** 上传名为 `fake.pdf` 但内容以 `MZ` 开头（Windows 可执行文件）
- **THEN** 响应 `415`

#### Scenario: 损坏的文本文件被拒

- **WHEN** 上传名为 `broken.md` 但内容含非法 UTF-8 字节序列
- **THEN** 响应 `415`

### Requirement: 文件大小限制

系统 SHALL 拒绝超过 10 MB 的上传请求并返回 `413`。配置 SHALL 通过 Flask `MAX_CONTENT_LENGTH` 在框架层生效，应用层对文件字节数做二次校验。

#### Scenario: 超限文件被拒

- **WHEN** teacher 上传 11 MB 的合法 pdf
- **THEN** 响应 `413`，磁盘与数据库零写入

#### Scenario: 恰好限额内成功

- **WHEN** teacher 上传 10 MB 以内的合法 pdf
- **THEN** 响应 `201`

### Requirement: 安全的磁盘存储命名

系统 SHALL 以 `uuid4().hex + 白名单扩展名` 作为磁盘文件名，原始文件名 SHALL 只存储在数据库中，绝不用于构造磁盘路径。下载 SHALL 以磁盘存储名为路径、原始名为 `download_name` 提供给客户端。

#### Scenario: 两个同名文件互不覆盖

- **WHEN** teacher 先后上传两个同名文件 `讲义.pdf`
- **THEN** 两次均 `201`，磁盘产生两个不同 uuid 文件名，数据库两条记录 `file_orig_name` 均为 `讲义.pdf`

#### Scenario: 恶意文件名不产生路径穿越

- **WHEN** teacher 上传名为 `../../etc/passwd.txt` 的文件
- **THEN** 响应 `201`，磁盘文件名不含任何路径分隔符，原文件按 uuid 存放在 `data/uploads/` 内

#### Scenario: 重启后文件仍可下载

- **WHEN** 上传成功后 `docker compose down && docker compose up -d`
- **THEN** 该材料的下载端点仍返回文件内容（存储位于持久化 volume）

### Requirement: 下载受会话与班级隔离保护

系统 SHALL 提供 `GET /api/materials/<id>/download`，未登录返回 `401`；登录用户只能下载本班材料，跨班或不存在的材料统一返回 `404`（不泄露存在性）。响应 `Content-Disposition` SHALL 使用数据库中的原始文件名。

#### Scenario: 本班学生可下载

- **WHEN** student1 请求本班文件材料的下载端点
- **THEN** 响应 `200`，body 为文件内容，`Content-Disposition` 含原始文件名

#### Scenario: 跨班下载被拒

- **WHEN** class-002 用户请求 class-001 材料的下载端点
- **THEN** 响应 `404`

#### Scenario: 未登录下载被拒

- **WHEN** 无会话请求下载端点
- **THEN** 响应 `401`

#### Scenario: 纯文本材料无下载

- **WHEN** 对 `file_stored_name` 为空的文本材料请求下载
- **THEN** 响应 `404`

### Requirement: 上传时自动提取文本内容

系统 SHALL 在文件材料上传成功落库前自动提取文本正文并写入 `content`：txt/md 的 UTF-8 解码文本即正文；pdf 使用 pypdf 逐页提取文本层后拼接。提取失败（损坏文件、扫描件无文本层、编码异常）SHALL NOT 阻塞上传——材料照常创建（`201`），`content` 置空。

#### Scenario: txt/md 正文即内容

- **WHEN** teacher 上传 `notes.md`，内容为 `# 标题\n正文段落`
- **THEN** 响应 `201`，且该材料详情的 `content` 等于原文本

#### Scenario: pdf 提取文本层

- **WHEN** teacher 上传含文本层的 `讲义.pdf`（内含"函数的极限"字样）
- **THEN** 响应 `201`，该材料详情的 `content` 包含"函数的极限"

#### Scenario: 扫描件无文本层不阻塞上传

- **WHEN** teacher 上传无文本层的图片型 pdf
- **THEN** 响应仍为 `201`（不做 OCR），该材料 `content` 为空，文件本身正常存储可下载

#### Scenario: 损坏 pdf 降级

- **WHEN** teacher 上传魔数正确但结构损坏的 pdf（`%PDF-` 开头但内容截断）
- **THEN** 响应 `201`，`content` 为空，文件照常存储

### Requirement: 材料详情端点支持预览

系统 SHALL 提供 `GET /api/materials/<id>`，返回单条材料的完整记录（含 `content` 正文、文件元数据，不含 `file_stored_name`）。未登录返回 `401`；本班用户返回 `200`；跨班或不存在返回 `404`。

#### Scenario: 本班学生预览文件材料正文

- **WHEN** student1 请求本班 pdf 材料的详情端点
- **THEN** 响应 `200`，JSON 含 `content`（提取文本）、`file_orig_name`、`file_size`

#### Scenario: 跨班详情被拒

- **WHEN** class-002 用户请求 class-001 材料的详情端点
- **THEN** 响应 `404`

#### Scenario: 未登录详情被拒

- **WHEN** 无会话请求详情端点
- **THEN** 响应 `401`
