# 第三关：让 AI 数据问答可信的实施计划

## 1. 目标和选择理由

第三关是可选加分项。当前项目已经有真实数据查询、证据展示和单轮 AI 问答，因此最有价值的下一步是让使用者连续追问，让每次回答能驱动看板检查，并用测试证明数字不会漂移。

本计划实现以下三项：

1. 多轮追问：支持“牛肉poke 六月卖了多少钱？”后继续问“那五月呢？”。
2. 自动化数字一致性测试：证明 AI 证据和数据库独立计算的数字一致。
3. 图表联动：用户可将看板切换到 AI 实际查询的日期范围。

流式输出和线上部署不纳入当前核心范围。它们可以改善体验，但不能替代回答真实和可复核。

## 2. 当前基础和限制

第二关的 `POST /api/v1/assistant/ask` 已经使用白名单工具和确定性回答渲染器。`AssistantResponse` 包含 `tool_call` 和 `evidence`，前端 AssistantPanel 会显示查询依据。

当前 AssistantPanel 在日期范围变化时清空回答，后端没有 `session_id`。因此“那五月呢？”缺少可验证的指代对象，看板也无法可靠地知道 AI 查询了哪个范围。

第三关必须扩展既有契约，不改变第一关的金额、订单数、客单价和数据清洗口径。

## 3. 范围和非目标

### 本阶段范围

- 服务端短期会话状态和日期替换型追问。
- 回答响应中的 `session_id` 和 `navigation`。
- 前端消息保留、查看查询范围按钮和统一 dashboard 加载。
- 后端数字一致性测试矩阵和前端构建验证。
- README、`AI_USAGE.md` 和 `DEMO.md` 的第三关说明与演示步骤。

### 本阶段非目标

- 通用长对话记忆、数据库持久化消息、账户登录或跨设备会话。
- 模型自由生成 SQL、自由生成数字或自动执行任意函数。
- 门店筛选看板、因为当前三个 AI 意图不会产生唯一门店 ID。
- 流式 token 输出、WebSocket、服务端推送和生产级队列。
- 云部署、域名、用户数据上传或 CI 密钥配置。

## 4. 后端设计

### 4.1 会话存储

新增 `backend/app/ai/session_store.py`。实现受锁保护的进程内 `ConversationStore`，供 FastAPI 的单进程本地演示使用。

它需要提供：

- `get_or_create(session_id: str | None) -> ConversationState`
- `record_answered(session_id, intent, tool_name, arguments) -> ConversationState`
- `touch(session_id) -> ConversationState | None`
- 过期和 100 会话容量淘汰

测试通过可注入时钟或明确的 `now` 参数验证 30 分钟过期和容量淘汰。不要在会话中存储 API key、完整提供商响应、原始 CSV 行或自由文本 SQL。

### 4.2 追问规划

在 provider 选择工具之前，新增纯函数 `resolve_turn(question, request_context, previous_state, bounds)`：

1. 判断问题是否是可支持的日期替换型追问。
2. 从问题解析明确日期范围。
3. 验证上一轮 `last_successful_intent` 和 `last_tool_arguments`。
4. 生成继承对象后的 `ToolCallPlan`，或返回需要澄清的结果。
5. 对非追问不改变第二关 provider 流程。

`resolve_turn` 不执行数据库查询，也不根据自然语言猜测商品 ID。对于商品追问，它继承上一轮经过产品解析的 `product_name`，然后仍通过第二关的 `resolve_product` 验证商品身份。

### 4.3 编排器和响应模型

- `AskRequest` 新增可选 `session_id`，验证 UUID 格式。
- `AssistantResponse` 新增 `session_id` 和可选 `navigation` Pydantic 模型。
- 在 `answered` 路径中，从实际 `start_date`、`end_date` 和工具参数生成导航指令。
- 成功执行后再调用 `record_answered`。失败、拒答或澄清不能写入新的上一轮状态。
- 旧客户端未传 `session_id` 时创建新会话，行为仍保持单轮兼容。
- `POST /api/v1/assistant/ask` 在返回 503 时仍不得泄露内部错误；仅在响应模型允许时返回会话 ID。

### 4.4 保持可信度的约束

- 会话状态只能继承已验证的结构化工具参数，不能继承模型的自然语言答案。
- `navigation` 只来自实际执行的工具参数，不能由 provider 返回或由回答文本解析。
- 回答的金额和订单数继续由确定性渲染器填入。
- 会话失效时要求澄清，不使用最近系统日期或任意商品作为猜测。

## 5. 前端设计

### 5.1 AssistantPanel 状态

新增状态：`sessionId`、`pinnedResponse` 和 `navigationStatus`。

- 首次回答后保存 API 返回的 `session_id`，之后每次提问都回传。
- 日期筛选发生普通变化时，保留最后回答并标注其原始查询范围，不再无条件清空。
- 用户点击“查看此范围”时，通过 `onNavigate` 通知 App；不要在 AssistantPanel 内直接请求 `/dashboard`。
- App 成功加载新范围后设置 `navigationStatus`，AssistantPanel 显示一次性确认文案。
- 用户开始新问题时可以保留前一答案到新响应到达，避免视觉闪烁；请求失败则保留前一答案并显示错误。

### 5.2 App 统一加载

App 新增 `navigateFromAssistant(navigation)`：

1. 更新 `draftStart` 和 `draftEnd`。
2. 调用现有 `load(navigation.start_date, navigation.end_date)`。
3. 仅当请求成功后更新当前范围和确认状态。
4. 保持图表、指标和 Top 10 表使用同一 dashboard API 响应。

当前 `store_id` 始终为 `null`。接口契约提前保留字段，不在本阶段新增无使用场景的门店筛选控件。

### 5.3 交互和可访问性

- “查看此范围”是带文字的按钮，并包含明确日期的 aria-label。
- 当前回答清楚显示其查询范围；看板范围不同时，不能用“当前范围”误导用户。
- 加载期间禁用重复导航；失败时保留已加载看板和回答。
- 窄屏下按钮换行，回答和证据不溢出。

## 6. 自动化测试设计

### 6.1 会话与追问测试

- 初次商品问题返回 UUID `session_id`、真实工具调用和导航范围。
- 使用相同 `session_id` 发送“那五月呢？”时，继承商品，范围替换为 2026-05-01 到 2026-05-31。
- 无会话、过期会话或上一轮未成功时，“那五月呢？”返回 `needs_clarification`，没有证据、工具调用或导航。
- 新问题包含另一个商品名时，不继承上一轮商品。
- `unsupported` 和 provider 失败不会覆盖上一轮成功状态。
- 会话淘汰和应用重启后的行为有明确单元测试。

### 6.2 数字一致性回归矩阵

新增 `backend/tests/test_ai_numeric_consistency.py`，使用一组固定问题和固定日期：

| 场景 | AI 问题 | 独立期望来源 | 必须断言 |
| --- | --- | --- | --- |
| 门店品类冠军 | 哪个品类的门店营业额最高？ | 独立 JOIN `stores` 的参数化 SQL | 品类、营业额、订单数、答案金额 |
| 指定商品月份 | 牛肉poke 六月卖了多少钱？ | 独立 JOIN `products` 的参数化 SQL | 商品、营业额、订单数、日期边界、答案金额 |
| 客单价趋势 | 客单价最近是涨了还是跌了？ | 独立计算两个 7 天窗口 | 两个客单价、差额、方向、答案金额 |
| 负金额 | 包含退款的商品或日期范围问题 | 独立净额 SQL | 负金额被保留且答案一致 |
| 空数据 | 无销售日期范围 | dashboard 服务与零值规则 | 不生成虚假金额或趋势 |

期望计算不能调用 `get_category_store_revenue`、`get_product_revenue` 或 `get_recent_average_order_value`。测试必须能捕获工具实现和回答渲染同时偏离口径的情况。

### 6.3 API 和前端验证

- 旧版无 `session_id` 请求仍返回正常单轮回答。
- 无效 UUID、超长问题和导航字段伪造被 HTTP 422 或服务器忽略。
- `navigation` 范围等于 `tool_call.arguments` 的实际起止日期。
- 运行 `pytest -q` 与 `npm run build`。
- 手动测试完整三问、五月追问、无上下文追问、日期联动、错误和窄屏。

## 7. 实施顺序

### 步骤 1：确定会话和导航契约

- 实现 API 模型、session store 和纯函数追问解析。
- 添加会话过期、无上下文澄清和工具参数继承测试。
- 确保单轮接口兼容。

完成标准：不依赖浏览器或真实 provider，后端能安全处理“那五月呢？”。

### 步骤 2：完成独立数字一致性测试

- 编写独立 SQL 或 dashboard 服务对照计算。
- 添加五类数值回归矩阵，验证 API、证据和回答文本。
- 先让测试失败一次，确认它能抓到故意改错的金额或日期边界，再恢复正确实现。

完成标准：测试清晰证明 AI 数字等于独立数据库计算，并且全套后端测试通过。

### 步骤 3：实现看板联动

- 扩展 AssistantPanel 类型、状态和“查看此范围”按钮。
- 将导航回调接入 App 的统一加载流程。
- 保留回答证据和查询范围，完成响应式样式。
- 在浏览器验证日期控件、三项指标、趋势图和 Top 10 同步变化。

完成标准：用户点击一次后，看板切到 AI 的真实查询范围，并可从响应和页面确认一致。

### 步骤 4：完成交付材料

- 更新根目录 README，说明第三关实现范围和本地内存会话限制。
- 更新 `AI_USAGE.md`，如实记录用于规划、代码和测试的 AI 协作过程，以及发现和修复的一个实际问题。
- 新增 `DEMO.md`，给出 1 到 3 分钟演示脚本：首问、五月追问、证据展开、点击联动、运行测试。
- 更新三个 phase 的 `status.md`，确保实现状态一致。

完成标准：陌生评审者可按 README 启动项目，并按 DEMO.md 重现可信度证明。

## 8. Git 提交安排

第三关在已有第二关提交之后使用两次提交即可：

```text
feat(trust): add follow-up context and answer verification suite
feat(trust): link verified answers to dashboard ranges
```

第一笔包含会话契约、session store、追问编排、独立数字一致性测试和后端文档。第二笔包含前端联动、README、`AI_USAGE.md`、`DEMO.md` 和浏览器验证。若测试实际发现并修复缺陷，单独增加 `fix(trust): ...`，不要为凑数量拆分代码。

## 9. 可选扩展

只有上述三项稳定后，才考虑以下任一项：

- 流式输出：仅流式传输后端已经验证的回答片段，不流式输出未经工具验证的模型数字；使用 SSE 并为断线重连、取消和完整响应落盘编写测试。
- 部署：使用环境变量注入密钥，限制 CORS，提供健康检查和部署说明；上线前不上传真实用户数据或密钥。
- 门店对比：先扩展 dashboard 的 `store_id` 筛选契约和测试，再让新的 AI 查询工具生成带门店 ID 的导航指令。

## 10. 给执行 AI 的约束

- 先阅读本目录和第二关实现，再修改代码。
- 不要跳过独立数字一致性测试，不要让测试期望复用同一查询工具函数。
- 不要把会话消息、API key、完整 provider 响应或模型提示词写进 SQLite 或浏览器本地存储。
- 不要让前端从回答文本解析日期，也不要让模型返回导航范围。
- 不要自动跳转看板范围，必须由用户触发“查看此范围”。
- 不要为了通过追问演示而预置某个商品、月份或金额。
- 实现结束时报告修改文件、测试命令、测试结果、会话限制、未完成扩展和建议的下一次提交信息。
