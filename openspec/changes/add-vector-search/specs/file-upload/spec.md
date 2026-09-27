## MODIFIED Requirements

### Requirement: 上传时自动提取文本并生成向量
系统 SHALL 在文件材料上传成功落库前自动提取文本正文并写入 `content`：txt/md 的 UTF-8 解码文本即正文；pdf 使用 pypdf 逐页提取文本层后拼接。提取失败（损坏文件、扫描件无文本层、编码异常）SHALL NOT 阻塞上传——材料照常创建（`201`），`content` 置空。当 content 非空时，系统 SHALL 将 content 切分为 chunk 并生成 embedding 存入向量数据库，chunk 记录包含 material_id、class_id、page_number（PDF 按 pypdf 页码，txt/md 统一为 null）、chunk_index。

#### Scenario: PDF 上传后按页切分 chunk
- **WHEN** 教师上传一份 5 页的 PDF，每页提取出文本
- **THEN** 系统按页切分 chunk，每个 chunk 的 page_number 对应 PDF 页码（1-5），chunk_index 从 0 递增

#### Scenario: txt/md 上传后整体切分 chunk
- **WHEN** 教师上传一份 txt 文件，内容 2000 字符
- **THEN** 系统按固定长度（如 500 字符）切分 chunk，所有 chunk 的 page_number 为 null，chunk_index 从 0 递增

#### Scenario: content 为空时不生成向量
- **WHEN** 教师上传一份扫描件 PDF（无文本层），content 提取为空
- **THEN** 材料照常创建（201），但不生成任何 chunk，该材料不可被语义检索到

#### Scenario: 上传响应不受向量化影响
- **WHEN** 教师上传一份文件材料
- **THEN** 上传端点返回 201 的响应体 SHALL 与当前一致（包含 material 元数据），不包含向量相关信息
