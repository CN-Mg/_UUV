/** 同源 API；开发时由 Vite 代理，生产时由 FastAPI 托管。 */
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, { headers: { 'Content-Type': 'application/json' }, ...options })
  if (!response.ok) {
    const body = await response.text()
    throw new Error(`${response.status} · ${body.slice(0, 600)}`)
  }
  return response.json() as Promise<T>
}

/** 运行控制统一提交 JSON；状态权威来自后端响应与事件。 */
export function post<T>(path: string, body: unknown = {}): Promise<T> {
  return api<T>(path, { method: 'POST', body: JSON.stringify(body) })
}
