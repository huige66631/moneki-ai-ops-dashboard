# Moneki AI Ops Dashboard

第一关是一个可本地运行的餐饮经营数据看板：从 `data/raw/` 读取销售流水，清洗后写入 SQLite，由 FastAPI 提供版本化报表接口，React + ECharts 展示经营趋势和商品贡献。

## 三步启动

```powershell
# 1. 安装后端依赖并导入（从原始 CSV 重建数据库）
cd backend
python -m pip install -r requirements.txt
python -m app.ingestion.load_data

# 2. 启动 API（另开终端）
python -m uvicorn app.main:app --reload --port 8000

# 3. 启动前端（另开终端）
cd frontend
npm install
npm run dev
```

页面默认地址：`http://127.0.0.1:5173/`。API 文档：`http://127.0.0.1:8000/docs`。

前端默认请求 `http://127.0.0.1:8000`。如需创建 `frontend/.env.local` 覆盖 API 地址，请以 `frontend/.env.example` 为准；修改后需要重启 `npm run dev`。

## 架构

```text
data/raw/*.csv -> backend/app/ingestion/load_data.py -> backend/data/moneki.sqlite3
                                                -> FastAPI /api/v1/dashboard + /api/v1/assistant/ask
                                                -> frontend/src/App.tsx + AssistantPanel
```

这张图也是项目的任务拆分图：先由 Codex 阅读数据规则并完成导入层，再实现只依赖数据库的报表 API，最后接入 React 看板和可信问答。每一层都先写清输入、输出和验收条件，下一层只使用上一层已经验证的接口。

### 技术选型与理由

- **SQLite**：项目是本地演示，数据量适中；单文件数据库便于重复导入、审计和提交后复现。
- **FastAPI + Pydantic**：用类型模型固定报表和问答契约，路由只做参数校验，聚合逻辑留在服务层。
- **React + TypeScript + Vite**：看板需要日期筛选、加载/错误/空数据状态和问答联动；类型检查能尽早发现前后端字段漂移。
- **ECharts**：趋势图是现成的业务图表，不把时间轴、空日期和 tooltip 逻辑手写在组件里。
- **白名单查询工具**：AI 只识别问题并选择工具，金额、订单数和日期范围由后端 SQL 决定，避免模型编造数字或生成自由文本 SQL。

具体的 Codex 拆分记录、提示词和修复过程见 [AI_USAGE.md](AI_USAGE.md)；可运行的验收演示见 [DEMO.md](DEMO.md)。

后端按 `api / services / ingestion / models` 分层。导入每次在同一事务中清空并重建事实表、维表和数据质量审计表，因此可重复执行，不会在旧库上累加；如果源文件读取失败，旧数据会回滚保留。金额使用整数分保存；负金额保留计入净营业额。重复记录、缺失金额、非法日期、非正数量和脏外键按 [第一关实施计划](docs/design/phase-1-dashboard/IMPLEMENTATION_PLAN.md) 处理，未匹配商品会显示回退名称。看板 API 额外返回服务端计算的日均营业额，并在数据质量折叠区标明导入时排除的非法日期数量。

## 验证

```powershell
cd backend
pytest -q
cd ../frontend
npm run build
```

当前已完成：数据导入、SQLite 数据集、`/api/v1/dashboard`、`/api/v1/health`、日期筛选、指标卡、连续日期趋势、Top 10 商品表、加载/错误/空数据状态、数据质量折叠审计，以及带真实白名单查询证据的 AI 数据问答。

## 第二关 AI 数据问答

后端默认使用 Mock provider。Mock 只负责识别问题和选择工具，金额、订单数和客单价全部来自 SQLite 查询；不提供自由文本 SQL。对话框会把当前看板日期范围作为没有明确日期问题的上下文。

DeepSeek 配置放在 `backend/.env`（该文件已被 Git 忽略），手动填写 `MONEKI_AI_API_KEY` 后，将 `MONEKI_AI_PROVIDER` 改为 `deepseek`：

```text
MONEKI_AI_PROVIDER=deepseek
MONEKI_AI_API_KEY=填写你的 DeepSeek key
MONEKI_AI_BASE_URL=https://api.deepseek.com
MONEKI_AI_MODEL=deepseek-chat
MONEKI_AI_TIMEOUT_SECONDS=20
```

密钥只由服务端读取，不会进入浏览器、接口响应或日志。完整接口状态和证据结构见 [第二关 API 契约](docs/design/phase-2-ai-qa/API_CONTRACT.md)。

## 第三关：可信 AI 数据问答

第三关在第二关的白名单工具之上增加了三项能力：

- 同一页面内的短期多轮追问，例如先问“牛肉poke 六月卖了多少钱？”，再问“那五月呢？”。服务端只继承上一轮已验证的结构化工具参数，不继承模型回答文本。
- 后端独立数字一致性回归矩阵，覆盖门店品类、商品金额、退款负金额、客单价窗口和空数据范围。期望值使用独立 SQL 或窗口计算，不复用 AI 工具函数。
- 回答返回实际执行的 `navigation` 日期范围。用户点击“查看此范围”后，App 通过唯一的 dashboard API 加载趋势、指标和商品表。

会话保存在 FastAPI 进程内存中，空闲 30 分钟过期，最多保留 100 个会话；应用重启后需要重新说明上下文。这是本地演示约束，不是跨设备消息存储。流式输出、生产部署和门店筛选仍未实现。

可按 [DEMO.md](DEMO.md) 在 1 到 3 分钟内复现首问、五月追问、证据展开、看板联动和测试验证。
