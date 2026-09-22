## Purpose

为教师提供教学材料上传与管理能力，写入后立即可在本班的材料列表中查询到。系统需安全地存储材料元数据（所有者、班级归属、创建时间），并预留将来扩展为向量化知识库的空间。

## ADDED Requirements

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
系统 SHALL 在写入成功后，使该材料对本班所有已认证用户（teacher 与 student）立即可查询到。

#### Scenario: 上传后同班学生立刻查到
- **WHEN** 教师 A 上传一份材料并返回 201 Created；随后同班学生 B 立刻调用材料列表端点
- **THEN** 学生 B 的响应列表中 SHALL 包含刚刚上传的那条记录，且 id、title、owner_id 等字段与教师 A 上传时一致

#### Scenario: 上传后同班教师立刻查到
- **WHEN** 教师 A 上传一份材料并返回 201；随后教师 A 自己（或同班另一位教师）调用材料列表端点
- **THEN** 教师 A 自己的列表中 SHALL 包含刚刚上传的那条记录

#### Scenario: 上传后他班用户查不到（列表中无）
- **WHEN** A 班教师上传一份材料；随后 B 班任意用户调用材料列表端点
- **THEN** B 班用户的响应列表中 SHALL **不**包含那条记录；B 班用户的列表仅展示 B 班自己的材料

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
材料记录 SHALL 以文本形式存储 content，并可通过简单扩展支持将来向量化或全文检索，无需迁移现有数据。

#### Scenario: 后续可无损接入向量化管道
- **WHEN** 未来需要将所有材料内容生成 embedding 并存入向量数据库
- **THEN** 当前的 content 字段包含完整文本，可直接作为 embedding 输入；现有数据无需迁移或破坏

#### Scenario: 预置数据脚本可在未来替换为正式用户管理流程
- **WHEN** 将来引入正式的用户注册和班级管理功能
- **THEN** 当前基于种子脚本的预置用户和班级数据可被替换或扩展，不影响已上传材料；材料的 class_id / owner_id 外键关系保持自洽

### Requirement: 容器化启动后材料功能立即可用
系统 SHALL 支持通过容器化方式启动，启动完成后所有材料上传、列表、详情端点立即可供调用，无需额外手动初始化数据库。

#### Scenario: 一键启动后预置账号可上传
- **WHEN** 执行容器化启动命令后等待应用就绪
- **THEN** 预置的教师账号能够登录并成功上传材料；随后同班学生能够查到那条记录
