
















import { beforeEach, describe, expect, it, vi } from 'vitest'


const captureMock = vi.hoisted(() => vi.fn())
const readMicDeviceIdMock = vi.hoisted(() => vi.fn(async () => ''))
const writeMicDeviceIdMock = vi.hoisted(() => vi.fn(async () => undefined))

vi.mock('@/services/voiceCapture', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/voiceCapture')>()
  return { ...actual, createCapture: captureMock }
})

vi.mock('@/services/micPrefs', () => ({
  readMicDeviceId: readMicDeviceIdMock,
  writeMicDeviceId: writeMicDeviceIdMock,
}))


vi.mock('@/services/assistantSwitch', () => ({ switchAssistant: vi.fn() }))
vi.mock('@/services/groupSwitch', () => ({ switchGroup: vi.fn() }))






vi.stubGlobal('localStorage', {
  getItem: () => null,
  setItem: () => undefined,
  removeItem: () => undefined,
})







vi.stubGlobal('window', {
  setTimeout: () => 0,
  clearTimeout: () => undefined,
})

const { useVoiceSessionStore, resetMicDeviceCacheForTest } = await import(
  '@/stores/voiceSessionStore'
)
const { CaptureError } = await import('@/services/voiceCapture')


function fakeCapture() {
  return { stop: vi.fn() }
}


const settle = () => vi.waitFor(() => expect(captureMock).toHaveBeenCalled())

beforeEach(() => {
  captureMock.mockReset()
  readMicDeviceIdMock.mockReset().mockResolvedValue('')
  writeMicDeviceIdMock.mockReset().mockResolvedValue(undefined)
  






  useVoiceSessionStore.getState().shutdown()
  
  resetMicDeviceCacheForTest()
  useVoiceSessionStore.setState({ micDeviceId: '', micDeviceFellBack: false })
})

describe('打开麦克风失败后的自救', () => {
  it('失败时记下原因、回到 off，并且**下一次还能再试**（句柄已归零）', async () => {
    captureMock.mockRejectedValueOnce(new CaptureError('麦克风被别的程序占用了，关掉它再试。', 'NotReadableError'))

    useVoiceSessionStore.getState().bootstrap()
    await settle()
    await vi.waitFor(() => expect(useVoiceSessionStore.getState().micError).not.toBeNull())

    const state = useVoiceSessionStore.getState()
    expect(state.micError).toContain('占用')
    expect(state.phase).toBe('off')

    











    captureMock.mockResolvedValueOnce(fakeCapture())
    useVoiceSessionStore.getState().retryMic()
    await vi.waitFor(() => expect(useVoiceSessionStore.getState().phase).toBe('global'))

    expect(captureMock).toHaveBeenCalledTimes(2)
    
    expect(useVoiceSessionStore.getState().micError).toBeNull()
  })

  it('retryMic 传下去的失败原因会进 store（状态行据此显示）', async () => {
    captureMock.mockRejectedValue(new CaptureError('没有找到可用的麦克风设备。', 'NotFoundError'))

    useVoiceSessionStore.getState().retryMic()
    await vi.waitFor(() => expect(useVoiceSessionStore.getState().micError).not.toBeNull())

    expect(useVoiceSessionStore.getState().micError).toContain('没有找到可用的麦克风设备')
  })
})

describe('设备选择', () => {
  it('开麦时把"上次选的设备"传下去', async () => {
    readMicDeviceIdMock.mockResolvedValue('dev-earbuds')
    captureMock.mockResolvedValue(fakeCapture())

    useVoiceSessionStore.getState().bootstrap()
    await settle()

    await vi.waitFor(() =>
      expect(captureMock).toHaveBeenCalledWith(expect.anything(), { deviceId: 'dev-earbuds' }),
    )
  })

  it('待命时换设备：仍留在待命层（不被踢回"只认开关词"的全局层）', async () => {
    captureMock.mockResolvedValue(fakeCapture())

    useVoiceSessionStore.getState().enable() 
    await vi.waitFor(() => expect(useVoiceSessionStore.getState().phase).toBe('standby'))

    useVoiceSessionStore.getState().setMicDevice('dev-earbuds')
    await vi.waitFor(() => expect(captureMock).toHaveBeenCalledTimes(2))

    
    
    
    expect(useVoiceSessionStore.getState().phase).toBe('standby')
  })

  it('选定的设备不在了 → 回落系统默认再试一次，并把偏好改回空', async () => {
    readMicDeviceIdMock.mockResolvedValue('dev-gone')
    captureMock
      .mockRejectedValueOnce(new CaptureError('上次选的麦克风不在了（可能已拔掉或换了接口）。', 'OverconstrainedError'))
      .mockResolvedValueOnce(fakeCapture())

    useVoiceSessionStore.getState().bootstrap()
    await vi.waitFor(() => expect(useVoiceSessionStore.getState().phase).toBe('global'))

    
    expect(captureMock).toHaveBeenNthCalledWith(1, expect.anything(), { deviceId: 'dev-gone' })
    expect(captureMock).toHaveBeenNthCalledWith(2, expect.anything(), {})
    
    expect(writeMicDeviceIdMock).toHaveBeenCalledWith('')
    const state = useVoiceSessionStore.getState()
    expect(state.micDeviceId).toBe('')
    
    expect(state.micDeviceFellBack).toBe(true)
    
    expect(state.micError).toBeNull()
  })
})
