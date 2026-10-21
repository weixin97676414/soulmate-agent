















import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  CaptureError,
  createCapture,
  listAudioInputs,
  resetAudioInputsCache,
} from './voiceCapture'


let lastConstraints: MediaStreamConstraints | null = null

let lastScriptNode: { onaudioprocess: ((event: AudioProcessingEvent) => void) | null } | null = null







function installBrowser(fail?: { name: string; message?: string }, workletFails = false) {
  lastConstraints = null
  lastScriptNode = null

  
  const track: { stop: () => void; onended?: () => void } = { stop: vi.fn() }
  const stream = {
    getTracks: () => [track],
    
    getAudioTracks: () => [track],
  } as unknown as MediaStream

  const mediaDevices = {
    getUserMedia: vi.fn(async (constraints: MediaStreamConstraints) => {
      lastConstraints = constraints
      if (fail) {
        const error = new Error(fail.message ?? fail.name)
        error.name = fail.name
        throw error
      }
      return stream
    }),
    enumerateDevices: vi.fn(async () => []),
    addEventListener: vi.fn(),
  }

  vi.stubGlobal('navigator', { mediaDevices })

  
  class FakeWorkletNode {
    
    port = {
      onmessage: null as ((event: MessageEvent<Float32Array>) => void) | null,
      close: vi.fn(),
    }
    connect = vi.fn()
    disconnect = vi.fn()
  }
  class FakeAudioContext {
    sampleRate = 16000
    destination = {}
    state = 'running'
    audioWorklet = {
      addModule: workletFails
        ? vi.fn(async () => {
            throw new Error("Unable to load a worklet's module.")
          })
        : vi.fn(async () => undefined),
    }
    createMediaStreamSource = vi.fn(() => ({ connect: vi.fn(), disconnect: vi.fn() }))
    
    resume = vi.fn(async () => undefined)
    close = vi.fn(async () => undefined)
    
    createGain = vi.fn(() => ({ gain: { value: 1 }, connect: vi.fn(), disconnect: vi.fn() }))
    createScriptProcessor = vi.fn(() => {
      
      
      const created = {
        onaudioprocess: null as ((event: AudioProcessingEvent) => void) | null,
        connect: vi.fn(),
        disconnect: vi.fn(),
      }
      lastScriptNode = created
      return created
    })
  }
  vi.stubGlobal('AudioContext', FakeAudioContext)
  vi.stubGlobal('AudioWorkletNode', FakeWorkletNode)
  vi.stubGlobal('URL', { createObjectURL: () => 'blob:x', revokeObjectURL: () => undefined })

  return { stream, track, mediaDevices }
}

beforeEach(() => {
  resetAudioInputsCache()
  vi.unstubAllGlobals()
})

describe('createCapture 的设备选择', () => {
  it('传入设备 id 时用 exact 约束点名校验，而不是宽松匹配', async () => {
    installBrowser()

    await createCapture({ onLevel: vi.fn(), onSegment: vi.fn(), onError: vi.fn() }, {
      deviceId: 'device-abc',
    })

    const audio = lastConstraints?.audio as MediaTrackConstraints
    
    
    expect(audio.deviceId).toEqual({ exact: 'device-abc' })
  })

  it('不传设备 id 时不带 deviceId 约束（交给系统默认）', async () => {
    installBrowser()

    await createCapture({ onLevel: vi.fn(), onSegment: vi.fn(), onError: vi.fn() })

    const audio = lastConstraints?.audio as MediaTrackConstraints
    expect(audio.deviceId).toBeUndefined()
    
    expect(audio.channelCount).toBe(1)
    expect(audio.echoCancellation).toBe(true)
  })
})

describe('createCapture 的失败翻译', () => {
  it('设备被占用 → 提示"关掉它再试"，且 reason 原样带出', async () => {
    installBrowser({ name: 'NotReadableError' })

    const error = await createCapture({
      onLevel: vi.fn(),
      onSegment: vi.fn(),
      onError: vi.fn(),
    }).catch((caught: unknown) => caught)

    expect(error).toBeInstanceOf(CaptureError)
    expect((error as CaptureError).reason).toBe('NotReadableError')
    expect((error as CaptureError).message).toContain('占用')
  })

  it('点名的设备不存在 → 单独的说明（引导去重选设备），并带 OverconstrainedError', async () => {
    installBrowser({ name: 'OverconstrainedError' })

    const error = await createCapture(
      { onLevel: vi.fn(), onSegment: vi.fn(), onError: vi.fn() },
      { deviceId: 'gone' },
    ).catch((caught: unknown) => caught)

    
    
    expect((error as CaptureError).reason).toBe('OverconstrainedError')
    expect((error as CaptureError).message).toContain('上次选的麦克风不在了')
  })

  it('被系统拒绝 → 引导去隐私设置（而不是让用户反复重试）', async () => {
    installBrowser({ name: 'NotAllowedError' })

    const error = await createCapture({
      onLevel: vi.fn(),
      onSegment: vi.fn(),
      onError: vi.fn(),
    }).catch((caught: unknown) => caught)

    expect((error as CaptureError).message).toContain('麦克风被拒绝')
  })
})

describe('AudioWorklet 加载失败时降级', () => {
  it('改用 ScriptProcessorNode 采集，音频块照样进 VAD（且必须留痕）', async () => {
    installBrowser(undefined, true)
    const onLevel = vi.fn()
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)

    await createCapture({ onLevel, onSegment: vi.fn(), onError: vi.fn() })

    
    
    expect(warn).toHaveBeenCalledWith(
      expect.stringContaining('降级到 ScriptProcessorNode'),
      expect.anything(),
      expect.anything(),
      expect.anything(),
    )
    
    expect(lastScriptNode?.onaudioprocess).toBeTruthy()

    
    const loud = new Float32Array(1024).fill(0.2)
    lastScriptNode?.onaudioprocess?.({
      inputBuffer: { getChannelData: () => loud },
    } as unknown as AudioProcessingEvent)

    expect(onLevel).toHaveBeenCalled()
    warn.mockRestore()
  })
})

describe('采集中途被中断', () => {
  it('设备断开时通过 onError 上报（否则界面一直显示"在听"却什么都收不到）', async () => {
    const { track } = installBrowser()
    const onError = vi.fn()

    await createCapture({ onLevel: vi.fn(), onSegment: vi.fn(), onError })
    expect(onError).not.toHaveBeenCalled()

    
    
    track.onended?.()
    expect(onError).toHaveBeenCalledTimes(1)
    expect(String(onError.mock.calls[0]?.[0])).toContain('断开')

    
    track.onended?.()
    expect(onError).toHaveBeenCalledTimes(1)
  })

  it('用户主动停掉采集**不算故障**（不该报 onError）', async () => {
    const { track } = installBrowser()
    const onError = vi.fn()

    const capture = await createCapture({ onLevel: vi.fn(), onSegment: vi.fn(), onError })
    capture.stop()
    
    track.onended?.()

    expect(onError).not.toHaveBeenCalled()
  })
})

describe('listAudioInputs', () => {
  function withDevices(devices: MediaDeviceInfo[]) {
    const { mediaDevices } = installBrowser()
    mediaDevices.enumerateDevices = vi.fn(async () => devices) as never
    return mediaDevices
  }

  it('只取录音设备，无名设备给占位名（下拉里不能是一排空白）', async () => {
    withDevices([
      { kind: 'audioinput', deviceId: 'a', label: '' },
      { kind: 'videoinput', deviceId: 'cam', label: '摄像头' },
      { kind: 'audioinput', deviceId: 'b', label: '耳麦' },
    ] as MediaDeviceInfo[])

    const inputs = await listAudioInputs()

    expect(inputs).toEqual([
      { deviceId: 'a', label: '麦克风 1' },
      { deviceId: 'b', label: '耳麦' },
    ])
  })

  it('结果被缓存（面板反复开关不该每次去问系统）', async () => {
    const mediaDevices = withDevices([
      { kind: 'audioinput', deviceId: 'a', label: '麦' },
    ] as MediaDeviceInfo[])

    await listAudioInputs()
    await listAudioInputs()

    expect(mediaDevices.enumerateDevices).toHaveBeenCalledTimes(1)
  })

  it('拿不到枚举能力时返回空数组，而不是把面板炸掉', async () => {
    vi.stubGlobal('navigator', {})

    await expect(listAudioInputs()).resolves.toEqual([])
  })
})
