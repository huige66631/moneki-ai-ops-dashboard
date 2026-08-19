export type Dashboard = {
  range: { start_date: string; end_date: string }
  summary: { revenue: number; order_count: number; average_order_value: number | null }
  daily: Array<{ date: string; revenue: number; order_count: number; average_order_value: number | null }>
  top_products: Array<{ rank: number; product_id: string; product_name: string; product_category: string | null; revenue: number; order_count: number; revenue_share: number }>
  data_quality: { included_record_count: number; excluded_duplicate_count: number; excluded_invalid_amount_count: number; unmatched_store_count: number; unmatched_product_count: number }
}

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'

export async function fetchDashboard(startDate?: string, endDate?: string): Promise<Dashboard> {
  const params = startDate && endDate ? `?start_date=${startDate}&end_date=${endDate}` : ''
  const response = await fetch(`${API_BASE}/api/v1/dashboard${params}`)
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || '接口暂时不可用，请稍后重试。')
  }
  return response.json()
}
