// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useNotificationStore } from '@/stores/notificationStore'

/**
 * 通知"多久消失"的口径（产品拍板，第 86 批 M-32 落地）。
 *
 * 为什么值得单测：这条规则**只在时间里体现** —— 界面上看不出对错，
 * 而写错了的表现是"带按钮的通知一闪而过，用户根本来不及点"，
 * 事后没人能复现（通知早就没了）。用例把时间轴钉住即可。
 *
 * ⚠️ 模块是全局单例（zustand），所以每个用例先 `clearAll()` —— 否则前一条的 toast
 * 会留在后面用例里，断言"长度是 1"就会随机红。
 */
describe('通知的消失口径', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    useNotificationStore.getState().clearAll()
  })

  afterEach(() => {
    vi.useRealTimers()
    useNotificationStore.getState().clearAll()
  })

  it('纯提醒：10 秒后自动消失', () => {
    const id = useNotificationStore.getState().push({ level: 'info', title: '提醒' })

    vi.advanceTimersByTime(9_999)
    expect(useNotificationStore.getState().toasts.map((item) => item.id)).toContain(id)

    vi.advanceTimersByTime(1)
    expect(useNotificationStore.getState().toasts.map((item) => item.id)).not.toContain(id)
  })

  it('带按钮的通知：常驻到手动关（按钮一闪而过等于没有这个按钮）', () => {
    const id = useNotificationStore
      .getState()
      .push({ level: 'success', title: '任务完成', action: { label: '查看结果', run: () => {} } })

    vi.advanceTimersByTime(60_000)
    expect(useNotificationStore.getState().toasts.map((item) => item.id)).toContain(id)

    useNotificationStore.getState().dismiss(id)
    expect(useNotificationStore.getState().toasts).toHaveLength(0)
  })

  it('有按钮时，显式传的倒计时也不生效（否则将来漏传就变成"按钮点不到"）', () => {
    const id = useNotificationStore.getState().push({
      level: 'success',
      title: '带按钮但显式给了 3 秒',
      autoDismissMs: 3_000,
      action: { label: '查看结果', run: () => {} },
    })

    vi.advanceTimersByTime(3_000)
    expect(useNotificationStore.getState().toasts.map((item) => item.id)).toContain(id)
  })

  it('显式传更短的时间会被尊重（纯提醒仍然可以自己定倒计时）', () => {
    useNotificationStore.getState().push({
      level: 'info',
      title: '短提示',
      autoDismissMs: 3_000,
    })

    vi.advanceTimersByTime(3_000)
    expect(useNotificationStore.getState().toasts).toHaveLength(0)
  })
})
