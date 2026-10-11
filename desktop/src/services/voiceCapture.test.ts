/**
 * 麦克风采集的单测（第 103 批）。
 *
 * ## 为什么要测这两件事
 *
 * 1. **选定的设备有没有真的传下去**：`deviceId` 一路从偏好文件 → store → 这里，
 *    中间任何一环写错（比如拼成 `deviceId: id` 而不是 `{ exact: id }`）的后果是
 *    "选了没用"或"悄悄换了一个麦"，而界面两边都看不出来。
 * 2. **失败原因有没有被翻译对**：`NotAllowedError`（去隐私设置放行）、
 *    `NotReadableError`（关掉占用的程序）、`OverconstrainedError`（重选设备）
 *    要求用户做的事完全不同。翻译错了，用户就会去做无用功。
 *
 * ⚠️ 这里**不测** AudioWorklet 的音频处理（VAD、断句）：那需要真实音频与
 * AudioContext 时序，属于"要真跑一遍才说明得了"的范围，本次如实记为未覆盖。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  CaptureError,
  createCapture,
  listAudioInputs,
  resetAudioInputsCache,
} from './voiceCapture'

/** 记下 `getUserMedia` 收到的约束，供断言使用。 */
let lastConstraints: MediaStreamConstraints | null = null
/** 降级路径创建的 ScriptProcessorNode（用例靠它喂音频块）。 */
let lastScriptNode: { onaudioprocess: ((event: AudioProcessingEvent) => void) | null } | null = null

/**
 * 每个用例前把浏览器侧的基础设施装成"能跑完 createCapture"的最小样子。
 *
 * `workletFails` 用来模拟用户实测的那条路：`addModule` 抛
 * `Unable to load a worklet's module.`。
 */
function installBrowser(fail?: { name: string; message?: string }, workletFails = false) {
  lastConstraints = null
  lastScriptNode = null

  // `onended` 由 createCapture 挂上（设备中途断开的信号）—— 类型上先留出来
  const track: { stop: () => void; onended?: () => void } = { stop: vi.fn() }
  const stream = {
    getTracks: () => [track],
    // createCapture 用它取第一条音轨来挂 `onended`（第 103 批）
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

  // 最小 AudioContext / AudioWorkletNode：`createCapture` 只用它们的这几个方法
  class FakeWorkletNode {
    // `port.close` / `disconnect` 是 `capture.stop()` 会调的（缺了就会让 stop 抛错）
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
    // `createCapture` 会 `resume()`：浏览器里刚建的 AudioContext 可能是 suspended
    resume = vi.fn(async () => undefined)
    close = vi.fn(async () => undefined)
    // 降级路径用到的两个节点工厂
    createGain = vi.fn(() => ({ gain: { value: 1 }, connect: vi.fn(), disconnect: vi.fn() }))
    createScriptProcessor = vi.fn(() => {
      // ⚠️ 必须让 `lastScriptNode` 指向**返回出去的那个对象本身**（不能展开成新对象，
      // 否则生产代码给返回对象挂的 `onaudioprocess` 我们这边看不到）
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
    // ⚠️ 必须是 `{ exact: … }`：宽松匹配会在设备不在时**静默换一个**，
    // 于是"选了耳麦却用内置麦"，界面上看不出来（见 voiceCapture 里的说明）
    expect(audio.deviceId).toEqual({ exact: 'device-abc' })
  })

  it('不传设备 id 时不带 deviceId 约束（交给系统默认）', async () => {
    installBrowser()

    await createCapture({ onLevel: vi.fn(), onSegment: vi.fn(), onError: vi.fn() })

    const audio = lastConstraints?.audio as MediaTrackConstraints
    expect(audio.deviceId).toBeUndefined()
    // 其它约束照旧，不能被这次改动弄丢
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

    // ⚠️ `reason` 是 store 判断"要不要回落系统默认"的唯一依据
    // （见 voiceSessionStore 的 openCaptureWithFallback）
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

    // ① 必须留痕：本项目对"静默降级"零容忍 —— 悄悄换一条更差的路，
    // 以后所有音频问题都会变得无法解释（见 voiceCapture 里的说明）
    expect(warn).toHaveBeenCalledWith(
      expect.stringContaining('降级到 ScriptProcessorNode'),
      expect.anything(),
      expect.anything(),
      expect.anything(),
    )
    // ② 真的挂上了降级回调（没挂上就等于"静默不工作"）
    expect(lastScriptNode?.onaudioprocess).toBeTruthy()

    // ③ 喂一块"有声"音频：音量回调动起来 ⇒ VAD 确实接在这条路上
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

    // 拔掉 USB 麦 / 蓝牙断连：`getUserMedia` 不会抛错，也没有音频块了 ——
    // 第 103 批之前这条路**完全没有信号**（onError 从来没被调用过）
    track.onended?.()
    expect(onError).toHaveBeenCalledTimes(1)
    expect(String(onError.mock.calls[0]?.[0])).toContain('断开')

    // 只报一次：同一次中断不该反复弹给用户
    track.onended?.()
    expect(onError).toHaveBeenCalledTimes(1)
  })

  it('用户主动停掉采集**不算故障**（不该报 onError）', async () => {
    const { track } = installBrowser()
    const onError = vi.fn()

    const capture = await createCapture({ onLevel: vi.fn(), onSegment: vi.fn(), onError })
    capture.stop()
    // 主动 stop 也会让 track 结束 —— 若不判 `stopped`，每次关语音都会弹一条错误
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
