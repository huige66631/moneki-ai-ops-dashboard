import verifiedJson from '../data.json'

type Fact = { order: string | null; date: string | null; store: string | null; product: string | null; cents: number | null; amountValid: boolean; storeMatched: boolean; productMatched: boolean }
type Product = { id: string; name: string; category: string | null }
type Data = { facts: Fact[]; products: Map<string, Product>; stores: Map<string, string>; duplicateDates: string[]; invalidAmountDates: string[]; invalidDateCount: number; bounds: [string, string] }
type Intent = 'category_store_revenue' | 'product_revenue' | 'recent_average_order_value' | 'unsupported'
type DeepSeekPlan = { intent: Intent; product_name?: string }

const DEEPSEEK_PROXY_URL = 'https://tryrevive-d4gzac2aj49df4aa4.service.tcloudbase.com/api/deepseek'
const DEEPSEEK_PROXY_ORIGIN = 'https://moneki-dashboard-tryrevive-d4gzac2aj49df4aa4.webapps.tcloudbase.com'
const sessions = new Map<string, string>()
let loaded: Promise<Data> | undefined

function inRange(value: string | null, start: string, end: string) { return !!value && value >= start && value <= end }
function money(cents: number) { return Number((cents / 100).toFixed(2)) }
function average(cents: number, count: number) { return count ? Number((cents / count / 100).toFixed(2)) : null }
function dateList(start: string, end: string) { const result: string[] = []; for (let d = new Date(`${start}T00:00:00Z`); d <= new Date(`${end}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + 1)) result.push(d.toISOString().slice(0, 10)); return result }

async function data(): Promise<Data> {
  if (loaded) return loaded
  loaded = Promise.resolve().then(() => {
    const raw = verifiedJson as { facts: Array<Record<string, unknown>>; products: Array<{ id: string; name: string; category: string | null }>; stores: Array<{ id: string; category: string }>; duplicateDates: string[]; invalidAmountDates: string[]; invalidDateCount: number; bounds: [string, string] }
    return {
      facts: raw.facts.map(f => ({ order: f.order as string | null, date: f.date as string | null, store: f.store as string | null, product: f.product as string | null, cents: f.cents as number | null, amountValid: Boolean(f.amountValid), storeMatched: Boolean(f.storeMatched), productMatched: Boolean(f.productMatched) })),
      products: new Map(raw.products.map(p => [p.id, p])),
      stores: new Map(raw.stores.map(s => [s.id, s.category])),
      duplicateDates: raw.duplicateDates,
      invalidAmountDates: raw.invalidAmountDates,
      invalidDateCount: raw.invalidDateCount,
      bounds: raw.bounds,
    }
  })
  return loaded
}

function valid(d: Data, start: string, end: string) { return d.facts.filter(f => inRange(f.date, start, end) && !!f.order && f.amountValid) }
function dashboard(d: Data, start: string, end: string) {
  const facts = valid(d, start, end); const cents = facts.reduce((s, f) => s + (f.cents || 0), 0); const orders = new Set(facts.map(f => f.order)).size
  const daily = dateList(start, end).map(date => { const list = facts.filter(f => f.date === date); const value = list.reduce((s, f) => s + (f.cents || 0), 0); const count = new Set(list.map(f => f.order)).size; return { date, revenue: money(value), order_count: count, average_order_value: average(value, count) } })
  const byProduct = new Map<string, { cents: number; orders: Set<string | null> }>()
  for (const f of facts) { const key = f.product || 'UNKNOWN'; const item = byProduct.get(key) || { cents: 0, orders: new Set<string | null>() }; item.cents += f.cents || 0; item.orders.add(f.order); byProduct.set(key, item) }
  const top_products = [...byProduct.entries()].sort((a, b) => b[1].cents - a[1].cents || a[0].localeCompare(b[0])).slice(0, 10).map(([id, item], i) => { const p = d.products.get(id); return { rank: i + 1, product_id: id, product_name: p?.name || `未匹配商品 (${id})`, product_category: p?.category || null, revenue: money(item.cents), order_count: item.orders.size, revenue_share: cents ? Number((item.cents / cents).toFixed(4)) : 0 } })
  const scoped = d.facts.filter(f => inRange(f.date, start, end)); const countDays = dateList(start, end).length
  return { range: { start_date: start, end_date: end }, summary: { revenue: money(cents), order_count: orders, average_order_value: average(cents, orders), average_daily_revenue: Number((cents / 100 / countDays).toFixed(2)) }, daily, top_products, data_quality: { included_record_count: scoped.filter(f => !!f.order && f.amountValid).length, excluded_duplicate_count: d.duplicateDates.filter(x => inRange(x, start, end)).length, excluded_invalid_amount_count: d.invalidAmountDates.filter(x => inRange(x, start, end)).length, excluded_invalid_date_count: d.invalidDateCount, unmatched_store_count: scoped.filter(f => !f.storeMatched).length, unmatched_product_count: scoped.filter(f => !f.productMatched).length } }
}

function range(question: string, bounds: [string, string], context?: { start_date: string; end_date: string }): [string, string] {
  const full = [...question.matchAll(/(20\d{2})\s*(?:年\s*|[-/]\s*)(\d{1,2})\s*(?:月\s*|[-/]\s*)(\d{1,2})\s*[日号]?/g)]
  if (full.length) {
    const dates = full.map(match => `${match[1]}-${String(Number(match[2])).padStart(2, '0')}-${String(Number(match[3])).padStart(2, '0')}`)
    return [dates[0], dates[1] || dates[0]]
  }
  const numericMonth = question.match(/(20\d{2})\s*[年/-]\s*(\d{1,2})\s*月|(?<!\d)(\d{1,2})\s*月/)
  const chineseMonth = question.match(/(?:(20\d{2})\s*年\s*)?(十二|十一|十|[一二三四五六七八九])月/)
  const map: Record<string, number> = { 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9, 十: 10, 十一: 11, 十二: 12 }
  const month = numericMonth ? Number(numericMonth[2] || numericMonth[3]) : chineseMonth ? map[chineseMonth[2]] : undefined
  const year = numericMonth ? Number(numericMonth[1] || bounds[0].slice(0, 4)) : chineseMonth ? Number(chineseMonth[1] || bounds[0].slice(0, 4)) : undefined
  if (!month || !year) return context ? [context.start_date, context.end_date] : bounds
  const start = `${year}-${String(month).padStart(2, '0')}-01`; const end = new Date(Date.UTC(year, month, 0)).toISOString().slice(0, 10)
  return [start, end]
}

function asRecord(value: unknown): Record<string, unknown> | null { return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null }
function parsePlan(value: unknown): DeepSeekPlan {
  const record = asRecord(value); const intent = record?.intent
  if (intent !== 'category_store_revenue' && intent !== 'product_revenue' && intent !== 'recent_average_order_value' && intent !== 'unsupported') throw new Error('invalid_deepseek_plan')
  const productName = record?.product_name
  return { intent, ...(typeof productName === 'string' && productName.trim() ? { product_name: productName.trim() } : {}) }
}

async function deepseekPlan(question: string, context: { start_date: string; end_date: string } | undefined, bounds: [string, string], products: string[]): Promise<DeepSeekPlan> {
  const system = `你是 Moneki 销售看板的查询意图识别器。只输出 JSON，不要输出 Markdown 或解释。JSON 格式必须是 {"intent":"category_store_revenue|product_revenue|recent_average_order_value|unsupported","product_name":"商品名（仅 product_revenue 需要）"}。门店品类营业额对应 category_store_revenue；商品卖了多少钱/销售额对应 product_revenue；客单价趋势对应 recent_average_order_value；不相关问题对应 unsupported；product_name 必须从商品目录中原样选择。商品目录：${JSON.stringify(products)}`
  const payload = { question, dashboard_context: context || null, data_bounds: { start_date: bounds[0], end_date: bounds[1] } }
  const response = await fetch(DEEPSEEK_PROXY_URL, { method: 'POST', headers: { 'Content-Type': 'application/json', Origin: DEEPSEEK_PROXY_ORIGIN }, body: JSON.stringify({ system, messages: [{ role: 'user', content: JSON.stringify(payload) }], max_tokens: 256, response_format: { type: 'json_object' } }) })
  if (!response.ok) throw new Error('deepseek_request_failed')
  const body = asRecord(await response.json())
  const content = Array.isArray(body?.content) ? body.content[0] : null
  const contentRecord = asRecord(content); const text = contentRecord?.text
  if (typeof text !== 'string') throw new Error('invalid_deepseek_response')
  const match = text.match(/\{[\s\S]*\}/)
  if (!match) throw new Error('invalid_deepseek_plan')
  return parsePlan(JSON.parse(match[0]))
}

function findProduct(d: Data, question: string, plannedName?: string): Product | undefined {
  const direct = [...d.products.values()].find(p => question.includes(p.name)); if (direct) return direct
  if (plannedName) return [...d.products.values()].find(p => p.name === plannedName)
  return undefined
}

function sessionProductId(d: Data, sessionId: string | undefined) {
  const marker = sessionId?.match(/\|product=([^|]+)$/)?.[1]
  if (marker && d.products.has(marker)) return marker
  return sessionId ? sessions.get(sessionId) : undefined
}

function provider() { return { name: 'deepseek', mode: 'live' as const } }
function averageWindow(d: Data, start: string, end: string) {
  const facts = valid(d, start, end); const cents = facts.reduce((sum, f) => sum + (f.cents || 0), 0); const orders = new Set(facts.map(f => f.order)).size
  return { start_date: start, end_date: end, revenue: money(cents), order_count: orders, average_order_value: average(cents, orders) || 0 }
}
async function answer(d: Data, body: { question?: string; context?: { start_date: string; end_date: string }; session_id?: string }) {
  const id = (body.session_id || crypto.randomUUID()).split('|product=')[0]; const previousProduct = sessionProductId(d, body.session_id) ? d.products.get(sessionProductId(d, body.session_id) || '') : undefined; const question = String(body.question || '').trim(); const dates = range(question, d.bounds, body.context); const plan = await deepseekPlan(question, body.context, d.bounds, [...d.products.values()].map(p => p.name)); const followUp = Boolean(previousProduct && /(?:那|呢|他|它)/.test(question) && /(?:20\d{2}\s*[年/-]\s*)?\d{1,2}\s*月/.test(question)); const productFollowUp = followUp && /(?:卖了多少|营业额|销售额|卖了多少钱)/.test(question) && !/(?:哪个品类|品类|门店|客单价|趋势)/.test(question); const intent = productFollowUp || (plan.intent === 'unsupported' && followUp) ? 'product_revenue' : plan.intent; const product = findProduct(d, question, plan.product_name) || (intent === 'product_revenue' ? previousProduct : undefined)
  if (dates[0] < d.bounds[0] || dates[1] > d.bounds[1]) return { status: 'needs_clarification', answer: `当前数据仅覆盖 ${d.bounds[0]} 至 ${d.bounds[1]}，无法完整核对 ${dates[0]} 至 ${dates[1]} 的销售情况；这不代表该期间营业额为 0。`, intent: intent === 'unsupported' ? null : intent, session_id: id, provider: provider() }
  if (!question || question.length > 500) throw new Error('invalid_question')
  if (body.context && (!body.context.start_date || !body.context.end_date || body.context.start_date > body.context.end_date)) throw new Error('invalid_context')
  if (intent === 'product_revenue' && product) { const list = valid(d, dates[0], dates[1]).filter(f => f.product === product.id); const cents = list.reduce((s, f) => s + (f.cents || 0), 0); const orders = new Set(list.map(f => f.order)).size; sessions.set(id, product.id); return { status: 'answered', answer: `${dates[0]} 至 ${dates[1]}，${product.name}的净营业额是 ¥${money(cents).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}，共涉及 ${orders} 个订单。`, intent: 'product_revenue', session_id: `${id}|product=${product.id}`, tool_call: { name: 'get_product_revenue', arguments: { product_name: product.name, product_id: product.id, start_date: dates[0], end_date: dates[1] } }, evidence: { metric: 'revenue', unit: 'CNY', filters: { product_id: product.id, product_name: product.name, start_date: dates[0], end_date: dates[1] }, values: { revenue: money(cents), order_count: orders }, summary: '商品名称通过 products 表规范化匹配，查询使用商品 JOIN。' }, provider: provider(), navigation: { start_date: dates[0], end_date: dates[1], reason: 'answer_query_range' } } }
  if (intent === 'product_revenue') return { status: 'needs_clarification', answer: `我没有找到唯一的商品“${plan.product_name || question}”，请提供看板中的准确商品名称。`, intent: 'product_revenue', session_id: id, provider: provider() }
  if (intent === 'category_store_revenue') { const categories = new Map<string, { cents: number; orders: Set<string | null>; stores: Set<string | null> }>(); for (const f of valid(d, dates[0], dates[1])) { const category = d.stores.get(f.store || '') || '未分类'; const item = categories.get(category) || { cents: 0, orders: new Set<string | null>(), stores: new Set<string | null>() }; item.cents += f.cents || 0; item.orders.add(f.order); item.stores.add(f.store); categories.set(category, item) } const winner = [...categories.entries()].sort((a, b) => b[1].cents - a[1].cents)[0]; if (winner) return { status: 'answered', answer: `在 ${dates[0]} 至 ${dates[1]}，门店品类“${winner[0]}”的净营业额最高，为 ¥${money(winner[1].cents).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}，涉及 ${winner[1].orders.size} 个订单。`, intent: 'category_store_revenue', session_id: id, tool_call: { name: 'get_category_store_revenue', arguments: { start_date: dates[0], end_date: dates[1] } }, evidence: { metric: 'revenue', unit: 'CNY', filters: { start_date: dates[0], end_date: dates[1], category: winner[0] }, values: { revenue: money(winner[1].cents), order_count: winner[1].orders.size, store_count: winner[1].stores.size }, summary: `共返回 ${categories.size} 个门店品类，按净营业额降序。` }, provider: provider(), navigation: { start_date: dates[0], end_date: dates[1], reason: 'answer_query_range' } } }
  if (intent === 'recent_average_order_value') {
    if (dateList(dates[0], dates[1]).length < 14) return { status: 'needs_clarification', answer: '当前范围不足以比较两个完整的 7 天客单价窗口，请扩大日期范围。', intent: 'recent_average_order_value', session_id: id, provider: provider() }
    const recentEnd = new Date(`${dates[1]}T00:00:00Z`); const recentStart = new Date(recentEnd); recentStart.setUTCDate(recentStart.getUTCDate() - 6)
    const previousEnd = new Date(recentStart); previousEnd.setUTCDate(previousEnd.getUTCDate() - 1); const previousStart = new Date(previousEnd); previousStart.setUTCDate(previousStart.getUTCDate() - 6)
    const recent = averageWindow(d, recentStart.toISOString().slice(0, 10), recentEnd.toISOString().slice(0, 10)); const previous = averageWindow(d, previousStart.toISOString().slice(0, 10), previousEnd.toISOString().slice(0, 10)); const difference = Number((recent.average_order_value - previous.average_order_value).toFixed(2)); const direction = difference > 0 ? '上涨' : difference < 0 ? '下跌' : '持平'
    return { status: 'answered', answer: `最近 7 天（${recent.start_date} 至 ${recent.end_date}）客单价为 ¥${recent.average_order_value.toFixed(2)}；此前 7 天（${previous.start_date} 至 ${previous.end_date}）为 ¥${previous.average_order_value.toFixed(2)}，整体${direction} ¥${Math.abs(difference).toFixed(2)}。`, intent: 'recent_average_order_value', session_id: id, tool_call: { name: 'get_recent_average_order_value', arguments: { start_date: dates[0], end_date: dates[1] } }, evidence: { metric: 'average_order_value', unit: 'CNY', filters: { start_date: dates[0], end_date: dates[1], window_days: 7 }, values: { recent, previous, difference, change_percent: previous.average_order_value ? difference / previous.average_order_value : null, direction: difference > 0 ? 'up' : difference < 0 ? 'down' : 'flat' }, summary: '两个窗口均按净营业额除以去重订单数计算。' }, provider: provider(), navigation: { start_date: dates[0], end_date: dates[1], reason: 'answer_query_range' } }
  }
  return { status: 'unsupported', answer: '我只能回答销售流水、门店、商品、营业额、订单数和客单价相关问题。', session_id: id, provider: provider() }
}

function json(value: unknown, origin: string, status = 200) { return new Response(JSON.stringify(value), { status, headers: { 'content-type': 'application/json; charset=utf-8', 'access-control-allow-origin': origin, 'access-control-allow-methods': 'GET, POST, OPTIONS', 'access-control-allow-headers': 'Content-Type' } }) }

export default { async fetch(request: Request) { const origin = request.headers.get('Origin') || '*'; if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: { 'access-control-allow-origin': origin, 'access-control-allow-methods': 'GET, POST, OPTIONS', 'access-control-allow-headers': 'Content-Type' } }); const d = await data(); const url = new URL(request.url); if (request.method === 'GET' && url.pathname === '/') return json({ service: 'moneki-dashboard-api', docs: '/docs', provider: 'deepseek' }, origin); if (request.method === 'GET' && url.pathname === '/api/v1/health') return json({ status: 'ok', database_ready: true, provider: 'deepseek' }, origin); if (request.method === 'GET' && url.pathname === '/api/v1/dashboard') { const startParam = url.searchParams.get('start_date'); const endParam = url.searchParams.get('end_date'); if ((startParam === null) !== (endParam === null)) return json({ detail: 'start_date 和 end_date 必须同时提供。' }, origin, 422); const start = startParam || d.bounds[0]; const end = endParam || d.bounds[1]; return start > end ? json({ detail: 'start_date 不能晚于 end_date。' }, origin, 422) : json(dashboard(d, start, end), origin) } if (request.method === 'POST' && url.pathname === '/api/v1/assistant/ask') { try { const body = await request.json() as { question?: string; context?: { start_date: string; end_date: string }; session_id?: string }; const question = String(body.question || '').trim(); if (!question || question.length > 500) return json({ detail: 'question 不能为空且不能超过 500 个字符。' }, origin, 422); if (body.context && (!body.context.start_date || !body.context.end_date || body.context.start_date > body.context.end_date)) return json({ detail: 'context.start_date 不能晚于 context.end_date。' }, origin, 422); return json(await answer(d, body), origin) } catch (error) { return json({ detail: error instanceof Error && error.message === 'invalid_json' ? '请求格式无效。' : 'DeepSeek 查询暂时不可用，请稍后重试。' }, origin, error instanceof Error && error.message === 'invalid_json' ? 422 : 503) } } return json({ detail: 'Not Found' }, origin, 404) } }
