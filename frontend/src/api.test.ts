import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, post } from './api'

afterEach(() => vi.unstubAllGlobals())
describe('同源运行控制请求', () => {
  it('暂停与倍速请求使用指定运行，不在前端推进数学时间', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'paused' }) })
    vi.stubGlobal('fetch', fetchMock)
    await post('/runs/test-a/pause')
    await post('/runs/test-a/speed', { speed: 2 })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/runs/test-a/pause')
    expect(fetchMock.mock.calls[1][1].body).toBe('{"speed":2}')
    expect(fetchMock.mock.calls[1][1].method).toBe('POST')
  })
  it('回放请求读取服务器事件，不调用定位算法', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => [] })
    vi.stubGlobal('fetch', fetchMock)
    expect(await api('/runs/test-a/replay')).toEqual([])
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/runs/test-a/replay')
  })
  it('后端错误保持可见，不伪造成功状态', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 409, text: async () => '运行已经结束' }))
    await expect(post('/runs/test-a/resume')).rejects.toThrow('409 · 运行已经结束')
  })
})
