/**
 * 语音能力探测的单测（第 103 批）。
 *
 * ## 守的是什么
 *
 * `ComposerShell` 里 `canSpeak = 可用 && availability?.asr === true` —— 也就是说
 * **探测没成功，麦克风按钮与语音状态行就不会出现**。而这套东西原先只在"进入输入框"
 * 时问一次、失败静默吞掉，于是那一次恰好落在"核心还没起来 / 正在重启 / token 刚换"
 * 的时刻时，用户看到的就是"语音功能用不了了、输入框下面的状态也没了"，并且**不会自己恢复**。
 *
 * 修法有两半：① 失败**不缓存终态**（本文件守住它）；② 后端就绪跳变时补探一次
 * （在 `ComposerShell` 的 effect 里，依赖 `backendStatus.state`）—— ② 属于组件层，
 * 本项目还没有渲染层测试底座，如实记为未覆盖。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

/** `/v1/voice/status` 的替身。 */
const voiceStatusMock = vi.hoisted(() => vi.fn())

/*
  ⚠️ 刻意**不**用 `importOriginal` 取真实的 appStore：它在模块顶层读 localStorage
  （当前主题），而测试环境不保证有 —— 一旦求值就会以
  `localStorage.getItem is not a function` 失败。`voiceStore` 只从 appStore 取 `getApi`，
  所以一个最小替身就够。
*/
vi.mock('@/stores/appStore', () => ({
  getApi: () => ({ voiceStatus: voiceStatusMock }) as never,
}))

const { useVoiceStore } = await import('@/stores/voiceStore')

beforeEach(() => {
  voiceStatusMock.mockReset()
  useVoiceStore.setState({ availability: null, transcribing: false })
})

describe('能力探测', () => {
  it('探测失败**不留终态**：下一次 refresh 会重新问（否则按钮永久消失）', async () => {
    voiceStatusMock.mockRejectedValueOnce(new Error('核心还没起来'))

    await useVoiceStore.getState().refresh()
    expect(useVoiceStore.getState().availability).toBeNull()

    // 核心起来了 —— 这时必须能问出结果（原先"失败"与"成功过"没有区别，
    // 一旦第一次失败，按钮就再也不会出现）
    voiceStatusMock.mockResolvedValueOnce({ asr: { available: true } })
    await useVoiceStore.getState().refresh()

    expect(useVoiceStore.getState().availability).toEqual({ asr: true })
  })

  it('成功之后不重复问（装好的模型不会凭空消失，不必每次进输入框都打一次接口）', async () => {
    voiceStatusMock.mockResolvedValue({ asr: { available: true } })

    await useVoiceStore.getState().refresh()
    await useVoiceStore.getState().refresh()

    expect(voiceStatusMock).toHaveBeenCalledTimes(1)
  })

  it('模型不可用时如实记成 false（不是"没探测过"）', async () => {
    voiceStatusMock.mockResolvedValue({ asr: { available: false } })

    await useVoiceStore.getState().refresh()

    expect(useVoiceStore.getState().availability).toEqual({ asr: false })
  })
})
