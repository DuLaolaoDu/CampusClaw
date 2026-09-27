# class-isolation Specification

## ADDED Requirements

### Requirement: 生效班级的确定与切换
系统 SHALL 为每个会话维护一个"生效班级"，作为所有班级隔离查询与写入的依据：登录时默认为用户自身 class_id；教师可通过班级切换仅在其任教班级集合内变更；学生的生效班级永远等于自身 class_id 且不可变更。

#### Scenario: 登录后生效班级默认为本班
- **WHEN** 任意用户登录成功
- **THEN** 会话中的生效班级 SHALL 等于该用户自身的 class_id

#### Scenario: 教师切换任教班级后生效班级更新
- **WHEN** 教师将生效班级切换为其任教的另一班级
- **THEN** 后续该会话的列表、详情、下载、上传 SHALL 全部以新生效班级为边界，直到再次切换或登出

#### Scenario: 登出后生效班级随会话清除
- **WHEN** 用户登出
- **THEN** 会话与其生效班级 SHALL 一并被清除；再次登录恢复为默认本班

#### Scenario: 学生无法通过任何入口改变生效班级
- **WHEN** 学生尝试切换班级（页面无控件，或直接构造切换请求）
- **THEN** 服务端 SHALL 拒绝（403）且生效班级保持为其自身 class_id

## MODIFIED Requirements

### Requirement: 读端点按当前用户班级过滤
系统 SHALL 在返回材料列表或单份材料详情时，仅返回 class_id 等于当前会话生效班级的记录；生效班级永远来自服务端会话（教师为选中的任教班级，学生为自身 class_id），不信任任何客户端参数。

#### Scenario: 列表端点 SQL 层强制附加 WHERE 条件
- **WHEN** 系统执行材料列表的数据库查询
- **THEN** SQL 查询中 SHALL 包含 `WHERE class_id = :effective_class_id`（或等价表达式），且该值取自服务端会话

#### Scenario: 本班材料正常返回
- **WHEN** 已认证的教师或学生调用材料列表端点或查看仪表盘
- **THEN** 返回结果中仅包含 class_id 等于其生效班级的材料

#### Scenario: 本班无材料时返回空列表而非报错
- **WHEN** 生效班级尚未有任何人上传材料
- **THEN** 系统 SHALL 返回 200 OK 加空列表（页面渲染空态），而不是 404 或 500

#### Scenario: 跨班访问单份材料被拒绝且不泄露存在性
- **WHEN** 用户通过 URL 直接请求 class_id 与其生效班级不同的材料（例如拿到了别人分享的 material id）
- **THEN** 系统返回 404 Not Found；响应不得泄露"该材料存在但不属于你"这类信息

#### Scenario: 他班列表端点不返回任何本班外的材料
- **WHEN** 生效班级为 A 的用户调用材料列表端点
- **THEN** 响应中的所有材料其 class_id SHALL 等于 A；B 班、C 班的材料不得出现在响应中，哪怕数据库里有几万条

#### Scenario: 教师切换生效班级后可见范围随之切换
- **WHEN** 兼任 A、B 两班的教师将生效班级从 A 切换为 B
- **THEN** 其材料列表 SHALL 仅包含 B 班材料，A 班材料不再出现在任何列表/详情/下载路径中（除非切回 A）

### Requirement: 写端点按当前用户班级强制约束
系统 SHALL 在写入新材料时，将材料的 class_id 设置为当前会话的生效班级，忽略或覆盖客户端传入的任何 class_id 参数。

#### Scenario: 上传成功后材料归属正确班级
- **WHEN** 教师在生效班级为 X 的会话中上传材料成功
- **THEN** 该材料记录的 class_id SHALL 等于 X；切换班级前后续读取均受此 class_id 约束

#### Scenario: 教师伪造他班 class_id 被服务端覆盖
- **WHEN** 教师上传时在表单或请求体中显式指定了与生效班级不同的 class_id
- **THEN** 服务端 SHALL 忽略该客户端传入值，始终以生效班级作为最终写入值
