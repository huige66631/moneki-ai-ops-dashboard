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

## 架构

```text
data/raw/*.csv -> backend/app/ingestion/load_data.py -> backend/data/moneki.sqlite3
                                                -> FastAPI /api/v1/dashboard
                                                -> frontend/src/App.tsx
```

后端按 `api / services / ingestion / models` 分层。导入每次清空并重建事实表、维表和数据质量审计表，因此可重复执行，不会在旧库上累加。金额使用整数分保存；负金额保留计入净营业额。重复记录、缺失金额、非正数量和脏外键按 [第一关实施计划](docs/design/phase-1-dashboard/IMPLEMENTATION_PLAN.md) 处理，未匹配商品会显示回退名称。

## 验证

```powershell
cd backend
pytest -q
cd ../frontend
npm run build
```

当前已完成：数据导入、SQLite 数据集、`/api/v1/dashboard`、`/api/v1/health`、日期筛选、指标卡、连续日期趋势、Top 10 商品表、加载/错误/空数据状态和数据质量折叠审计。

尚未实现：第二关 AI 数据问答、模型接入、聊天界面、第三关部署与生产化运维。
