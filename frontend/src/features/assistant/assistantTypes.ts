export type AssistantEvidence = {
  metric: string
  unit: string
  filters: Record<string, string | number>
  values: Record<string, unknown>
  summary: string
}

export type AssistantResponse = {
  status: 'answered' | 'unsupported' | 'needs_clarification' | 'error'
  answer: string
  intent: string | null
  session_id: string
  tool_call: { name: string; arguments: Record<string, unknown> } | null
  evidence: AssistantEvidence | null
  navigation: AssistantNavigation | null
  provider: { name: string; mode: 'mock' | 'live' }
}

export type AssistantNavigation = {
  start_date: string
  end_date: string
  store_id: string | null
  reason: 'answer_query_range'
}
