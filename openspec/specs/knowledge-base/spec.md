# knowledge-base Specification

## Purpose

为教师提供教学材料上传与管理能力，写入后立即可在本班的材料列表中查询到。系统需安全地存储材料元数据（所有者、班级归属、创建时间），并预留将来扩展为向量化知识库的空间。

## Requirements

### Requirement: 教师可以上传教学材料
系统 SHALL 提供材料上传端点，接受标题和正文内容，校验通过后持久化并返回新建记录的标识。

#### Scenario: 上传纯文本材料成功
- **WHEN** 已认证的 teacher 角色 POST 包含 title 和 content 的 JSON 请求体到上传端点
- **THEN** 系统返回 201 Created，响应体包含新材料的 id、title、class_id、owner_id、created_at 字段

#### Scenario: 上传时缺少 title 或 content 被拒绝
- **WHEN** 教师上传时请求体缺少 title 字段、缺少 content 字段、或两者皆缺
- **THEN** 系统返回 400 Bad Request，且不得在数据库中产生任何写入；响应体 SHALL 指明哪些字段是必填的

#### Scenario: 上传空字符串内容被拒绝
- **WHEN** 教师上传时 title="" 或 content=""（空字符串或仅空白）
- **THEN** 系统返回 400 Bad Request，不得写入任何数据

### Requirement: 上传后的材料立即在本班列表中可见
系统 SHALL 在写入成功后，使该材料对本班所有已认证用户（teacher 与 student）立即可查询到。列表响应 SHALL 对文件材料包含 `file_orig_name`、`file_size`、`file_mime` 字段（文本材料这些字段为 `null`），SHALL NOT 暴露内部磁盘名 `file_stored_name`。

#### Scenario: 上传后同班学生立刻查到
- **WHEN** 教师 A 上传一份材料并返回 201 Created；随后同班学生 B 立刻调用材料列表端点
- **THEN** 学生 B 的响应列表中 SHALL 包含刚刚上传的那条记录，且 id、title、owner_id 等字段与教师 A 上传时一致

#### Scenario: 上传后同班教师立刻查到
- **WHEN** 教师 A 上传一份材料并返回 201；随后教师 A 自己（或同班另一位教师）调用材料列表端点
- **THEN** 教师 A 自己的列表中 SHALL 包含刚刚上传的那条记录

#### Scenario: 列表区分文本与文件材料且不暴露内部磁盘名
- **WHEN** 本班同时存在文本材料和文件材料，teacher 查询列表
- **THEN** 文本材料 `content` 非空且 `file_orig_name` 为 `null`；所有记录 SHALL NOT 包含 `file_stored_name` 字段

#### Scenario: 上传后他班用户查不到（列表中无）
- **WHEN** A 班教师上传一份文件材料；随后 B 班任意用户调用材料列表端点
- **THEN** B 班用户的响应列表中 SHALL **不**包含那条记录；班级隔离行为不因新字段改变

#### Scenario: 上传后他班用户按 id 直接请求也被拒绝
- **WHEN** A 班教师上传材料后，把 material id 发给 B 班学生；B 班学生用这个 id 请求材料详情端点
- **THEN** 系统返回 404 Not Found（不泄露"该材料存在但不属于你"）

### Requirement: 每份材料记录保留所有者与班级归属
系统 SHALL 在每份材料记录中存储 owner_id（上传者用户 id）和 class_id（所属班级）。

#### Scenario: 查询材料详情包含所有者和班级字段
- **WHEN** 用户（teacher 或 student）查询本班某份材料的详情
- **THEN** 响应体中 SHALL 包含 owner_id 字段和 class_id 字段；owner_id 的值等于上传者的用户 id

#### Scenario: 列表响应包含所有者和班级字段
- **WHEN** 用户调用材料列表端点
- **THEN** 列表中每一项 SHALL 包含 id、title、owner_id、class_id、created_at 字段

### Requirement: 材料数据结构预留知识库扩展
材料记录 SHALL 支持两种形式：文本材料（`content` 存用户粘贴的正文）或文件材料（关联 `file_orig_name` 原始文件名、`file_stored_name` 磁盘存储名、`file_size` 字节数、`file_mime` MIME 类型四个文件列，`content` 存上传时自动提取的文本正文，提取失败为空）。`content` 约束 SHALL 放宽为可空。迁移 SHALL 无损——对已有数据行新增列取空默认值，现有文本材料与种子数据不受影响，且不影响将来向量化或全文检索扩展（文件材料的提取文本可直接作为 embedding 输入）。

#### Scenario: 已有数据库无损迁移
- **WHEN** 携带旧 schema（已有 2 条种子文本材料）的数据库启动新版本应用
- **THEN** `materials` 表出现 4 个文件新列，旧记录新列均为空值，文本材料仍可正常查询，无需迁移或重建数据

#### Scenario: 全新数据库直接含新列
- **WHEN** 全新部署（空 volume）首次启动
- **THEN** 建表语句直接包含全部文件列与可空 `content`，种子脚本写入 2 条文本材料

#### Scenario: 后续可无损接入向量化管道
- **WHEN** 未来需要将所有材料内容生成 embedding 并存入向量数据库
- **THEN** 文本材料的 content 包含用户粘贴的完整文本，文件材料的 content 包含提取文本，二者均可直接作为 embedding 输入；现有数据无需迁移或破坏

#### Scenario: 预置数据脚本可在未来替换为正式用户管理流程
- **WHEN** 将来引入正式的用户注册和班级管理功能
- **THEN** 当前基于种子脚本的预置用户和班级数据可被替换或扩展，不影响已上传材料（含文件材料）；材料的 class_id / owner_id 外键关系保持自洽

### Requirement: 容器化启动后材料功能立即可用
系统 SHALL 支持通过容器化方式启动，启动完成后所有材料上传、列表、详情端点立即可供调用，无需额外手动初始化数据库。

#### Scenario: 一键启动后预置账号可上传
- **WHEN** 执行容器化启动命令后等待应用就绪
- **THEN** 预置的教师账号能够登录并成功上传材料；随后同班学生能够查到那条记录
