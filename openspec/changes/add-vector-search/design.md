## Context

当前 CampusClaw 使用 Flask + SQLite 技术栈，材料上传后提取文本存入 `materials.content` 字段。系统已有班级隔离机制（`class_id` 强制从服务端 session 推导），以及文件上传时的文本提取管道（`extract.py`）。需要在此基础上增加语义检索能力，使教师和学生能在本班范围内通过自然语言查询知识库，并获得带来源溯源的结果。

## Goals / Non-Goals

**Goals:**
- 提供班级隔离的语义检索 API，返回带溯源信息的 chunk 列表
- 利用现有 `materials.content` 作为 embedding 输入源，零数据迁移
- 向量索引与材料 CRUD 保持最终一致性
- 首次启动自动回填已有材料的向量索引

**Non-Goals:**
- 不支持跨班级检索或全局搜索
- 不支持对图片、表格等非文本内容的向量化
- 不引入大模型生成回答（仅做检索，不做 RAG 生成）
- 不支持用户自定义 embedding 模型或参数调优
- 不提供向量索引的管理界面或 API

## Decisions

### 1. 向量数据库选型：Chroma（嵌入式）

**选择**: Chroma（本地持久化模式）

**理由**:
- 嵌入式部署，无需额外服务进程，与现有 SQLite 架构一致
- Python 原生支持，API 简洁，学习成本低
- 支持 metadata 过滤（用于班级隔离），性能满足小规模场景（<10k 文档）
- 持久化目录可挂载到现有 `campusclaw-data` Docker volume

**替代方案**:
- **Milvus**: 分布式架构，适合大规模场景，但需要独立服务，增加部署复杂度
- **PgVector**: 需要 PostgreSQL，与当前 SQLite 技术栈不匹配
- **FAISS**: 纯向量索引库，缺乏 metadata 过滤和持久化管理，需自行实现

### 2. Embedding 模型：sentence-transformers (all-MiniLM-L6-v2)

**选择**: `sentence-transformers/all-MiniLM-L6-v2`（384 维，约 80MB）

**理由**:
- 轻量级，CPU 推理速度快（50-100ms/chunk）
- 中文支持良好（多语言模型）
- 社区广泛使用，质量稳定
- 模型文件可缓存到 Docker volume，避免每次启动重新下载

**替代方案**:
- **OpenAI embeddings**: 需要 API key，增加外部依赖和成本
- **大型模型（如 bge-large）**: 精度更高但推理慢，CPU 场景不实用
- **本地训练模型**: 需要标注数据，成本过高

### 3. Chunk 切分策略：按页（PDF）+ 固定长度（文本）

**选择**:
- PDF: 按 pypdf 提取的页切分，每页一个 chunk（保留 page_number 溯源）
- txt/md: 按 500 字符固定长度切分，重叠 50 字符（避免语义断裂）

**理由**:
- PDF 按页切分天然保留页码信息，符合用户溯源习惯
- 文本固定长度切分简单可靠，重叠窗口避免边界语义丢失
- chunk 大小适中（500 字符 ≈ 200-300 词），embedding 质量稳定

**替代方案**:
- **语义切分（按段落/句子）**: 实现复杂，边界判断不稳定
- **滑动窗口**: 重叠比例需调优，chunk 数量膨胀

### 4. 向量同步时机：同步写入（上传时）+ 异步回填（启动时）

**选择**:
- 材料上传：同步执行 chunk 切分和 embedding，写入向量库后再返回 201
- 材料删除：同步删除对应向量
- 首次启动回填：后台线程异步执行，不阻塞应用启动

**理由**:
- 上传时同步写入保证"上传后立即可检索"的契约
- embedding 耗时短（50-100ms/chunk），对用户感知影响小
- 启动回填可能涉及大量材料，异步执行避免启动超时

**替代方案**:
- **完全异步（消息队列）**: 增加架构复杂度，当前规模不必要
- **定时批量同步**: 无法保证"立即可检索"

### 5. 班级隔离实现：Chroma metadata 过滤

**选择**: 在 Chroma 查询时使用 `where={"class_id": "<user_class>"}` 过滤

**理由**:
- Chroma 原生支持 metadata 过滤，查询效率高
- 避免应用层事后过滤，减少数据传输
- 与现有 class_id 隔离逻辑一致

### 6. Chunk 元数据存储：SQLite `chunks` 表

**选择**: 新增 `chunks` 表记录 chunk 与 material 的映射关系

**表结构**:
```sql
CREATE TABLE chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    class_id TEXT NOT NULL,
    chroma_id TEXT UNIQUE NOT NULL,  -- Chroma 中的 document id
    chunk_index INTEGER NOT NULL,    -- 文档内序号（从 0 开始）
    page_number INTEGER,             -- PDF 页码（从 1 开始），非 PDF 为 null
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_chunks_material ON chunks(material_id);
CREATE INDEX idx_chunks_class ON chunks(class_id);
```

**理由**:
- 保留 chunk 与 material 的关联关系，支持删除时级联清理
- `chroma_id` 用于在 Chroma 中定位 document
- `page_number` 支持 PDF 溯源
- 使用 `ON DELETE CASCADE` 简化删除逻辑

## Risks / Trade-offs

### [Risk] Embedding 模型首次加载需下载权重（约 80MB）
→ **Mitigation**: 模型文件缓存到 Docker volume（`/app/data/models`），首次启动下载后后续启动直接使用本地缓存。Dockerfile 中可预下载模型镜像层。

### [Risk] PDF 文本提取失败导致无法向量化
→ **Mitigation**: 与现有逻辑一致，提取失败时 `content` 置空，不生成 chunk，材料仍可下载但不可检索。不阻塞上传流程。

### [Risk] 大量材料启动回填耗时过长
→ **Mitigation**: 后台线程异步执行，应用启动后立即提供服务。回填进度可通过日志观察。对于超大规模场景（>1000 份材料），可考虑分批处理或限制回填并发。

### [Risk] Chroma 持久化目录损坏导致索引丢失
→ **Mitigation**: Chroma 数据存储在 `campusclaw-data` volume，与 SQLite 数据库同目录。启动时检测索引是否为空，自动触发回填。定期备份 volume。

### [Risk] Embedding 推理占用 CPU 影响其他请求
→ **Mitigation**: 当前规模（<10k 文档）下推理耗时短，影响可控。若成为瓶颈，可考虑使用 GPU 加速或限制并发推理请求。

### [Trade-off] 同步写入 vs 异步写入
- 同步写入保证"立即可检索"，但上传响应时间增加 50-200ms
- 异步写入响应快，但需引入消息队列，增加架构复杂度
- 当前选择同步，符合小规模场景的简单性原则

### [Trade-off] 固定长度切分 vs 语义切分
- 固定长度简单可靠，但可能在句子中间切断
- 语义切分更自然，但实现复杂，边界判断不稳定
- 当前选择固定长度 + 重叠窗口，平衡简单性和语义完整性
