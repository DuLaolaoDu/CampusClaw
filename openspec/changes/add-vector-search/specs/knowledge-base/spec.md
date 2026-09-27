## MODIFIED Requirements

### Requirement: 材料数据结构预留知识库扩展
材料记录 SHALL 支持两种形式：文本材料（`content` 存用户粘贴的正文）或文件材料（关联 `file_orig_name` 原始文件名、`file_stored_name` 磁盘存储名、`file_size` 字节数、`file_mime` MIME 类型四个文件列，`content` 存上传时自动提取的文本正文，提取失败为空）。`content` 约束 SHALL 放宽为可空。迁移 SHALL 无损——对已有数据行新增列取空默认值，现有文本材料与种子数据不受影响，且不影响将来向量化或全文检索扩展（文件材料的提取文本可直接作为 embedding 输入）。系统 SHALL 在材料记录被创建或更新时，将 content 作为 embedding 输入源，切分为 chunk 后存入向量数据库。

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

#### Scenario: 材料创建时触发向量化
- **WHEN** 教师上传一份材料（文本或文件），content 提取完成后
- **THEN** 系统 SHALL 将 content 切分为 chunk 并生成 embedding 存入向量数据库，chunk 记录关联 material_id、class_id、page_number（PDF 有值，其他为 null）

#### Scenario: 材料删除时清除向量
- **WHEN** 教师删除一份材料
- **THEN** 系统 SHALL 同步清除该材料在向量数据库中的所有 chunk
