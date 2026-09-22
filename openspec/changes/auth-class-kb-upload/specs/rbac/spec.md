## Purpose

为校园知识库提供基于角色的访问控制，确保教师角色可以上传教学材料而学生角色被严格禁止上传。所有授权检查必须在服务端强制执行，前端 UI 不得作为唯一防护手段。

## ADDED Requirements

### Requirement: 每个用户具有明确的角色属性
系统 SHALL 为每个用户分配 role 属性，取值为 "teacher" 或 "student"。

#### Scenario: 用户角色值域受限
- **WHEN** 查询任意已注册用户的 role 字段
- **THEN** 其值 SHALL 严格等于 "teacher" 或 "student" 之一，不存在其他取值

#### Scenario: 预置种子账号具备正确角色
- **WHEN** 首次部署后检查预置的教师和学生账号
- **THEN** 教师账号 role="teacher"，学生账号 role="student"

### Requirement: 上传端点仅对教师角色开放
系统 SHALL 在上传材料的写端点上执行角色检查。非 teacher 角色的已认证请求必须被拒绝，且不得产生任何数据库写入。

#### Scenario: 学生尝试上传被拒绝
- **WHEN** 已认证但 role=student 的用户调用材料上传端点
- **THEN** 系统返回 403 Forbidden；该请求不得触发任何数据库写入；响应体 SHALL 表明权限不足

#### Scenario: 未认证用户调用上传端点
- **WHEN** 未携带有效会话令牌的请求调用材料上传端点
- **THEN** 系统返回 401 Unauthorized（认证检查优先于角色检查）

#### Scenario: 教师上传成功返回 201
- **WHEN** 已认证且 role=teacher 的用户调用材料上传端点
- **THEN** 在参数校验通过后，系统执行后续班级隔离与持久化逻辑，成功时返回 201 Created 及新建材料的完整 JSON

### Requirement: 所有写端点的授权检查必须在服务端执行
系统 SHALL 仅在服务端执行角色校验逻辑。前端隐藏按钮、禁用控件或修改 UI 不得作为唯一的防护手段。

#### Scenario: 绕过前端直接调用被服务端拒绝
- **WHEN** 通过 Postman / curl / 自定义脚本绕过前端 UI，直接对上传端点发起 HTTP POST 请求
- **THEN** 服务端根据会话令牌解析出的用户角色执行检查；student 身份的请求 SHALL 被服务端以 403 拒绝，不依赖任何前端参与

#### Scenario: 前端未正确隐藏按钮时后端仍拦截
- **WHEN** 前端因 bug 未能对学生隐藏上传按钮，学生在浏览器中点击按钮发起上传
- **THEN** 服务端仍以 403 拒绝请求；错误出现在 UI 层但安全基线不受影响
