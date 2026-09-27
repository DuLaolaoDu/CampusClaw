# edge-proxy Specification

## Purpose

以 nginx 反向代理作为系统的唯一对外入口：浏览器用户只能访问页面路由与用户侧下载路由，程序化 API（/api/*）不对用户暴露。应用容器不再直接发布端口。

## ADDED Requirements

### Requirement: 应用容器不直接对外发布端口
系统 SHALL 不把 Flask 应用端口映射到宿主机；应用仅在内部网络中可被边缘代理与容器健康检查访问。

#### Scenario: 宿主机直连应用端口失败
- **WHEN** 在宿主机上对 Flask 应用容器端口发起连接（如 curl http://localhost:8000）
- **THEN** 连接 SHALL 失败（端口未发布），外部无法绕过边缘代理访问应用

#### Scenario: 健康检查不依赖对外端口
- **WHEN** Docker Compose 对应用容器执行健康检查
- **THEN** 健康检查 SHALL 在容器内部直连应用完成，正常进入 (healthy) 状态，不受端口未发布影响

### Requirement: 外部访问 /api 被拒绝且不泄露信息
边缘代理 SHALL 对外部请求的 /api/* 路径返回 404，不转发到应用，不区分端点是否存在。

#### Scenario: 外部直连 API 列表被拒
- **WHEN** 用户通过对外入口请求 /api/materials（无论是否携带登录 Cookie）
- **THEN** 边缘代理返回 404，请求不到达应用；响应不泄露后端路由结构

#### Scenario: 外部直连健康检查被拒
- **WHEN** 外部用户通过对外入口请求 /api/health
- **THEN** 边缘代理返回 404（健康检查仅供容器编排内部使用）

### Requirement: 页面与用户侧路由正常放行
边缘代理 SHALL 将页面路由（登录、登出、仪表盘）与用户侧下载路由原样转发到应用，包括表单 POST、multipart 上传与文件下载响应。

#### Scenario: 用户通过入口正常使用页面
- **WHEN** 用户通过对外入口访问登录页、提交登录/上传表单、下载材料
- **THEN** 行为与应用直连时一致；10MB multipart 上传不被代理截断（代理请求体上限 SHALL 不低于应用层的 10MB 限制）

#### Scenario: 用户侧下载可完整取得文件
- **WHEN** 本班用户通过对外入口请求某文件材料的用户侧下载路由
- **THEN** 边缘代理 SHALL 完整转发文件响应（字节数与原文件一致），并保留原文件名 disposition

### Requirement: 对外入口单端口
系统 SHALL 仅通过边缘代理发布一个对外端口；用户按文档 URL（含端口）访问页面即可使用全部功能。

#### Scenario: compose 起停后入口可用
- **WHEN** 执行 docker compose up -d 并等待两个服务均 healthy
- **THEN** 通过对外入口可完成登录→查看列表→上传→下载→切换班级→登出的完整闭环
