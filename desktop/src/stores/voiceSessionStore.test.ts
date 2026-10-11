/**
 * 麦克风会话的单测（第 103 批）。
 *
 * ## 为什么这几条最值得测
 *
 * 它们守的是**"打不开麦克风之后就再也救不回来"**这一类静默失败 —— 用户报障时
 * 看到的现象就是"语音功能用不了了、输入栏下面那条状态也没了"，而代码里没有一处
 * 会因此变红：
 *
 * 1. 失败后**句柄必须归零**：`capture` 是模块级句柄，残留会让下一次 `openCapture`
 *    以为"已经在跑"而只换等待目标 —— 用户点重试**什么也不会发生**。
 * 2. 失败原因必须进 store（`micError`）：只在通知里闪一下的话，状态行那头是空的，
 *    用户看不到任何原因、也没有下一步。
 * 3. 点名的设备不在了要**回落系统默认再试一次**，而且要顺手把偏好改回空，
 *    否则每次启动都先失败一次，表现成"语音时好时坏"。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

/** `createCapture` 的替身：由每个用例决定成功 / 抛什么错。 */
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

// 这两个只在"喊醒某个目标"时才用得上，本文件不涉及 —— 换成替身免得真去切搭子
vi.mock('@/services/assistantSwitch', () => ({ switchAssistant: vi.fn() }))
vi.mock('@/services/groupSwitch', () => ({ switchGroup: vi.fn() }))

/*
  ⚠️ `appStore`（被 store 间接引入）在**模块顶层**读 localStorage（当前主题），而
  vitest 的 environment 不保证提供它。必须在导入 store **之前**装上最小实现 ——
  下面的 `await import` 正好保证了顺序（静态 import 会被提升，所以这里刻意用动态导入）。
*/
vi.stubGlobal('localStorage', {
  getItem: () => null,
  setItem: () => undefined,
  removeItem: () => undefined,
})

/*
  ⚠️ 通知 store 用 `window.setTimeout` 做"自动消失"，而测试环境（node）没有 `window`
  —— 于是每次 `notify` 都会抛 `ReferenceError`。它被吞在 promise 里、测试仍然是绿的，
  但 vitest 会报 unhandled rejection，而且**"通知其实没发出去"这件事被掩盖了**。
  这里补一个最小 window，让那条路径真的跑通。
*/
vi.stubGlobal('window', {
  setTimeout: () => 0,
  clearTimeout: () => undefined,
})

const { useVoiceSessionStore, resetMicDeviceCacheForTest } = await import(
  '@/stores/voiceSessionStore'
)
const { CaptureError } = await import('@/services/voiceCapture')

/** 一个能跑的最小采集句柄。 */
function fakeCapture() {
  return { stop: vi.fn() }
}

/** 等异步的 `openCapture` 链跑完（它内部有 await）。 */
const settle = () => vi.waitFor(() => expect(captureMock).toHaveBeenCalled())

beforeEach(() => {
  captureMock.mockReset()
  readMicDeviceIdMock.mockReset().mockResolvedValue('')
  writeMicDeviceIdMock.mockReset().mockResolvedValue(undefined)
  /*
    ⚠️ 这里必须用 `shutdown()`，不能只 `setState({ phase: 'off' })`：
    真正的 `phase` 与采集句柄 `capture` 都是**模块级变量**，只有 `shutdown()`（内部
    `stopCapture()` + `setPhase()`）会把两者一起复位。只改 store.state 的话，
    上一个用例留下的 `capture` 会让下一次 `openCapture` 认为"已经在跑"而直接返回 ——
    表现就是"createCapture 一次都没被调用"（而这条恰恰也是生产里那个 bug 的形态）。
  */
  useVoiceSessionStore.getState().shutdown()
  // 清掉模块级的"设备偏好已读"缓存，否则第二个用例会复用第一个读到的设备
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

    /*
      ⚠️ 这条是本文件的核心：失败之后必须能**再开一次**。

      守护点在 `retryMic()` 开头那句 `stopCapture()` —— 少了它，若 `capture` 上还留着
      一条已经死掉的流，第二次开麦会在 `if (capture)` 处提前返回、只换等待目标，
      表现就是"点重试没反应"（不报错，只能靠这条用例守）。

      ⚠️ 但要说准它**证明了什么**：本用例里失败发生在 `capture` 赋值**之前**，
      所以句柄本来就是 null。它证明的是"retryMic 会重新走完开麦链路"，
      **不是**"catch 里那句归零救了场"（那一步经反向验证确认是防御性的、
      单独撤掉也不会让任何用例变红）。
    */
    captureMock.mockResolvedValueOnce(fakeCapture())
    useVoiceSessionStore.getState().retryMic()
    await vi.waitFor(() => expect(useVoiceSessionStore.getState().phase).toBe('global'))

    expect(captureMock).toHaveBeenCalledTimes(2)
    // 重试成功后原因要清掉，否则状态行会一直挂着上一条错误
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

    useVoiceSessionStore.getState().enable() // → standby
    await vi.waitFor(() => expect(useVoiceSessionStore.getState().phase).toBe('standby'))

    useVoiceSessionStore.getState().setMicDevice('dev-earbuds')
    await vi.waitFor(() => expect(captureMock).toHaveBeenCalledTimes(2))

    // ⚠️ 换了麦克风但层级不变：用户还能直接喊唤醒词，不必重新说一遍「开启语音」。
    // （踩过的坑：把 `awaiting`/`recognizing` 误判成 global，会让"正在待令"的用户
    //  在换设备后彻底发不出已经说好的内容。）
    expect(useVoiceSessionStore.getState().phase).toBe('standby')
  })

  it('选定的设备不在了 → 回落系统默认再试一次，并把偏好改回空', async () => {
    readMicDeviceIdMock.mockResolvedValue('dev-gone')
    captureMock
      .mockRejectedValueOnce(new CaptureError('上次选的麦克风不在了（可能已拔掉或换了接口）。', 'OverconstrainedError'))
      .mockResolvedValueOnce(fakeCapture())

    useVoiceSessionStore.getState().bootstrap()
    await vi.waitFor(() => expect(useVoiceSessionStore.getState().phase).toBe('global'))

    // 第一次带旧设备、第二次不带（= 系统默认）
    expect(captureMock).toHaveBeenNthCalledWith(1, expect.anything(), { deviceId: 'dev-gone' })
    expect(captureMock).toHaveBeenNthCalledWith(2, expect.anything(), {})
    // ⚠️ 偏好也要跟着改回空：否则每次启动都要先失败一次，用户感受是"时好时坏"
    expect(writeMicDeviceIdMock).toHaveBeenCalledWith('')
    const state = useVoiceSessionStore.getState()
    expect(state.micDeviceId).toBe('')
    // 并且要留一句"回落过"的说明（设置面板会显示它）
    expect(state.micDeviceFellBack).toBe(true)
    // 回落后**不算失败**：不该在输入栏同时挂一条错误提示
    expect(state.micError).toBeNull()
  })
})
