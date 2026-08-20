# 第三关 API 和状态契约

## 1. 扩展 AI 提问请求

扩展现有接口，保持原有调用方式可用：

```text
POST /api/v1/assistant/ask
```

新增可选字段：

```json
{
  "question": "那五月呢？",
  "context": {
    "start_date": "2026-05-01",
    "end_date": "2026-07-31"
  },
  "session_id": "5ebc0c5e-8f50-4b53-b65a-f4eb6b57a8d0"
}
```

- `session_id` 是后端首次收到问题时生成的 UUID，由浏览器在同一页面会话内回传；旧客户端不传该字段仍可获得一次新的单轮会话。
- 客户端不能提交上一轮工具参数、证据值或回答文本来替代 `session_id`。
- 未提供、过期或未知的 `session_id` 不报错。系统将问题按单轮问题处理；无法独立理解时返回 `needs_clarification`。
- 当前看板 `context` 仍提供默认日期范围。问题里明确日期优先于 `context` 和上一轮日期。

## 2. 扩展 AI 回答响应

所有回答都新增 `session_id`。只有 `answered` 状态可以返回 `navigation`：

```json
{
  "status": "answered",
  "answer": "2026-05-01 至 2026-05-31，牛肉poke 的净营业额是 ¥8,000.00。",
  "intent": "product_revenue",
  "session_id": "5ebc0c5e-8f50-4b53-b65a-f4eb6b57a8d0",
  "tool_call": {
    "name": "get_product_revenue",
    "arguments": {
      "product_name": "牛肉poke",
      "start_date": "2026-05-01",
      "end_date": "2026-05-31"
    }
  },
  "evidence": {},
  "navigation": {
    "start_date": "2026-05-01",
    "end_date": "2026-05-31",
    "store_id": null,
    "reason": "answer_query_range"
  },
  "provider": {"name": "mock", "mode": "mock"}
}
```

字段规则：

- `session_id` 为 UUID 字符串。`answered`、`unsupported` 和 `needs_clarification` 返回当前会话 ID，便于浏览器保持连续对话；provider 或工具错误继续使用 HTTP 503 的安全错误响应，不暴露内部细节。
- `navigation.start_date` 和 `navigation.end_date` 必须等于实际执行工具的日期参数，不能来自模型回答文本。
- `navigation.store_id` 当前为 `null`。后续增加门店筛选工具后才允许传入真实门店 ID。
- `reason` 目前固定为 `answer_query_range`，用于前端可读状态和测试断言。
- `tool_call`、`evidence` 或工具执行失败时，`navigation` 必须是 `null`。

## 3. 会话状态模型

服务端维护以下最小状态，键是 `session_id`：

```text
ConversationState(
  session_id,
  last_successful_intent,
  last_tool_name,
  last_tool_arguments,
  updated_at,
  expires_at
)
```

- 只在 `answered` 后更新 `last_*` 字段。
- `unsupported`、`needs_clarification` 和 `error` 不能覆盖已验证的上一轮状态。
- 每次读取或更新会话都刷新 `expires_at` 为当前时间加 30 分钟。
- 存储最多保留 100 个会话。超过时删除最早过期或最久未更新状态。
- 应用重启后会话状态丢失属于已知限制。页面收到 `needs_clarification` 后提示用户重新说明对象，不伪造上下文。

## 4. 追问解析规则

最小可交付版本只支持“继承对象并改变日期”的追问。追问必须带有效 `session_id`，且上一轮是 `answered`：

| 上一轮意图 | 追问示例 | 复用内容 | 新内容 |
| --- | --- | --- | --- |
| `product_revenue` | 那五月呢？ | 商品名称和工具 | 2026-05-01 至 2026-05-31 |
| `category_store_revenue` | 那六月呢？ | 工具和“门店品类”语义 | 2026-06-01 至 2026-06-30 |
| `recent_average_order_value` | 那五月呢？ | 工具和 7 天窗口规则 | 2026-05-01 至 2026-05-31 |

解析优先级：

1. 问题明确写出的日期范围或月份。
2. 有效会话的上一轮对象或意图。
3. 当前看板 `context`。

“那五月呢？”没有可解析月份、没有有效会话，或上一轮不是成功答案时，必须返回 `needs_clarification`，例如“你想查询哪种商品、门店品类或指标的五月数据？”

如果追问包含新的商品、品类或指标词，则把它当作新的独立问题，不继承上一轮对象。金额、营业额、销售额和订单数这类泛查询词本身不代表新对象，例如“那五月营业额是多少？”仍继承已验证的商品。

## 5. 图表联动接口

前端无需新增 HTTP 接口。`AssistantPanel` 接收：

```ts
onNavigate?: (navigation: {
  start_date: string
  end_date: string
  store_id: string | null
  reason: 'answer_query_range'
}) => void
```

调用规则：

- 收到 `answered` 且 `navigation` 的范围与当前看板范围不同时，AssistantPanel 显示“查看此范围”按钮。
- 用户点击后，`App` 更新日期输入、调用既有 `fetchDashboard`，并把趋势图和商品表切到相同范围。
- 切换完成后，页面显示“看板已按 AI 查询范围更新”的简短状态。
- AssistantPanel 不自行调用 dashboard API，仍由 `App` 统一加载，避免数字来源分叉。
- 不清除已回答消息或证据。该消息标注它对应的查询范围，直到用户发送下一条问题。

显式点击优于自动跳转，可以防止用户在查看一个范围时被仅作比较的 AI 回答打断。

## 6. 数字一致性测试契约

测试矩阵中的每一项都必须执行以下三条独立路径：

```text
固定问题和日期范围
  -> POST /api/v1/assistant/ask
  -> AssistantResponse.evidence.values

固定日期范围
  -> dashboard 服务或明确的参数化 SQL
  -> 独立期望值

比较
  -> 工具证据值等于独立期望值
  -> 回答文本含有正确格式化的核心金额或客单价
```

测试不能从同一个工具函数取得“期望值”，否则无法发现工具和回答同时出错。每个期望值必须由 dashboard 服务、独立参数化 SQL，或固定且人工核对过的 fixture 聚合生成。
