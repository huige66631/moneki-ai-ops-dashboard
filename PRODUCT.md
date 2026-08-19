# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

推断：餐饮门店运营人员和区域负责人，在日常复盘或经营例会上快速查看营业表现、订单规模和商品贡献。

## Product Purpose

推断：将销售流水清洗成可追溯的经营报表，让使用者在一个页面内完成日期筛选、趋势判断和商品排行核对。成功标准是页面数字可由版本化 API 的同一份响应解释。

## Positioning

以真实 CSV 清洗规则和数据质量审计为基础的本地运营看板；脏数据不会被静默丢弃，异常记录的处理口径可被核对。

## Operating Context

本地开发环境，运营人员使用桌面浏览器为主，也需要在窄屏下正常阅读。原始数据位于 `data/raw/`，后端通过 SQLite 提供查询，前端只在提交日期范围后请求接口。

## Capabilities and Constraints

- 第一关只实现数据导入、看板 API、看板界面和验证，不接入模型 SDK、API key、聊天界面或自由文本 SQL。
- 指标包含净营业额、去重订单数、客单价、连续日期的每日营业额趋势和 Top 10 商品。
- 金额在后端使用整数分保存并在展示层格式化为人民币；负金额保留。
- 缺失金额、重复记录、无效数量和脏外键按 `docs/design/phase-1-dashboard/IMPLEMENTATION_PLAN.md` 的规则处理。

## Evidence on Hand

- `data/raw/sales.csv`
- `data/raw/stores.csv`
- `data/raw/products.csv`
- `docs/design/phase-1-dashboard/IMPLEMENTATION_PLAN.md`

## Product Principles

- 每个业务数字都能回到同一份 API 响应。
- 清洗规则可重复执行、可审计，不修改原始 CSV。
- 运营任务优先：先看状态，再筛选，再深入商品贡献。
- 异常数据要可解释，但不抢占主视觉。

## Accessibility & Inclusion

推断：保证键盘可操作、清晰焦点、正文和控件有足够对比度，移动窄屏下不依赖悬停才能获取信息。
