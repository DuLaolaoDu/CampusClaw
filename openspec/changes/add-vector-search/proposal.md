## Why

当前知识库仅支持按班级列出全部材料，缺乏语义检索能力。教师和学生无法在大量教学资料中快速定位到相关内容段落，也无法追溯某段回答出自哪份文档的哪个位置。需要引入向量检索，使本班用户能通过自然语言查询知识库，并获得带来源引用的精准结果。

## What Changes

- 新增向量数据库（Chroma）存储材料内容的 embedding，在材料上传/删除时同步维护向量索引
- 新增语义检索端点 `POST /api/search`，接受查询文本，返回本班范围内的相关 chunk 列表
- 检索结果包含内容溯源信息：来源文档 id、文档标题、原始文件名、页码（PDF）、chunk 序号、匹配的相关文本片段
- 检索强制班级隔离：服务端从会话推导 class_id，仅在本班向量集合中检索，跨班不可达
- 支持教师指定 top_k 和可选的相关性阈值
- 现有材料上传、列表、下载端点保持不变

## Capabilities

### New Capabilities
- `vector-search`: 基于向量数据库的班级隔离语义检索能力，包含 embedding 生成、chunk 切分、向量存储与检索、内容溯源返回

### Modified Capabilities
- `knowledge-base`: 材料上传时触发 embedding 生成与向量入库；材料删除时同步清除对应向量；现有文本提取（content 字段）作为 embedding 输入源
- `file-upload`: 上传流程新增 embedding 步骤（在现有文本提取之后），不改变文件校验、存储、下载行为

## Impact

- **依赖**: 新增 chromadb（嵌入式向量数据库，无需额外服务）、sentence-transformers 或轻量 embedding 模型（如 all-MiniLM-L6-v2）
- **存储**: Chroma 持久化目录挂载到现有 `campusclaw-data` Docker volume，无需新增 volume 或 Dockerfile 改动
- **API**: 新增 `POST /api/search` 端点；材料上传/删除端点内部新增向量同步逻辑，接口契约不变
- **数据库**: SQLite 新增 `chunks` 表记录 chunk 与 material 的映射关系（chunk_id、material_id、page_number、text、chroma_id）
- **启动**: 应用启动时自动初始化 Chroma collection，首次启动对已有材料做批量 embedding 回填
- **性能**: embedding 模型首次加载需下载权重（约 80MB），后续推理在 CPU 上约 50-100ms/chunk
