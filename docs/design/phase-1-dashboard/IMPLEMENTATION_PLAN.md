# 第一关：数据看板实施计划

## 1. 目标和边界

本阶段交付一个可本地运行的餐饮经营数据看板。运营人员可以选择日期范围，查看每日营业额趋势、订单数、客单价和营业额最高的十个商品。

本阶段必须为第二关 AI 数据问答提供稳定的真实数据查询层。不要在本阶段接入大模型、聊天界面、流式输出或部署功能。

完成后，使用者应能在三步内启动服务和页面，并能用一个 API 响应解释页面上的每个数字。

## 2. 当前数据和发现

原始文件位于 `data/raw/`：

| 文件 | 作用 | 行数（含表头） |
| --- | --- | ---: |
| `sales.csv` | 销售流水 | 12,132 |
| `stores.csv` | 门店维表 | 6 |
| `products.csv` | 商品维表 | 21 |

销售日期覆盖 2026-05-01 到 2026-07-31。数据不是干净样例。当前文件中已观察到以下情况：

| 问题 | 观察值 | 处理原则 |
| --- | ---: | --- |
| 规范化前的重复行 | 至少 76 行 | 清洗后按完整业务字段去重 |
| 规范化后重复行 | 78 行 | 排除出报表，保留审计计数 |
| 缺失金额 | 120 行 | 不计入金额、订单和商品排行 |
| 带货币符号的金额 | 40 行 | 去除符号后解析为十进制金额 |
| 负金额 | 49 行 | 保留，计入净营业额 |
| 未匹配门店外键 | 11 行 | 保留，显示回退名称 |
| 未匹配商品外键 | 30 行 | 保留，显示回退名称 |
| 非正数量 | 25 行 | 保留金额；数量字段记为无效，不作为销量统计依据 |

不要假定这些数量永远不变。代码必须依规则计算审计指标，而不是写死这些数字。

## 3. 固定技术方案和目录结构

使用单仓库结构。不要把前端和后端拆成独立 Git 仓库。

```text
data/
  raw/                     # 已下载的原始 CSV，只读并提交
backend/
  app/
    api/                   # HTTP 路由
    services/              # 报表聚合和数据访问
    ingestion/             # CSV 解析、清洗和入库
    models/                # Pydantic 响应模型
  tests/
  requirements.txt
  .env.example
frontend/
  src/
    components/
    features/dashboard/
    lib/
  package.json
README.md
```

- 后端：Python 3.12、FastAPI、SQLite、Pydantic、pytest。
- 前端：React、TypeScript、Vite、ECharts。
- 数据库文件放在 `backend/data/` 或可配置路径，并加入 `.gitignore`。
- CORS 只允许本地前端开发地址。不要在代码中写入密钥。

## 4. 数据清洗和报表口径

### 4.1 清洗顺序

导入脚本必须可重复执行。每次执行都从原始 CSV 重建 SQLite 数据库，不能在旧数据库上追加数据。

1. 读取 CSV，并记录每行的来源文件和原始行号。
2. 去除字段首尾空白；将 `store_id`、`product_id` 和 `order_id` 转为大写。
3. 解析日期。依次接受 `YYYY-MM-DD`、`YYYY/MM/DD`、`DD-MM-YYYY`，输出 ISO 日期。
4. 去除金额中的货币符号和空白，使用十进制类型解析金额。空值或无法解析的金额标记为无效。
5. 将数量解析为整数。小于或等于零的数量标记为无效数量，不改写金额。
6. 使用规范化后的 `order_id`、日期、门店 ID、商品 ID、数量、金额和支付方式组成重复判定键。只保留首次出现的记录。
7. 左连接门店和商品维表。未匹配外键不能删除销售记录。
8. 写入销售事实表、维表和数据质量审计表。

### 4.2 数据库模型

至少建立以下表：

```text
stores(store_id PK, store_name, category, district)
products(product_id PK, product_name, product_category, unit_price)
sales_facts(
  id PK,
  source_line_number,
  order_id,
  sale_date,
  store_id,
  product_id,
  quantity,
  amount,
  payment,
  amount_is_valid,
  quantity_is_valid,
  store_is_matched,
  product_is_matched
)
data_quality_events(
  run_id,
  source_line_number,
  sale_date,
  rule_name,
  is_excluded,
  created_at
)
data_quality_audit(run_id, rule_name, affected_rows, created_at)
```

金额在 Python 中使用 `Decimal`，数据库以整数分或固定精度十进制保存。不要用二进制浮点数累计营业额。

### 4.3 统计口径

| 指标 | 计算规则 |
| --- | --- |
| 日期范围 | `start_date` 和 `end_date` 均包含在内 |
| 有效报表记录 | 日期、订单号和金额有效，且不是规范化后的重复记录 |
| 营业额 | 有效报表记录的金额之和，保留负金额 |
| 订单数 | 有效报表记录的去重 `order_id` 数量 |
| 客单价 | 营业额除以订单数；订单数为零时返回 `null` |
| 每日营业额 | 按规范化日期汇总有效报表记录的金额 |
| 每日订单数 | 按规范化日期汇总去重 `order_id` |
| 每日客单价 | 当日营业额除以当日订单数；订单数为零时为 `null` |
| Top 10 商品 | 按净营业额降序；并列时按商品 ID 升序；未匹配商品显示 `未匹配商品 (<product_id>)` |

商品表不显示“销量”主指标，除非数量有效性规则在页面中明确标注。第一关的 Top 10 表应显示商品、商品类别、净营业额、订单数和营业额占比。

## 5. API 契约

实现一个稳定的版本化接口：

```text
GET /api/v1/dashboard?start_date=2026-05-01&end_date=2026-07-31
```

参数：

- `start_date`：ISO 日期，查询起始日。
- `end_date`：ISO 日期，查询结束日。
- 两个参数必须同时提供或同时省略。省略时接口使用数据中的最小和最大日期，并在响应 `range` 中返回实际范围。
- 只提供其中一个参数时返回 HTTP 422 和可读错误信息。
- 起始日大于结束日时返回 HTTP 422 和可读错误信息。

成功响应必须保持以下结构。数值字段返回 JSON number，不要把金额格式化为带货币符号的字符串。只有订单数为零时，`average_order_value` 可以为 `null`。

```json
{
  "range": {
    "start_date": "2026-05-01",
    "end_date": "2026-07-31"
  },
  "summary": {
    "revenue": 0,
    "order_count": 0,
    "average_order_value": 0,
    "average_daily_revenue": 0
  },
  "daily": [
    {
      "date": "2026-05-01",
      "revenue": 0,
      "order_count": 0,
      "average_order_value": 0
    }
  ],
  "top_products": [
    {
      "rank": 1,
      "product_id": "P01",
      "product_name": "豚骨拉面",
      "product_category": "主食",
      "revenue": 0,
      "order_count": 0,
      "revenue_share": 0
    }
  ],
  "data_quality": {
    "included_record_count": 0,
    "excluded_duplicate_count": 0,
    "excluded_invalid_amount_count": 0,
    "excluded_invalid_date_count": 0,
    "unmatched_store_count": 0,
    "unmatched_product_count": 0
  }
}
```

`data_quality` 统计所选日期范围内的记录和质量事件，不作为前端主视觉指标。非法日期没有可用于筛选的日期，`excluded_invalid_date_count` 按最近一次导入的全部非法日期事件统计，并在界面明确标注为“导入”。开发阶段可在折叠区域展示它，方便验证数据口径。`data_quality_events` 保存逐行事件，`data_quality_audit` 保存整次导入的汇总。`summary.average_daily_revenue` 由服务层按所选范围的自然日天数计算，包含无销售日。

同时提供 `GET /api/v1/health`。它返回服务是否存活以及数据库是否已准备好。前端不要依赖该接口显示业务数据。

## 6. 前端体验和状态

页面首先展示看板，不要做营销首页。采用桌面优先但可在窄屏正常阅读的单页布局。

页面必须包含：

1. 页面标题和当前日期范围。
2. 起始日期、结束日期和“应用筛选”按钮。
3. 三个指标：营业额、订单数、客单价。
4. 每日营业额趋势折线图。横轴按日期连续显示，日期范围中的无销售日以零值展示。
5. Top 10 商品表，含排名、商品、类别、净营业额、订单数、营业额占比。
6. 明确的加载、接口错误和空数据状态。

前端只在用户提交日期筛选后请求 API。把 API 返回的原始数值保留在状态中，金额和百分比只在展示层格式化。使用人民币格式显示金额，但不要在前端重新计算核心指标。

图表、指标卡和表格必须使用同一个接口响应。不要为每个区域单独写不同的聚合逻辑。

## 7. 实施步骤

### 步骤 1：建立项目骨架和数据导入

- 创建 `backend/` 和 `frontend/` 的最小可运行项目。
- 将三份 `data/raw/*.csv` 纳入版本控制。
- 实现可重复执行的数据导入命令，例如 `python -m app.ingestion.load_data`。
- 建表、清洗、规范化、去重、左连接和审计计数。
- 用小型 CSV fixture 覆盖每一种脏数据规则。

完成标准：清空数据库后运行一次导入命令，能够生成数据库和审计记录；同一命令再次运行，结果不发生重复累加。

### 步骤 2：实现并验证看板 API

- 实现 `GET /api/v1/dashboard` 和 `GET /api/v1/health`。
- 将聚合查询放在服务层，路由层只负责参数校验和调用服务。
- 用 SQL 聚合计算指标。不要把全表读入 Python 后循环计算。
- 为默认范围、单日范围、空范围、非法范围、脏外键回退名称和负金额编写 API 测试。

完成标准：测试能证明汇总指标等于每日数据汇总；Top 10 数据按指定规则排序；空范围不会产生除零或前端错误。

### 步骤 3：实现看板界面

- 建立日期筛选、指标区、趋势图和 Top 10 表。
- 接入真实 API；开发中可以先用 fixture，但合并前必须移除 mock 数据路径。
- 对加载、错误、空数据和移动端布局做手动验证。
- 在浏览器中选择至少三个日期范围，对照 API JSON、指标卡、图表和表格。

完成标准：页面全部业务数字来自 API；用户修改日期范围后，三个区域同步更新。

### 步骤 4：补齐交付说明

- 更新根目录 `README.md`，写明三步启动命令、环境要求、架构图和数据口径。
- 写明原始数据来源与清洗规则。
- 写下暂未实现的第二关和第三关内容，不把它们伪装成已完成。

完成标准：新的评审者从空目录按 README 能启动项目，并能理解数字的来源。

## 8. 自动化测试和手动验收

最低自动化测试集合：

- 日期格式、货币符号、空金额、负金额、非正数量和外键格式的解析测试。
- 规范化后重复记录只保留一次的测试。
- 导入重复执行不会累加数据的测试。
- 固定 fixture 的营业额、订单数、客单价和 Top 10 排序测试。
- API 参数校验、空范围和 HTTP 错误响应测试。

手动验收清单：

- 选择完整范围、单日范围和无销售范围。
- 核对指标卡、图表和表格均使用同一份 API 响应。
- 核对负金额影响净营业额。
- 核对未匹配商品不会让页面崩溃或无故丢失营业额。
- 关闭后端或制造网络失败，确认页面显示可读错误状态。

## 9. Git 提交安排

不要为追求数量拆碎提交。第一关在已有初始化提交之后，只增加三次有意义的提交：

```text
docs: define dashboard data rules and implementation plan
feat(data): normalize source data and build reporting dataset
feat(dashboard): deliver dashboard api, interface and verification
```

第一笔文档提交记录在写代码前如何定义口径。第二笔提交包含原始 CSV、导入脚本、SQLite 模型和数据测试。第三笔提交包含 API、前端、API 测试、README 和最后验证。若开发中发现真实缺陷，再增加一笔针对问题的 `fix(...)` 提交，不要预先制造空提交。

这使第一关连同已有初始化提交共四次。后续第二关、第三关和最终文档各占一到两次提交时，整个仓库自然会形成八到十次有意义的提交。

## 10. 给执行 AI 的约束

- 先阅读本文件，再查看 `data/raw/` 的表头和样本。
- 一次只实现一个实施步骤，并在每个步骤后运行相关测试。
- 不要修改原始 CSV，不要提交数据库文件、`node_modules`、`dist`、虚拟环境或任何密钥。
- 不要为了完成页面而跳过清洗、测试或错误状态。
- 不要在第二关前加入模型 SDK、API key、聊天组件或自由文本 SQL。
- 当需求未说明时，按本文件的报表口径执行，并在 README 中记录该决定。
- 实现结束时报告：修改的文件、执行的测试、测试结果、尚未实现的内容和建议的下一次提交信息。
