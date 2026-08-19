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
  tool_call: { name: string; arguments: Record<string, unknown> } | null
  evidence: AssistantEvidence | null
  provider: { name: string; mode: 'mock' | 'live' }
}
