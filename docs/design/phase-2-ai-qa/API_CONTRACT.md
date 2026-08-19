# 第二关 API 和工具契约

## 1. 对话接口

新增接口：

```text
POST /api/v1/assistant/ask
Content-Type: application/json
```

请求体：

```json
{
  "question": "牛肉poke 六月卖了多少钱？",
  "context": {
    "start_date": "2026-05-01",
    "end_date": "2026-07-31"
  }
}
```

字段含义：

- `question` 是用户的自然语言问题，必填，去除首尾空白，长度限制为 1 到 500 个字符。
- `context` 是当前看板的筛选范围，属于路由上下文，不是数字来源。两个日期必须同时存在或同时省略。
- 如果问题包含明确日期，后端使用问题解析出的日期；没有明确日期时使用 `context`；两者都没有时使用数据库可用的完整日期范围。

成功响应：

```json
{
  "status": "answered",
  "answer": "2026 年 6 月，牛肉poke 的净营业额是 ¥12,345.00，共涉及 286 个订单。",
  "intent": "product_revenue",
  "tool_call": {
    "name": "get_product_revenue",
    "arguments": {
      "product_id": "P06",
      "start_date": "2026-06-01",
      "end_date": "2026-06-30"
    }
  },
  "evidence": {
    "metric": "revenue",
    "unit": "CNY",
    "filters": {
      "product_id": "P06",
      "product_name": "牛肉poke",
      "start_date": "2026-06-01",
      "end_date": "2026-06-30"
    },
    "values": {
      "revenue": 12345.0,
      "order_count": 286
    }
  },
  "provider": {
    "name": "mock",
    "mode": "mock"
  }
}
```

`answer` 可以由经过验证的后端回答渲染器生成。模型负责理解问题和选择工具，不能自行填写 `evidence.values`。金额在 API 中返回 JSON number，前端再格式化为人民币。

## 2. 状态和错误

### `answered`

工具成功返回了足够数据。`answer`、`tool_call` 和 `evidence` 都必须存在。

### `unsupported`

问题不属于当前数据能力，例如询问成本、利润、员工排班或天气。响应 HTTP 200，返回：

```json
{
  "status": "unsupported",
  "answer": "我只能回答销售流水、门店、商品、营业额、订单数和客单价相关问题。",
  "intent": null,
  "tool_call": null,
  "evidence": null,
  "provider": {"name": "mock", "mode": "mock"}
}
```

此状态不能带有看起来像真实查询结果的金额或数量。

### `needs_clarification`

问题可以归类，但日期、商品或门店不明确，或数据不足以完成比较。回答必须说明缺少什么，并提出一个具体的澄清问题。不能猜测商品或日期。

### `error`

模型服务超时、配置错误或数据库不可用。响应 HTTP 503，回答说明系统暂时不能完成查询，不暴露 API key、堆栈或内部提示词。

所有无效请求仍使用 FastAPI 的 HTTP 422，例如空问题、日期格式错误、只提供一个上下文日期或起始日大于结束日。

## 3. 三个允许的查询工具

工具的输入和输出使用 Pydantic 模型校验。工具函数只允许访问 `sales_facts`、`stores`、`products` 和数据质量相关表。

### `get_category_store_revenue`

用途：回答“哪个品类的门店营业额最高”等问题。

输入：`start_date`、`end_date`，均为 ISO 日期。

查询口径：`sales_facts.store_id = stores.store_id` 左连接门店表，按 `stores.category` 汇总有效销售记录的净营业额，按营业额降序、品类名称升序排序。

输出：

```json
{
  "rows": [
    {
      "category": "轻食",
      "revenue": 50000.0,
      "order_count": 1200,
      "store_count": 1
    }
  ],
  "winner": {
    "category": "轻食",
    "revenue": 50000.0,
    "order_count": 1200,
    "store_count": 1
  },
  "filters": {"start_date": "2026-05-01", "end_date": "2026-07-31"}
}
```

这里的“品类”明确指门店维表中的 `stores.category`，不是商品维表中的 `products.product_category`。

### `get_product_revenue`

用途：回答“牛肉poke 六月卖了多少钱”等问题。

输入：已解析的 `product_id`、`start_date`、`end_date`。模型不直接传未经解析的商品名作为 SQL 片段。

查询口径：`sales_facts.product_id = products.product_id` 左连接商品表，汇总有效金额和去重订单数。商品 ID 不存在时返回“未匹配商品”，不能静默换成其他商品。

输出：商品身份、商品类别、净营业额、订单数和筛选日期。商品名称解析由后端的规范化匹配器完成，支持大小写、空格和中英文标点差异；多个候选时返回 `needs_clarification`。

成功结果至少包含以下字段：

```json
{
  "product": {
    "product_id": "P06",
    "product_name": "牛肉poke",
    "product_category": "主食",
    "matched": true
  },
  "revenue": 12345.0,
  "order_count": 286,
  "filters": {
    "start_date": "2026-06-01",
    "end_date": "2026-06-30"
  }
}
```

如果商品 ID 不存在，工具返回 `matched: false` 和可供回答渲染器使用的身份信息，不返回伪造的营业额。

### `get_recent_average_order_value`

用途：回答“客单价最近是涨了还是跌了”等问题。

输入：`start_date`、`end_date`，以及固定的 `window_days=7`。

查询口径：把所选范围末尾的 7 个自然日作为最近窗口，把紧接着的前 7 个自然日作为对比窗口。两个窗口都按“净营业额 / 去重订单数”计算客单价。范围不足 14 个自然日或任一窗口没有订单时，返回 `insufficient_data`，不要编造方向。

输出：两个窗口的起止日期、客单价、订单数、净营业额、差额、变化百分比和 `up`、`down`、`flat` 或 `insufficient_data` 方向。`insufficient_data` 时数值可以为 `null`，回答渲染器必须说明数据不足。

## 4. 工具调用流程

```text
看板日期范围 + 用户问题
  -> 请求校验和日期解析
  -> 提供商只选择一个允许的工具及结构化参数
  -> 后端校验工具名和参数
  -> 查询服务执行参数化 SQL
  -> 结果校验和证据对象生成
  -> 后端根据证据生成回答
  -> 页面展示回答、查询范围和证据
```

模型不能跳过工具直接返回数字。最终回答渲染器只能读取工具结果，禁止读取原始 CSV、环境变量或模型的自由文本数字。
