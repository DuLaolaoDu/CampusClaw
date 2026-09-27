## Purpose

在用户与教学材料之间建立班级（class_id）数据边界，确保任何角色都只能访问本班范围内的数据，跨班读写在服务端强制拒绝。隔离逻辑必须放在服务端的查询/写入层，不靠前端隐藏按钮或过滤。

## ADDED Requirements

### Requirement: 用户与班级关联
系统 SHALL 在用户记录中存储 class_id，标识该用户所属的班级。每个用户在任意时刻只能隶属于一个班级。

#### Scenario: 用户记录包含非空 class_id
- **WHEN** 查询任意已注册用户
- **THEN** 该用户记录 SHALL 包含一个非空、可与材料记录中 class_id 比较的值

#### Scenario: 预置种子账号具备同一 class_id
- **WHEN** 首次部署后检查预置的教师和两个学生账号
- **THEN** 三者的 class_id SHALL 相同（表示属于同一班级）

### Requirement: 材料与班级关联
系统 SHALL 在每份教学材料记录中存储 class_id，标识该材料所属的班级。class_id 由服务端强制写入，不信任任何来自客户端的值。

#### Scenario: 上传时服务端自动填入班级
- **WHEN** 教师上传一份材料
- **THEN** 该材料的 class_id SHALL 由服务端从当前登录用户的 class_id 推导并写入；上传者无法也无需在请求体中提供 class_id 字段

#### Scenario: 教师伪造他班 class_id 被服务端覆盖
- **WHEN** 教师上传材料时（因逆向工程或测试）在请求体中显式指定了一个与自己班级不同的 class_id
- **THEN** 服务端 SHALL 忽略该客户端传入值，始终以当前教师的 class_id 作为最终写入值；材料落库后 class_id 等于教师的 class_id

### Requirement: 读端点按当前用户班级过滤
系统 SHALL 在返回材料列表或单份材料详情时，仅返回 class_id 等于当前认证用户 class_id 的记录。

#### Scenario: 列表端点 SQL 层强制附加 WHERE 条件
- **WHEN** 系统执行材料列表的数据库查询
- **THEN** SQL 查询中 SHALL 包含 `WHERE class_id = :current_user_class_id`（或等价表达式），且 `:current_user_class_id` 来自服务端会话中存储的当前用户 class_id

#### Scenario: 本班材料正常返回
- **WHEN** 已认证的教师或学生调用材料列表端点
- **THEN** 返回结果中仅包含 class_id 等于该用户 class_id 的材料；响应条数等于本班材料总数

#### Scenario: 本班无材料时返回空列表而非报错
- **WHEN** 用户所在班级尚未有任何人上传材料
- **THEN** 调用材料列表端点 SHALL 返回 200 OK 加空数组（`[]`），而不是 404 或 500

#### Scenario: 跨班访问单份材料被拒绝且不泄露存在性
- **WHEN** 用户通过 URL 直接请求 class_id 与自己不同的材料（例如拿到了别人分享的 material id）
- **THEN** 系统返回 404 Not Found；响应体不得泄露"该材料存在但不属于你"这类信息（统一成"材料不存在"即可）

#### Scenario: 他班列表端点不返回任何本班外的材料
- **WHEN** A 班用户调用材料列表端点
- **THEN** 响应中的所有材料其 class_id SHALL 等于 A 班的 class_id；B 班、C 班的材料不得出现在响应中，哪怕数据库里有几万条

### Requirement: 写端点按当前用户班级强制约束
系统 SHALL 在写入新材料时，将材料的 class_id 设置为当前认证用户的 class_id，忽略或覆盖客户端传入的任何 class_id 参数。

#### Scenario: 上传成功后材料归属正确班级
- **WHEN** 教师上传材料成功（返回 201）
- **THEN** 该材料记录的 class_id SHALL 等于该教师的 class_id；后续任何班级用户读取该材料都受到此 class_id 约束
