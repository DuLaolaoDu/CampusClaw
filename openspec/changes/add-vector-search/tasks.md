## 1. 依赖与配置

- [ ] 1.1 在 `requirements.txt` 中添加 `chromadb>=0.4.0` 和 `sentence-transformers>=2.2.0`，运行 `pip install -r requirements.txt` 验证安装成功
- [ ] 1.2 在 `app/config.py` 中添加向量相关配置：`CHROMA_PERSIST_DIR`（默认 `data/chroma`）、`EMBEDDING_MODEL_NAME`（默认 `all-MiniLM-L6-v2`）、`CHUNK_SIZE`（默认 500）、`CHUNK_OVERLAP`（默认 50），验证配置可正常加载
- [ ] 1.3 在 `docker-compose.yml` 中确认 `campusclaw-data` volume 挂载路径包含 Chroma 持久化目录和模型缓存目录，运行 `docker-compose config` 验证配置正确

## 2. 数据库 Schema

- [ ] 2.1 在 `app/db.py` 的 `SCHEMA_SQL` 中添加 `chunks` 表定义（包含 `id`, `material_id`, `class_id`, `chroma_id`, `chunk_index`, `page_number`, `created_at` 字段及索引），启动应用验证表创建成功
- [ ] 2.2 在 `app/db.py` 的 `migrate_schema()` 中添加幂等迁移逻辑：检测 `chunks` 表是否存在，不存在则创建，运行迁移脚本验证旧数据库可正常升级

## 3. Embedding 服务

- [ ] 3.1 创建 `app/embeddings.py`，实现 `EmbeddingService` 类：初始化时加载 sentence-transformers 模型（支持延迟加载），提供 `encode(texts: list[str]) -> list[list[float]]` 方法，编写单元测试验证模型加载和编码输出维度正确（384 维）
- [ ] 3.2 在 `app/embeddings.py` 中实现 `chunk_text(text: str, chunk_size: int, overlap: int) -> list[tuple[int, str]]` 函数：按固定长度切分文本并返回 `(chunk_index, chunk_text)` 列表，重叠窗口处理边界，编写单元测试验证切分逻辑（包括空文本、短文本、长文本场景）
- [ ] 3.3 在 `app/embeddings.py` 中实现 `chunk_pdf(pdf_bytes: bytes) -> list[tuple[int, str, int]]` 函数：使用 pypdf 按页提取文本并返回 `(chunk_index, page_text, page_number)` 列表，编写单元测试验证 PDF 切分逻辑和页码保留

## 4. 向量存储集成

- [ ] 4.1 创建 `app/vectorstore.py`，实现 `VectorStore` 类：初始化时连接 Chroma（持久化模式），提供 `add_documents(chunks: list[dict], embeddings: list[list[float]])` 方法，每个 chunk 包含 `chroma_id`, `material_id`, `class_id`, `chunk_index`, `page_number`, `text` 元数据，编写单元测试验证文档添加和元数据存储
- [ ] 4.2 在 `app/vectorstore.py` 中实现 `search(query_embedding: list[float], class_id: str, top_k: int, threshold: float) -> list[dict]` 方法：使用 Chroma 的 `where` 过滤 `class_id`，返回包含 `material_id`, `chunk_index`, `page_number`, `text`, `score` 的结果列表，编写单元测试验证班级隔离和阈值过滤
- [ ] 4.3 在 `app/vectorstore.py` 中实现 `delete_by_material_id(material_id: int)` 方法：删除指定材料的所有 chunk，编写单元测试验证删除操作不影响其他材料

## 5. 上传流程集成

- [ ] 5.1 修改 `app/materials.py` 的 `upload_material()` 函数：在材料创建后调用 `EmbeddingService` 和 `VectorStore`，对 `content` 进行切分和向量化，将 chunk 元数据写入 `chunks` 表，编写集成测试验证上传后向量库中存在对应 chunk
- [ ] 5.2 修改 `app/materials.py` 的 `upload_file_material()` 函数：在文件提取文本后执行向量化流程，PDF 按页切分保留 `page_number`，txt/md 按固定长度切分，编写集成测试验证不同类型文件的切分和向量化
- [ ] 5.3 在 `app/materials.py` 中处理向量化失败场景：embedding 模型加载失败或编码异常时记录日志但不阻塞上传（材料创建成功，向量库为空），编写测试验证上传接口仍返回 201

## 6. 删除流程集成

- [ ] 6.1 在 `app/materials.py` 中添加 `delete_material()` 函数（如不存在）：删除材料记录后同步调用 `VectorStore.delete_by_material_id()` 清除向量，编写集成测试验证删除后向量库中无对应 chunk
- [ ] 6.2 确保 `chunks` 表的 `ON DELETE CASCADE` 外键约束生效：删除材料后 `chunks` 表对应记录自动清除，编写测试验证级联删除

## 7. 检索端点

- [ ] 7.1 在 `app/materials.py` 或新建 `app/search.py` 中实现 `POST /api/search` 端点：接收 `query`, `top_k`, `threshold` 参数，调用 `EmbeddingService.encode()` 生成查询向量，调用 `VectorStore.search()` 检索，返回符合 spec 格式的 JSON 响应，编写集成测试验证端点响应格式
- [ ] 7.2 在检索端点中实现参数校验：`query` 必填且非空，`top_k` 范围 1-20（默认 5），`threshold` 范围 0-1（默认 0.0），校验失败返回 400，编写测试验证边界值
- [ ] 7.3 在检索端点中实现内容溯源信息组装：从 `chunks` 表查询 `material_id` 对应的 `title`, `file_orig_name`，截断 `text` 至 500 字符并添加 "..." 后缀，编写测试验证返回字段完整性
- [ ] 7.4 在检索端点中实现班级隔离：从 `current_user` 获取 `effective_class`，传递给 `VectorStore.search()` 的 `where` 条件，编写测试验证跨班检索返回空结果

## 8. 启动初始化

- [ ] 8.1 在 `app/__init__.py` 的 `create_app()` 中添加启动钩子：检测 Chroma 集合是否为空，若为空则查询所有 `materials` 记录，批量执行 chunk 切分和向量化，写入向量库和 `chunks` 表，编写测试验证空索引触发回填
- [ ] 8.2 实现回填逻辑的异步执行：使用后台线程执行批量向量化，应用启动后立即提供服务，回填完成后记录日志，编写测试验证回填不阻塞应用启动
- [ ] 8.3 处理回填失败场景：单条材料向量化失败时记录日志并跳过，不影响其他材料回填，编写测试验证部分失败不影响整体流程

## 9. 测试与验证

- [ ] 9.1 编写端到端测试：上传材料 → 执行检索 → 验证返回结果包含正确的溯源信息（material_id, title, page_number 等），验证班级隔离（A 班材料不可被 B 班检索）
- [ ] 9.2 编写性能测试：上传 10 份材料（含 PDF），验证检索响应时间 < 500ms，验证启动回填 10 份材料耗时 < 30s
- [ ] 9.3 在 Docker 容器中验证完整流程：构建镜像 → 启动容器 → 上传材料 → 执行检索 → 验证结果，确认 Chroma 持久化目录和模型缓存正确挂载到 volume

## 10. 文档与配置

- [ ] 10.1 更新 `README.md`：添加向量检索 API 使用说明（请求格式、响应格式、示例），说明首次启动模型下载和回填行为，说明 Chroma 和模型缓存的 volume 挂载配置
- [ ] 10.2 在 `.env.example` 中添加向量相关配置示例：`CHROMA_PERSIST_DIR`, `EMBEDDING_MODEL_NAME`, `CHUNK_SIZE`, `CHUNK_OVERLAP`，添加注释说明各配置项作用
- [ ] 10.3 更新 `docker-compose.yml`：确认 `campusclaw-data` volume 挂载路径包含 Chroma 持久化目录（如 `./data/chroma`）和模型缓存目录（如 `./data/models`），验证容器启动后目录权限正确
