import api from './index'

type Assets = { fetch(request: Request): Promise<Response> }
type PagesEnv = { ASSETS: Assets }

export default {
  async fetch(request: Request, env: PagesEnv): Promise<Response> {
    const url = new URL(request.url)
    if (url.pathname.startsWith('/api/')) return api.fetch(request)
    return env.ASSETS.fetch(request)
  },
}
