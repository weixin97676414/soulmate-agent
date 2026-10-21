

























import { beforeEach, describe, expect, it, vi } from 'vitest'


const voiceStatusMock = vi.hoisted(() => vi.fn())







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

  







  it('force 能突破缓存：模型补装完成后要能重新探到可用', async () => {
    voiceStatusMock.mockResolvedValueOnce({ asr: { available: false } })
    await useVoiceStore.getState().refresh()
    expect(useVoiceStore.getState().availability).toEqual({ asr: false })

    
    voiceStatusMock.mockResolvedValueOnce({ asr: { available: true } })
    await useVoiceStore.getState().refresh({ force: true })

    expect(voiceStatusMock).toHaveBeenCalledTimes(2)
    expect(useVoiceStore.getState().availability).toEqual({ asr: true })
  })

  it('不带 force 时仍然走缓存（常规路径不该多打接口）', async () => {
    voiceStatusMock.mockResolvedValue({ asr: { available: false } })
    await useVoiceStore.getState().refresh()
    await useVoiceStore.getState().refresh() 
    expect(voiceStatusMock).toHaveBeenCalledTimes(1)
  })
})
