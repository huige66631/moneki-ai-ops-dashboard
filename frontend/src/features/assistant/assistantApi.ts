import { AssistantResponse } from './assistantTypes'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'

export async function askAssistant(question: string, context?: { start_date: string; end_date: string }, signal?: AbortSignal): Promise<AssistantResponse> {
  const response = await fetch(`${API_BASE}/api/v1/assistant/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, context }),
    signal,
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.detail || '对话服务暂时不可用，请稍后重试。')
  return body
}
