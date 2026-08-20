# Moneki 展示型线上部署方案

## 1. 目标与范围

将当前 Moneki 项目部署为一个可公开访问的展示站点，线上行为与本地版本保持一致：

- React 看板可加载默认范围、日期筛选、指标卡、趋势图、Top 10 商品和数据质量审计。
- AI 数据问答可使用 Mock provider；配置 DeepSeek 后可使用真实模型。
- 同一页面会话内支持追问；刷新页面后会话消失是可接受的。
- 不购买云数据库、不购买对象存储、不使用 Cloudflare Worker 代理 DeepSeek。
- 当前数据已脱敏，展示型部署暂不处理数据泄露问题；仍不得把 DeepSeek 私钥放进前端。

本方案是演示/小流量方案，不承诺生产级的高可用、账号体系、跨实例会话和数据持久化。

## 2. 最终架构

```text
浏览器
  -> Cloudflare Pages（React/Vite，使用 pages.dev 地址）
       -> VITE_API_BASE=https://<腾讯云 API HTTPS 地址>
  -> 腾讯云 CloudBase 云托管/Cloud Run（FastAPI）
       -> 部署包内只读 data/raw/*.csv 或构建出的 SQLite
       -> MONEKI_AI_API_KEY（腾讯云环境变量/Secret）
       -> DeepSeek API（https://api.deepseek.com）
```

### 组件职责

| 组件 | 职责 |
| --- | --- |
| Cloudflare Pages | 构建并托管 `frontend/dist`，不放业务密钥 |
| 腾讯云 API Service | 运行 FastAPI、读取 SQLite、执行白名单查询、调用 DeepSeek |
| 部署包数据 | 包含脱敏 CSV；服务启动时生成 SQLite，运行时只读 |
| 腾讯云环境变量 | 保存 CORS、数据库路径、AI provider 和 DeepSeek Key |
| DeepSeek | 仅负责 AI 问题识别/工具选择；金额和订单数仍由 SQLite SQL 计算 |

## 3. 为什么不使用云数据库或 Cloudflare Worker

- 当前数据量小且只读，SQLite 足够；不需要 PostgreSQL、Redis、Vectorize 或对象存储。
- 数据可以随后端部署包发布。服务重启时从 CSV 重建 SQLite，展示数据很小，启动耗时可接受。
- Cloudflare Worker 不参与 AI 链路，避免国内访问路径增加一个不必要的中间层。
- `MONEKI_AI_API_KEY` 只在腾讯云后端读取；前端构建变量只能包含 API 地址。

## 4. 后端部署要求

### 4.1 平台

优先使用腾讯云 CloudBase 云托管/Cloud Run，选择支持 Docker 的 Python 服务并设置低实例数或按请求缩容。若当前账号没有该能力，使用一台最低配置的腾讯云轻量应用服务器运行同一个 Docker 镜像。

后端必须提供公网 HTTPS 地址，不能让 Cloudflare Pages 调用 `http://公网IP:8000`，否则浏览器会拦截混合内容。

### 4.2 容器与启动流程

新增后端 `Dockerfile`（或等效腾讯云构建配置），要求：

1. 使用固定版本的 Python 3.11/3.12 基础镜像。
2. 安装 `backend/requirements.txt`。
3. 复制 `backend/`、`data/raw/` 和必要的项目文件。
4. 构建阶段执行测试；镜像构建时执行 `python -m app.ingestion.load_data`，生成 `backend/data/moneki.sqlite3`。
5. 启动命令使用生产模式：

   ```text
   uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
   ```

6. 运行阶段只读查询 SQLite，不在每个请求中重新导入。

如果平台构建阶段不能生成 SQLite，则使用入口脚本：数据库不存在时执行一次 `python -m app.ingestion.load_data`，随后启动 Uvicorn。入口脚本必须避免每次重启无条件清空并重建已有数据库。

### 4.3 生产环境变量

在腾讯云控制台配置，不提交到 Git：

```dotenv
PORT=8000
MONEKI_DB_PATH=backend/data/moneki.sqlite3
MONEKI_CORS_ORIGINS=https://<项目名>.pages.dev
MONEKI_AI_PROVIDER=mock
MONEKI_AI_API_KEY=
MONEKI_AI_BASE_URL=https://api.deepseek.com
MONEKI_AI_MODEL=deepseek-chat
MONEKI_AI_TIMEOUT_SECONDS=20
```

启用真实 DeepSeek 时只改后端变量：

```dotenv
MONEKI_AI_PROVIDER=deepseek
MONEKI_AI_API_KEY=<腾讯云 Secret 中的 DeepSeek Key>
```

不要设置任何 `VITE_*` 私钥变量。Vite 的 `VITE_*` 内容会进入浏览器构建产物。

### 4.4 后端验收

部署完成后检查：

```text
GET  /                 -> 返回 moneki-dashboard-api
GET  /api/v1/health   -> {"status":"ok","database_ready":true}
GET  /api/v1/dashboard
POST /api/v1/assistant/ask
GET  /docs
```

用浏览器打开 API HTTPS 地址的 `/docs`，再从 Pages 页面验证看板、日期筛选、AI 首问、五月追问和“查看此范围”。

## 5. Cloudflare Pages 部署要求

### 5.1 项目配置

- Git 仓库：当前 GitHub 仓库。
- Root directory：`frontend`。
- Build command：`npm ci && npm run build`。
- Output directory：`dist`。
- Node.js：使用 Cloudflare 当前支持的 LTS 版本。

### 5.2 构建环境变量

在 Cloudflare Pages 项目设置中配置：

```dotenv
VITE_API_BASE=https://<腾讯云 API HTTPS 地址>
```

这样 `frontend/src/lib/api.ts` 和 `frontend/src/features/assistant/assistantApi.ts` 会请求腾讯云 API，而不会回退到本机 `127.0.0.1`。

### 5.3 前端验收

- 页面能够正常加载 `/api/v1/dashboard`。
- 日期筛选请求成功，加载/错误/空数据状态仍正常。
- AI 问答请求成功，响应显示 provider、证据和 navigation。
- 浏览器 Network 中只能看到 API 地址和用户问题，不能看到 `MONEKI_AI_API_KEY` 或 DeepSeek Authorization Header。

## 6. 会话策略

当前后端 `ConversationStore` 是进程内存存储，默认 30 分钟过期、最多 100 个会话。展示部署可接受刷新后丢失记忆。

但如果腾讯云平台使用多个实例，同一个 `session_id` 可能落到不同实例。为保证同一浏览器页面内的追问稳定，优先采用以下之一：

1. 展示环境固定单实例；或
2. 将上一轮已验证的结构化工具状态暂存 React 内存，并随下一次请求发送，后端重新校验后执行 SQL。

禁止使用 `localStorage` 持久化会话，因为需求明确允许刷新后清空。

## 7. 发布流程

1. 本地运行后端测试：`cd backend; pytest -q`。
2. 本地构建前端：`cd frontend; npm ci; npm run build`。
3. 构建后端镜像并确认 SQLite 已生成，执行健康检查。
4. 将镜像发布到腾讯云 CloudBase 云托管/Cloud Run。
5. 配置腾讯云环境变量和 DeepSeek Secret。
6. 记录腾讯云 API HTTPS 地址。
7. 在 Cloudflare Pages 设置 `VITE_API_BASE`，触发生产构建。
8. 完成端到端验收后，再切换 `MONEKI_AI_PROVIDER=deepseek`。

## 8. 成本边界

- Cloudflare Pages：展示流量在免费额度内时通常无需付费。
- 腾讯云计算：云函数/按请求服务可能落在免费额度；长驻 Service 或轻量服务器通常按运行资源收费。
- SQLite：本方案不购买数据库和持久化磁盘。
- 环境变量：通常不单独收费；Secret Manager 是否收费以腾讯云控制台当前规则为准。
- DeepSeek：按实际 token 调用量计费；当前线上问答默认使用实时 DeepSeek。
- 流量、日志和超出免费额度的调用可能产生费用，部署后应设置费用提醒和限额。

## 9. 明确不做的事情

- 不把 DeepSeek Key 放入前端或 Cloudflare Pages 环境变量。
- 不引入 Cloudflare D1/Vectorize；Cloudflare Worker 仅承载只读 API 和安全的 DeepSeek 代理调用。
- 不引入 PostgreSQL、Redis、对象存储和登录租户系统。
- 不承诺多实例会话、数据编辑、跨设备同步、自动备份和生产级高可用。

## 当前已落地版本（2026-08-20）

实际部署采用了用户确认的第二种方案：Cloudflare Pages 同源托管前端和 `/api/v1/*` 看板 API，腾讯云 Event Function 仅保存 `DEEPSEEK_API_KEY` 并代理 DeepSeek。线上 API 的 AI provider 默认是 `deepseek/live`，不再使用 Mock；模型只负责意图识别，金额、订单数和客单价仍由 Worker 内置的 SQLite 校验数据计算。

线上地址：

- 前端和 API：`https://moneki-dashboard.pages.dev`
- 独立 Worker API（备用）：`https://moneki-api.tryrevive-deepseek.workers.dev`
- DeepSeek 函数代理：`https://tryrevive-d4gzac2aj49df4aa4.service.tcloudbase.com/api/deepseek`

如果 DeepSeek 调用失败，接口返回 503，不会静默回退到 Mock；实时调用会产生 DeepSeek token 费用，并增加问答延迟。

## 10. 交付验收标准

部署完成必须满足：

- Pages 地址可访问，页面无 localhost 请求。
- API HTTPS 地址健康检查为 `ok`。
- 看板数字与本地测试数据一致。
- 线上 AI provider 为 `deepseek/live`，金额和订单数仍由校验数据计算。
- 同一页面内首问和追问可用；刷新后重新开始会话。
- 前端构建产物和浏览器 Network 中不存在 DeepSeek Key。
- 腾讯云服务重启后能自动恢复 SQLite 数据。
