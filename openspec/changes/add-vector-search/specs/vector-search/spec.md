## Purpose

为班级知识库提供基于语义向量的检索能力，使用户能通过自然语言查询本班教学材料，并获得带来源溯源（文档名、页码、段落位置）的精准结果。

## ADDED Requirements

### Requirement: 语义检索端点
系统 SHALL 提供 `POST /api/search` 端点，接受 JSON 请求体 `{ "query": "<文本>", "top_k": <int>, "threshold": <float> }`，返回本班范围内语义最相关的 chunk 列表。`query` 必填，`top_k` 默认 5（范围 1-20），`threshold` 可选（0-1，默认 0.0 即不过滤）。未登录返回 401。

#### Scenario: 成功检索返回溯源信息
- **WHEN** 已认证用户 POST `/api/search` 包含 `{"query": "光合作用过程"}`
- **THEN** 系统返回 200，响应体为 `{ "results": [ { "material_id": <int>, "title": "<文档标题>", "file_orig_name": "<原始文件名或null>", "page_number": <int或null>, "chunk_index": <int>, "text": "<匹配文本片段>", "score": <float> }, ... ] }`，按 score 降序排列

#### Scenario: 检索结果仅包含本班材料
- **WHEN** A 班用户上传包含"量子力学"的材料；B 班用户查询"量子力学"
- **THEN** B 班用户的检索结果中 SHALL NOT 包含 A 班的任何材料

#### Scenario: top_k 参数生效
- **WHEN** 用户请求 `{"query": "xxx", "top_k": 3}`
- **THEN** 响应 results 数组长度 SHALL <= 3

#### Scenario: threshold 过滤低相关性结果
- **WHEN** 用户请求 `{"query": "xxx", "threshold": 0.7}`
- **THEN** 响应中所有 results 的 score SHALL >= 0.7

#### Scenario: query 为空被拒绝
- **WHEN** 用户请求 `{"query": ""}` 或缺少 query 字段
- **THEN** 系统返回 400 Bad Request

#### Scenario: top_k 越界被拒绝
- **WHEN** 用户请求 `{"query": "xxx", "top_k": 0}` 或 `top_k: 21`
- **THEN** 系统返回 400 Bad Request

### Requirement: 班级隔离检索
检索 SHALL 在服务端强制限定于当前用户的 effective_class（教师可切换授课班级，学生固定为所属班级）。向量数据库的查询条件 SHALL 包含 class_id 过滤，不依赖应用层事后过滤。

#### Scenario: 教师切换班级后检索范围变化
- **WHEN** 教师教授 A 班和 B 班，当前切换到 A 班视图，执行检索
- **THEN** 检索结果仅包含 A 班材料

#### Scenario: 学生只能检索本班
- **WHEN** A 班学生执行检索
- **THEN** 检索结果仅包含 A 班材料，无法通过任何参数访问 B 班内容

### Requirement: 内容溯源信息完整
每个检索结果 SHALL 包含足够的信息让用户定位到原始文档中的具体位置：material_id（文档标识）、title（文档标题）、file_orig_name（原始文件名，文本材料为 null）、page_number（PDF 页码，从 1 开始；非 PDF 为 null）、chunk_index（该 chunk 在文档内的序号，从 0 开始）、text（匹配的实际文本片段，最长 500 字符）、score（相似度分数 0-1）。

#### Scenario: PDF 材料返回页码
- **WHEN** 检索命中一份 PDF 材料的某个 chunk，该 chunk 来源于 PDF 第 3 页
- **THEN** 结果中 page_number SHALL 为 3

#### Scenario: 文本材料页码为 null
- **WHEN** 检索命中一份 txt 或 md 材料的 chunk
- **THEN** 结果中 page_number SHALL 为 null

#### Scenario: 文本片段截断
- **WHEN** 检索命中的 chunk 原始文本超过 500 字符
- **THEN** 返回的 text 字段 SHALL 截断至 500 字符并以 "..." 结尾

### Requirement: 向量索引自动维护
系统 SHALL 在材料上传成功后自动将内容切分为 chunk 并生成 embedding 存入向量数据库；在材料删除时同步清除对应向量。索引维护 SHALL 不阻塞上传/删除的响应（可异步），但最终一致性 SHALL 保证上传后立即可检索到。

#### Scenario: 上传后立即可检索
- **WHEN** 教师上传一份包含"细胞分裂"的材料，上传返回 201 后立刻执行检索 query="细胞分裂"
- **THEN** 检索结果 SHALL 包含该材料的 chunk

#### Scenario: 删除后不可检索
- **WHEN** 教师删除一份材料后执行检索
- **THEN** 检索结果 SHALL NOT 包含该材料的任何 chunk

### Requirement: 首次启动自动回填向量索引
系统 SHALL 在启动时检测向量索引是否为空，若为空则对所有已有材料执行批量 embedding 回填。回填过程 SHALL 不阻塞应用启动（可后台执行），但完成后立即可检索。

#### Scenario: 全新部署首次启动
- **WHEN** 全新容器首次启动，数据库中有 2 条种子材料
- **THEN** 应用启动完成后，对这 2 条材料的检索可用

#### Scenario: 已有数据库升级
- **WHEN** 携带已有材料的数据库启动新版本（向量索引为空）
- **THEN** 后台回填完成后，所有已有材料可被检索到
