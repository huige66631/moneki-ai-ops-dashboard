import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import { AlertCircle, ArrowDownRight, ArrowUpRight, CalendarDays, ChevronDown, CircleHelp, RefreshCw } from 'lucide-react'
import { Dashboard, fetchDashboard } from './lib/api'
import { AssistantPanel } from './features/assistant/AssistantPanel'
import { AssistantNavigation } from './features/assistant/assistantTypes'

const money = new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY', maximumFractionDigits: 0 })
const moneyExact = new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY', minimumFractionDigits: 2, maximumFractionDigits: 2 })
const number = new Intl.NumberFormat('zh-CN')
const percent = new Intl.NumberFormat('zh-CN', { style: 'percent', maximumFractionDigits: 1 })
const todayLabel = new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date()).replaceAll('/', '.')

function formatDateRange(start: string, end: string) {
  return `${start.replaceAll('-', '.')} — ${end.replaceAll('-', '.')}`
}

function App() {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null)
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [draftStart, setDraftStart] = useState('')
  const [draftEnd, setDraftEnd] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [rangeError, setRangeError] = useState('')
  const [navigationStatus, setNavigationStatus] = useState('')
  const requestController = useRef<AbortController | null>(null)

  const load = useCallback(async (nextStart?: string, nextEnd?: string): Promise<Dashboard | null> => {
    requestController.current?.abort()
    const controller = new AbortController()
    requestController.current = controller
    setLoading(true)
    setError('')
    try {
      const nextDashboard = await fetchDashboard(nextStart, nextEnd, controller.signal)
      setDashboard(nextDashboard)
      setStartDate(nextDashboard.range.start_date)
      setEndDate(nextDashboard.range.end_date)
      setDraftStart(nextDashboard.range.start_date)
      setDraftEnd(nextDashboard.range.end_date)
      return nextDashboard
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return null
      setError(err instanceof Error ? err.message : '接口暂时不可用。')
      return null
    } finally {
      if (!controller.signal.aborted) setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
    return () => requestController.current?.abort()
  }, [load])

  const apply = (event: React.FormEvent) => {
    event.preventDefault()
    if (!draftStart || !draftEnd) {
      setRangeError('请选择起始日期和结束日期。')
      return
    }
    if (draftStart > draftEnd) {
      setRangeError('起始日期不能晚于结束日期。')
      return
    }
    setRangeError('')
    void load(draftStart, draftEnd)
  }

  const navigateFromAssistant = useCallback(async (navigation: AssistantNavigation) => {
    setNavigationStatus('')
    setDraftStart(navigation.start_date)
    setDraftEnd(navigation.end_date)
    const nextDashboard = await load(navigation.start_date, navigation.end_date)
    if (nextDashboard) setNavigationStatus('看板已按 AI 查询范围更新。')
  }, [load])

  useEffect(() => {
    if (!navigationStatus) return
    const timer = window.setTimeout(() => setNavigationStatus(''), 4500)
    return () => window.clearTimeout(timer)
  }, [navigationStatus])

  const chartOption = useMemo(() => {
    const daily = dashboard?.daily ?? []
    return {
      animationDuration: 500,
      grid: { top: 28, right: 18, bottom: 28, left: 12, containLabel: true },
      tooltip: { trigger: 'axis', backgroundColor: '#1d2421', borderWidth: 0, textStyle: { color: '#fcfbf8' }, formatter: (items: Array<{ axisValue: string; data: number }>) => `${items[0].axisValue}<br/><strong>${moneyExact.format(items[0].data)}</strong>` },
      xAxis: { type: 'category', boundaryGap: false, data: daily.map(point => point.date.slice(5).replace('-', '/')), axisLine: { lineStyle: { color: '#d8d4cb' } }, axisLabel: { color: '#68716b', fontSize: 11, interval: Math.max(0, Math.floor(daily.length / 8) - 1) } },
      yAxis: { type: 'value', splitNumber: 4, axisLabel: { color: '#68716b', fontSize: 11, formatter: (value: number) => `¥${Math.round(value / 1000)}k` }, splitLine: { lineStyle: { color: '#e7e3db' } } },
      series: [{ type: 'line', smooth: 0.18, showSymbol: false, data: daily.map(point => point.revenue), lineStyle: { color: '#d94f3d', width: 3 }, areaStyle: { color: 'rgba(217,79,61,.08)' }, emphasis: { focus: 'series' } }],
    }
  }, [dashboard])

  return <div className="app-shell">
    <header className="topbar"><div className="brand-mark"><span className="brand-dot" /> MONEKI <span className="brand-divider">/</span> OPS</div><div className="topbar-meta"><span className="live-dot" /> 数据已同步 <span className="meta-separator" /> {todayLabel}</div></header>
    <main className="workspace" aria-busy={loading}>
      <section className="intro"><div><p className="kicker">DAILY OPERATING LEDGER</p><h1>经营看板</h1><p className="intro-copy">把营业流水变成今天可以行动的判断。</p></div><div className="range-stamp"><span>当前查看范围</span><strong>{dashboard ? formatDateRange(dashboard.range.start_date, dashboard.range.end_date) : '加载中'}</strong></div></section>
      <form className="filter-bar" onSubmit={apply} noValidate><div className="filter-label"><CalendarDays size={17} strokeWidth={1.7} /><span>筛选日期</span></div><label>起始日期<input type="date" value={draftStart} aria-invalid={Boolean(rangeError)} onChange={e => { setDraftStart(e.target.value); setRangeError('') }} /></label><span className="date-arrow" aria-hidden="true">→</span><label>结束日期<input type="date" value={draftEnd} aria-invalid={Boolean(rangeError)} onChange={e => { setDraftEnd(e.target.value); setRangeError('') }} /></label><button type="submit" disabled={loading}><span>{loading ? '更新中' : '应用筛选'}</span>{loading ? <RefreshCw size={15} className="spin" aria-hidden="true" /> : <ArrowUpRight size={15} aria-hidden="true" />}</button>{rangeError && <p className="range-error" role="alert">{rangeError}</p>}</form>
      <AssistantPanel startDate={startDate || undefined} endDate={endDate || undefined} navigating={loading} navigationStatus={navigationStatus} onNavigate={navigateFromAssistant} />
      {error ? <div className="state-panel error-state" role="alert"><AlertCircle size={20} aria-hidden="true" /><div><strong>暂时无法读取看板</strong><p>{error}</p></div><button type="button" onClick={() => void load(startDate || undefined, endDate || undefined)}><RefreshCw size={15} aria-hidden="true" /> 重试</button></div> : <>
        <section className="metrics" aria-label="关键指标"><Metric label="净营业额" value={dashboard ? money.format(dashboard.summary.revenue) : '—'} note="所选范围累计" accent /><Metric label="订单数" value={dashboard ? number.format(dashboard.summary.order_count) : '—'} note="去重订单" /><Metric label="客单价" value={dashboard?.summary.average_order_value == null ? '—' : money.format(dashboard.summary.average_order_value)} note="营业额 ÷ 订单数" /></section>
        <section className="evidence-grid"><div className="panel trend-panel"><div className="panel-heading"><div><p className="panel-kicker">01 / FLOW</p><h2>每日营业额</h2></div><div className="heading-note"><span className="legend-line" />净营业额</div></div>{loading && !dashboard ? <div className="chart-placeholder" role="status">正在整理每日流水…</div> : dashboard?.daily.every(point => point.revenue === 0) ? <div className="empty-state"><CircleHelp size={22} aria-hidden="true" /><span>这个日期范围暂无有效营业额。</span></div> : <ReactECharts option={chartOption} style={{ height: 288, width: '100%' }} notMerge lazyUpdate />}</div><aside className="panel readout-panel"><div className="panel-heading"><div><p className="panel-kicker">READOUT</p><h2>范围摘要</h2></div><ChevronDown size={17} className="muted-icon" aria-hidden="true" /></div><div className="readout-list"><div><span>覆盖天数</span><strong>{dashboard ? dashboard.daily.length : '—'} <small>天</small></strong></div><div><span>日均营业额</span><strong>{dashboard ? money.format(dashboard.summary.average_daily_revenue) : '—'}</strong></div><div><span>高峰日</span><strong>{dashboard?.daily.length ? dashboard.daily.reduce((peak, point) => point.revenue > peak.revenue ? point : peak, dashboard.daily[0]).date.slice(5).replace('-', '/') : '—'}</strong></div></div><div className="readout-foot"><span className="pulse-icon" /> 包含无销售日期，以 ¥0 计入趋势</div></aside></section>
        <section className="panel products-panel"><div className="panel-heading products-heading"><div><p className="panel-kicker">02 / CONTRIBUTION</p><h2>Top 10 商品</h2><p className="section-subtitle">按净营业额排序 · 并列时按商品编号升序</p></div><div className="table-total">{dashboard ? `${dashboard.top_products.length} 个品项` : '—'}</div></div>{dashboard && dashboard.top_products.length ? <div className="table-wrap"><table><thead><tr><th className="rank-col">排名</th><th>商品</th><th>类别</th><th className="num-col">净营业额</th><th className="num-col">订单数</th><th className="num-col">营业额占比</th></tr></thead><tbody>{dashboard.top_products.map(item => <tr key={item.product_id}><td className="rank-col"><span className={item.rank <= 3 ? 'rank top-rank' : 'rank'}>{String(item.rank).padStart(2, '0')}</span></td><td><strong>{item.product_name}</strong><span className="product-id">{item.product_id}</span></td><td><span className="category-tag">{item.product_category || '未分类'}</span></td><td className="num-col amount">{moneyExact.format(item.revenue)}</td><td className="num-col">{number.format(item.order_count)}</td><td className="num-col share"><span className="share-track"><i style={{ width: `${Math.min(100, item.revenue_share * 100 * 3)}%` }} /></span>{percent.format(item.revenue_share)}</td></tr>)}</tbody></table></div> : <div className="empty-state table-empty"><CircleHelp size={22} aria-hidden="true" /><span>这个日期范围暂无可排行的商品。</span></div>}</section>
        {dashboard && <details className="quality-details"><summary><span>数据质量审计</span><span className="quality-summary">{number.format(dashboard.data_quality.included_record_count)} 条纳入报表 <ChevronDown size={16} aria-hidden="true" /></span></summary><div className="quality-grid"><span>重复排除 <strong>{number.format(dashboard.data_quality.excluded_duplicate_count)}</strong></span><span>金额无效 <strong>{number.format(dashboard.data_quality.excluded_invalid_amount_count)}</strong></span><span>日期无效（导入） <strong>{number.format(dashboard.data_quality.excluded_invalid_date_count)}</strong></span><span>未匹配门店 <strong>{number.format(dashboard.data_quality.unmatched_store_count)}</strong></span><span>未匹配商品 <strong>{number.format(dashboard.data_quality.unmatched_product_count)}</strong></span></div></details>}
      </>}
    </main><footer className="footer"><span>MONEKI / PHASE 01</span><span>数字来自同一份 dashboard API 响应</span></footer>
  </div>
}

function Metric({ label, value, note, accent }: { label: string; value: string; note: string; accent?: boolean }) { return <div className={`metric ${accent ? 'metric-accent' : ''}`}><div className="metric-label"><span>{label}</span>{accent ? <ArrowUpRight size={15} aria-hidden="true" /> : <ArrowDownRight size={15} aria-hidden="true" />}</div><strong>{value}</strong><span className="metric-note">{note}</span></div> }

export default App
