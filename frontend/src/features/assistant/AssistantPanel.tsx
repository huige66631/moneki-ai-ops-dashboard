import { FormEvent, useEffect, useRef, useState } from 'react'
import { AlertCircle, ArrowUpRight, CalendarDays, Check, ChevronDown, MessageSquare, RefreshCw } from 'lucide-react'
import { askAssistant } from './assistantApi'
import { AssistantNavigation, AssistantResponse } from './assistantTypes'

const examples = ['哪个品类的门店营业额最高？', '牛肉poke 六月卖了多少钱？', '客单价最近是涨了还是跌了？']

type Props = {
  startDate?: string
  endDate?: string
  navigating?: boolean
  navigationStatus?: string
  onNavigate?: (navigation: AssistantNavigation) => void
}

const evidenceLabels: Record<string, string> = {
  revenue: '净营业额',
  order_count: '订单数',
  store_count: '门店数',
  difference: '变化额',
  change_percent: '变化比例',
  direction: '方向',
  average_order_value: '客单价',
  start_date: '开始日期',
  end_date: '结束日期',
}

const moneyEvidenceKeys = new Set(['revenue', 'average_order_value', 'difference'])

function formatEvidenceValue(key: string, value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (key === 'direction') return ({ up: '上涨', down: '下跌', flat: '持平' } as Record<string, string>)[String(value)] || String(value)
  if (typeof value === 'number') {
    if (moneyEvidenceKeys.has(key)) return new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)
    if (key === 'change_percent') return new Intl.NumberFormat('zh-CN', { style: 'percent', maximumFractionDigits: 1 }).format(value)
    return Number.isInteger(value) ? value.toLocaleString('zh-CN') : value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
  }
  if (typeof value === 'object') return Object.entries(value as Record<string, unknown>).map(([nestedKey, item]) => `${evidenceLabels[nestedKey] || nestedKey} ${formatEvidenceValue(nestedKey, item)}`).join(' · ')
  return String(value)
}

function formatRange(startDate: string, endDate: string) {
  return `${startDate.replaceAll('-', '.')} — ${endDate.replaceAll('-', '.')}`
}

export function AssistantPanel({ startDate, endDate, navigating = false, navigationStatus, onNavigate }: Props) {
  const [question, setQuestion] = useState('')
  const [pinnedResponse, setPinnedResponse] = useState<AssistantResponse | null>(null)
  const [sessionId, setSessionId] = useState<string>()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [showEvidence, setShowEvidence] = useState(false)
  const controller = useRef<AbortController | null>(null)

  useEffect(() => () => controller.current?.abort(), [])

  const submit = async (event?: FormEvent, submittedQuestion?: string) => {
    event?.preventDefault()
    const value = (submittedQuestion ?? question).trim()
    if (!value || loading) return
    controller.current?.abort()
    const nextController = new AbortController()
    controller.current = nextController
    setLoading(true)
    setError('')
    setShowEvidence(false)
    try {
      const next = await askAssistant(value, startDate && endDate ? { start_date: startDate, end_date: endDate } : undefined, sessionId, nextController.signal)
      setPinnedResponse(next)
      setSessionId(next.session_id)
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      setError(err instanceof Error ? err.message : '对话服务暂时不可用。')
    } finally {
      if (!nextController.signal.aborted) setLoading(false)
    }
  }

  const statusLabel = pinnedResponse?.status === 'answered' ? '已核对' : pinnedResponse?.status === 'needs_clarification' ? '需要补充' : '暂不支持'
  const providerLabel = pinnedResponse?.provider.name === 'mock' ? '本地 Mock' : 'DeepSeek'
  const answerRange = pinnedResponse?.navigation
  const currentRangeMatchesAnswer = Boolean(answerRange && answerRange.start_date === startDate && answerRange.end_date === endDate)

  return <section className="assistant-panel" aria-label="AI 数据问答">
    <div className="assistant-heading">
      <div className="assistant-title"><span className="assistant-icon"><MessageSquare size={17} aria-hidden="true" /></span><div><p className="panel-kicker">03 / VERIFIED QA</p><h2>问问经营数据</h2></div></div>
      <span className="assistant-scope">提问默认使用看板范围</span>
    </div>
    <form className="assistant-form" onSubmit={submit}>
      <input value={question} onChange={event => setQuestion(event.target.value)} placeholder="例如：哪个品类的门店营业额最高？" aria-label="输入经营数据问题" maxLength={500} />
      <button type="submit" disabled={!question.trim() || loading}>{loading ? <RefreshCw size={16} className="spin" aria-hidden="true" /> : <ArrowUpRight size={16} aria-hidden="true" />}<span>{loading ? '查询中' : '提问'}</span></button>
    </form>
    <div className="assistant-examples" aria-label="示例问题">{examples.map(example => <button type="button" key={example} onClick={() => { setQuestion(example); void submit(undefined, example) }}>{example}</button>)}</div>
    {error && <div className="assistant-result assistant-error" role="alert"><AlertCircle size={17} aria-hidden="true" /><span>{error}</span><button type="button" onClick={() => void submit()}><RefreshCw size={14} aria-hidden="true" /> 重试</button></div>}
    {pinnedResponse && <div className={`assistant-result assistant-${pinnedResponse.status}`} role="status"><div className="assistant-result-top"><span className="assistant-status">{pinnedResponse.status === 'answered' && <Check size={13} aria-hidden="true" />}{statusLabel}</span><span className="assistant-provider">{providerLabel} · {pinnedResponse.evidence ? '已执行白名单查询' : '未提供查询证据'}</span></div><p className="assistant-answer">{pinnedResponse.answer}</p>{answerRange && <div className="assistant-query-range"><span><CalendarDays size={14} aria-hidden="true" />此回答查询范围：{formatRange(answerRange.start_date, answerRange.end_date)}</span>{!currentRangeMatchesAnswer && onNavigate && <button type="button" onClick={() => onNavigate(answerRange)} disabled={navigating} aria-label={`查看 AI 查询范围 ${answerRange.start_date} 至 ${answerRange.end_date}`}><CalendarDays size={14} aria-hidden="true" />{navigating ? '正在更新看板' : '查看此范围'}</button>}</div>}{navigationStatus && <p className="assistant-navigation-status"><Check size={14} aria-hidden="true" />{navigationStatus}</p>}{pinnedResponse.evidence && <details open={showEvidence} onToggle={event => setShowEvidence((event.currentTarget as HTMLDetailsElement).open)} className="assistant-evidence"><summary>查看查询依据 <ChevronDown size={14} aria-hidden="true" /></summary><div className="evidence-copy"><span>{pinnedResponse.evidence.summary}</span><span>{Object.entries(pinnedResponse.evidence.filters).map(([key, value]) => `${evidenceLabels[key] || key}: ${value}`).join(' · ')}</span><span>{Object.entries(pinnedResponse.evidence.values).map(([key, value]) => `${evidenceLabels[key] || key}: ${formatEvidenceValue(key, value)}`).join(' · ')}</span></div></details>}</div>}
  </section>
}
