/**
 * 语音会话：应用级**唯一**的一条麦克风，以及它的三层状态机。
 *
 * ## 三层（产品拍板）
 *
 * ```
 *  off ──按 startup_mode 启动──▶ global（全局层：只听「开启语音」/「关闭语音」）
 *                                   │ 听到「开启语音」
 *                                   ▼
 *                                standby（唤醒层：听**所有**搭子**与群**的唤醒词）
 *                                   │ 听到某个唤醒词 → 切到那个搭子 / 那个群
 *                                   ▼
 *                                listening → recognizing → awaiting（录音 / 待令）
 *                                   │ 任何时刻听到「关闭语音」
 *                                   └──▶ 回 global（整个语音功能关掉）
 * ```
 *
 * ⚠️ 唤醒层从"只有搭子"扩到"搭子 + 群"是产品要求。扩展点只有
 * 三处：候选表 `listeningTargets()`、命中后的分派 `switchToTarget()`、
 * 以及界面上那句提示的措辞 —— **状态机本身一行没改**。这正是当初把候选表
 * 和切换路径抽成函数的价值：加一类唤醒目标不需要碰采集、识别、待令任何一环。
 *
 * ⚠️ **"关闭语音"是关整个语音功能**（产品明确要求），但落在 `global` 而不是 `off`：
 * 全局层继续留着，用户随时说一句「开启语音」就能回来，不必再去点界面。
 *
 * ## 为什么必须提到应用级
 *
 * 这套东西原先长在 `ComposerShell` 里 —— 单聊一个实例、群聊又一个，各自开自己的
 * 麦克风。但"常驻监听"下**必须只有一个**：
 *   · 同时开两条流会抢设备（Windows 上第二条常拿到静音，而且**不报错**）；
 *   · "关闭语音"要一次关掉所有，状态分散在组件里就关不干净。
 *
 * 所以采集与状态机搬进这个 store；`ComposerShell` 退化成"订阅 + 提供一个输入框
 * 当落点"（见 `useVoiceSink`）。
 *
 * ⚠️ 这条理由在**群聊也能语音**之后变得更充分：单聊与群聊两个输入壳可能同时在
 * 屏幕上（用户从一个页面切到另一个只隔一帧），而麦克风只能有一条流。落点由
 * `useVoiceSink` 的**挂载/卸载**登记（晚挂载的接管），所以"现在的声音该进哪个
 * 输入框"永远只有一个答案。
 *
 * ## 为什么全局层单独判，不放进命令目录
 *
 * `voiceCommands.ts` 里每条命令都要求"它的按钮此刻在屏幕上"（注册制）。但
 * 「开启语音」/「关闭语音」不属于任何按钮 —— 它们**永远**有效、优先级最高，
 * 必须在搭子层之前检查。放进目录反而要给它开一堆特例。
 */

import { useEffect, useRef } from 'react'
import { create } from 'zustand'

import { switchAssistant } from '@/services/assistantSwitch'
import { switchGroup } from '@/services/groupSwitch'
import { readMicDeviceId, writeMicDeviceId } from '@/services/micPrefs'
import {
  CaptureError,
  createCapture,
  float32ToBase64,
  type VoiceCapture,
} from '@/services/voiceCapture'
import { VOICE_COMMANDS } from '@/services/voiceCommands'
import { getApi, useAppStore } from '@/stores/appStore'
import { useAssistantStore } from '@/stores/assistantStore'
import { useChatStore } from '@/stores/chatStore'
import { useGroupStore } from '@/stores/groupStore'
import { useNotificationStore } from '@/stores/notificationStore'
import { useVoiceCommandStore } from '@/stores/voiceCommandStore'

export type VoicePhase = 'off' | 'global' | 'standby' | 'listening' | 'recognizing' | 'awaiting'

/** 待命期一次送检多久的音频（滑动窗口，理由见 `handleSegment`）。 */
const WAKE_WINDOW_MS = 3000

const NOISE = /[\s，。！？、；：""''《》…—·.,!?;:"'()[\]{}]/g

function normalize(text: string): string {
  return (text ?? '').replace(NOISE, '')
}

/**
 * 一个可以被唤醒的**目标**：搭子，或群（现在群也能喊）。
 *
 * ## 为什么要 `kind` 而不是两个数组
 *
 * 撞词处理必须**跨两类一起判**（用户完全可能把群唤醒词和某个搭子配成一样），
 * 所以候选表只能是一份。`kind` 决定命中之后走哪条切换路径 —— 而两条路径的
 * **规则是刻意对齐的**（见 `services/groupSwitch.ts` 与 `assistantSwitch.ts`）：
 * 都是"切过去 + 落到它最近的那条对话"。
 */
interface WakeTarget {
  /**
   * 搭子 id 或群 id。
   *
   * ⚠️ 两类共用同一个命名空间：理论上一个群和一个搭子可以重名 id（后端各自的
   * 校验只保证"各自内部唯一"）。所以下面所有映射都必须**带上 kind 一起比**，
   * 不能只比 id —— 不然喊搭子可能切到同 id 的群上。
   */
  id: string
  kind: 'assistant' | 'group'
  words: string[]
}

/** 输入壳登记进来的"落点"：识别结果要写进哪个输入框。 */
export interface VoiceSink {
  getDraft: () => string
  setDraft: (text: string) => void
  /** 把待令内容真正发出去 */
  send: () => void | Promise<void>
}

interface VoiceSessionState {
  phase: VoicePhase
  level: number
  heard: string
  /** 最近命中的**那个词**（不是目标名）——界面只用来显示"唤醒了" */
  lastHit: string
  pending: string
  /**
   * 最近命中的**目标 id**（搭子或群）。
   *
   * ⚠️ 之前叫 `hitAssistantId`。加群之后它装的不再只是搭子，继续叫那个名字
   * 会让后续每一个读它的人都先猜一次"群里这个值是什么"。
   */
  hitTargetId: string | null
  /**
   * 当前在等哪一层的东西。
   *
   * ⚠️ 值从 `'assistant'` 改成了 `'standby'`（现在语音也能唤醒群）：
   * 那一层的候选词不再只有搭子的，说"各搭子自己的词"已经不准确。改成与
   * `phase` 同名的 `standby` 之后，两者说的是同一件事、也不会再被误读成
   * "只在单聊里生效"。
   */
  scope: 'global' | 'standby'
  /**
   * 语音设置面板开没开。
   *
   * ⚠️ 放在 store 而不是输入栏的局部 state：面板要**覆盖整个对话框**（长宽位置
   * 与它完全一致，产品要求），所以它得渲染在对话框那一层 —— 由输入栏持有这个
   * 布尔值的话，对话框拿不到它。
   */
  panelOpen: boolean
  setPanelOpen: (open: boolean) => void

  /**
   * 最近一次"打开麦克风"失败的原因（已翻译成人话）；`null` = 没失败。
   *
   * ⚠️ 为什么要进 store（第 103 批）：失败原先只在通知里闪一下就没，
   * 而**输入栏下方那条状态行恰恰在此时整块消失**（它只在 `phase !== 'off'` 时渲染）
   * —— 界面上于是既不显示状态、也不告诉用户该做什么，只剩"点了没反应"。
   */
  micError: string | null
  /**
   * 失败后的自救入口：停掉再重开麦克风。
   *
   * 有它之前，用户唯一能重新尝试的路径是"去语音设置面板改一下启动模式" ——
   * 谁也猜不到。现在状态行上就有一个「重试」。
   */
  retryMic: () => void
  /** 当前选定的录音设备 id（空串 = 系统默认）—— 语音设置面板那个下拉的选中值。 */
  micDeviceId: string
  /** 换一台录音设备：记住选择，并在麦克风正开着时**真的**用新设备重开。 */
  setMicDevice: (deviceId: string) => void
  /**
   * 上一次开麦时"选定的设备不在了、已自动回落系统默认"。
   *
   * 只为**说明**用（设置面板那一行显示"上次选的设备不在了，已用系统默认"）——
   * 不说的话，用户会觉得"我明明选的耳麦、它却在用别的"，或者反复遇到打不开。
   */
  micDeviceFellBack: boolean

  enable: () => void
  disable: () => void
  /** 彻底停掉麦克风 */
  shutdown: () => void
  /** 应用启动时按设置决定初始状态 */
  bootstrap: () => void
  discard: () => void
  /** 切搭子时清空语音侧对草稿的全部记忆（见实现处的说明） */
  resetDraft: () => void
}

// ---- 组件之外的可变状态 ---------------------------------------------------- //
//
// 这些刻意**不放进 zustand**：它们是采集回调读写的"句柄"，不是给界面看的状态。
// 塞进 store 会让每个音频分块都触发一次订阅通知。
let capture: VoiceCapture | null = null
/**
 * 采集的代数：`stopCapture()` 每次递增，`openCapture()` 进入时领一个号。
 *
 * ⚠️ 为什么需要它（第 103 批）：`openCapture` 里有一段 `await getUserMedia`，
 * 期间句柄还是 null —— 于是**并发**的第二次调用（用户连点两下「重试」、或快速连换
 * 两次设备）会各自打开一条流：先完成的那条既没被 stop 也没人引用 → 泄漏，
 * 而且两条流同时占着麦克风（正是这次要消灭的"抢设备"）。
 * 同理，用户在等待期间把语音关掉时，那次开麦 resolve 后会把麦克风又打开 ——
 * 表现为"明明关了，它还在听"。
 */
let captureEpoch = 0
let sink: VoiceSink | null = null
/**
 * 当前选定的录音设备 id（空串 = 系统默认）。
 *
 * 与 `capture` 一样放模块级：`openCapture` 每次都要用它，而采集回调不读它。
 *
 * ⚠️ 刚启动时它是空串，**必须先读一次偏好文件**（`ensureMicDeviceLoaded`）才能用 ——
 * 否则"用户上次选的耳麦"会在这台机器上失效，表现为"设了没用 / 记不住"。
 */
let micDeviceId = ''
/** 读偏好的 promise 缓存：启动与首次开麦可能并发，只走一次 IPC。 */
let micDevicePromise: Promise<void> | null = null
/**
 * 用户**手动选过设备**的代数。`0` = 还没选过。
 *
 * ⚠️ 存在的唯一理由：挡住"在途的偏好读取把用户刚选的设备盖回去"。
 * `bootstrap()` 发出一读就返回（不 await），而那次 IPC 可能排队几百毫秒 ——
 * 用户完全可能在这段时间里打开面板选好设备。不校验的话，那条读取 resolve 后会把
 * 磁盘上的**旧值**写回 `micDeviceId` 与界面，表现就是"选了又自己跳回去"。
 */
let micDeviceEpoch = 0

/** 读一次"上次选的麦克风"（顺带同步进 store，供设置面板的下拉显示）。 */
function ensureMicDeviceLoaded(): Promise<void> {
  micDevicePromise ??= readMicDeviceId().then((id) => {
    if (micDeviceEpoch !== 0) return // 用户已经手动选过了：以他的选择为准
    micDeviceId = id
    useVoiceSessionStore.setState({ micDeviceId: id })
  })
  return micDevicePromise
}

/**
 * 仅供测试：清掉"设备偏好已读"的缓存。
 *
 * 生产里这两个变量是**刻意的单例**（偏好读一次就够，`setMicDevice` 会同时更新它们），
 * 但单测每个用例都要从"还没读过偏好"的状态开始 —— 少了它，第二个用例会复用
 * 前一个用例读到的设备，测出来的东西与自己以为的不是一回事。
 */
export function resetMicDeviceCacheForTest(): void {
  micDeviceId = ''
  micDevicePromise = null
  // ⚠️ 代数也要一起清零：忘了它的话，前一个用例里"手动选过设备"的状态会留下来，
  // 后面用例的偏好读取会被静默跳过（表现为"回落用例莫名其妙走不到回落分支"）
  micDeviceEpoch = 0
}
let wakeWindow: Float32Array[] = []
let wakeFrames = 0
/** 进入录音那一刻的草稿：「取消」要能退回到它 */
let baseDraft = ''
/** 采集回调是异步的，读不到最新的 phase/pending —— 各留一份镜像 */
let phase: VoicePhase = 'off'
let pendingText = ''

function setPhase(next: VoicePhase): void {
  phase = next
  useVoiceSessionStore.setState({ phase: next })
}

/** 全局语音设置（未加载时给安全默认值，保证应用刚起来那一两秒也能用）。 */
function globalVoice() {
  return useAppStore.getState().settings?.voice
}

function globalWords(): { enable: string; disable: string } {
  const voice = globalVoice()
  return {
    enable: (voice?.enable_word ?? '').trim() || '开启语音',
    disable: (voice?.disable_word ?? '').trim() || '关闭语音',
  }
}

/**
 * 未唤醒时**不放行**的命令：会真的放行高危操作的那些。
 *
 * 由命令自己的 `dangerous` 标记算出来，不写死 id —— 以后新增的危险命令自动进来。
 */
const DANGEROUS_COMMAND_IDS = VOICE_COMMANDS.filter((item) => item.dangerous).map(
  (item) => item.id,
)

/**
 * 派发**界面命令**（未唤醒也允许的那批）。
 *
 * 「全局界面操作的层级应该和唤醒搭子是一样的」—— 以前没喊醒
 * 某个搭子时，说「打开设置」不会有任何反应，因为命令只在录音态才被派发。
 *
 * ⚠️ 设计稿的三层优先级**没变**（全局开关词 > 唤醒词 > 命令）：调用点只有两处 ——
 * `global` 层（听完两个开关词之后）与 `standby` 层的**唤醒词未命中时** ——
 * 所以"喊醒某个搭子"永远优先于"执行命令"。
 *
 * ⚠️ 危险命令（「开始执行」「允许执行」）**不放行**：它们会真的放行高危操作，
 * 多一道"先喊醒某个搭子"的门槛值得。排除方式是复用 `dispatch` 已有的
 * `disabled` 参数（它的语义本来就是"这批命令此刻不算数"），不新增任何机制。
 */
async function dispatchCommand(text: string): Promise<boolean> {
  const voice = globalVoice()
  const blocked = [...(voice?.disabled_commands ?? []), ...DANGEROUS_COMMAND_IDS]
  return useVoiceCommandStore.getState().dispatch(text, voice?.command_words ?? {}, blocked)
}

/** 当前参与唤醒的全部目标 —— **搭子与群**（现在群也能喊），
 *  且**当前主体排在最前**。
 *
 * ## 为什么必须固定"当前主体优先"
 *
 * 两个目标配了同一个唤醒词时，这句话该归谁**没有客观答案**。以前只有一个
 * 隐含顺序（列表顺序），撞了之后的表现就是"喊谁醒谁靠运气" —— 而那时我们
 * 的做法是**提示用户去改词**。
 *
 * 产品要求是：**这件事由后台处理掉，不要拿去烦用户**。
 * 所以改成挑一个确定性的、而且符合直觉的判据：**用户多半想找眼前这个**
 * —— 当前主体排最前，其余保持列表原序（`sort` 是稳定的）。
 *
 * 于是撞车既不报错也不提示，只是稳定地落到当前主体上。
 *
 * ## 为什么群要参与排序，而且用**同一个** currentId
 *
 * 加群之后"眼前那个"变得依赖页面：群聊页是当前群，其余页面是当前搭子。
 * 不看页面、或者只把搭子排前面，就会出现"在群里喊这个群的名字，却切到了
 * 另一个搭子"—— 因为群永远排在搭子后面。
 */
function listeningTargets(): WakeTarget[] {
  const { assistants, activeId } = useAssistantStore.getState()
  const { groups, selectedId } = useGroupStore.getState()
  const view = useAppStore.getState().view

  const targets: WakeTarget[] = [
    ...groups.map((group) => ({
      id: group.id,
      kind: 'group' as const,
      words: (group.wake_words ?? []).map((word) => word.trim()).filter(Boolean),
    })),
    ...assistants.map((profile) => ({
      id: profile.id,
      kind: 'assistant' as const,
      words: (profile.voice?.wake_words ?? []).map((word) => word.trim()).filter(Boolean),
    })),
  ].filter((item) => item.words.length > 0)

  // 群聊页的"眼前那个"是群，其余页面是搭子
  const currentId = view === 'groups' ? selectedId : activeId
  return targets.sort((a, b) => {
    if (a.id === currentId) return -1
    if (b.id === currentId) return 1
    return 0
  })
}

function notify(title: string, message: string, level: 'info' | 'warning' = 'warning'): void {
  useNotificationStore.getState().push({
    level,
    title,
    message,
    ...(level === 'info' ? { autoDismissMs: 8000 } : {}),
  })
}

function takeWindow(): Float32Array {
  const merged = new Float32Array(wakeFrames)
  let offset = 0
  for (const part of wakeWindow) {
    merged.set(part, offset)
    offset += part.length
  }
  return merged
}

function resetWindow(): void {
  wakeWindow = []
  wakeFrames = 0
}

function stopCapture(): void {
  // 递增代数：让**还在 await** 的那次 `openCapture` 作废（见 `captureEpoch` 的说明）
  captureEpoch += 1
  capture?.stop()
  capture = null
  resetWindow()
  useVoiceSessionStore.setState({ level: 0 })
}

/**
 * 按**当前选定的设备**开麦；若点名的设备不在了，回落系统默认**再试一次**。
 *
 * ⚠️ 为什么回落只能在"尝试之后"做（第 103 批）：`enumerateDevices()` 在**没有麦克风
 * 权限**时返回的 `deviceId` 是**空串**，所以"开麦前先枚举一遍校验"是不可靠的
 * （会把所有设备都判成"不在了"）。唯一可靠的信号是 `OverconstrainedError` ——
 * 它明确表示"点名的那个设备不存在"（见 `createCapture` 里 `exact` 的说明）。
 *
 * ⚠️ 回落时**把偏好也改回空**：否则每次启动都要先失败一次，用户感受到的是
 * "语音时好时坏"，而不是"上次选的麦不在了"。
 */
async function openCaptureWithFallback(
  handlers: Parameters<typeof createCapture>[0],
): Promise<VoiceCapture> {
  try {
    return await createCapture(handlers, { deviceId: micDeviceId })
  } catch (error) {
    const shouldFallBack =
      micDeviceId !== '' &&
      error instanceof CaptureError &&
      error.reason === 'OverconstrainedError'
    if (!shouldFallBack) throw error
    micDeviceId = ''
    // ⚠️ "已回落"这个标记与写偏好都放在**回落成功之后**：若系统默认也打不开，
    // 设置面板不该显示"已改用系统默认"（与事实不符，反而更难排查）。
    const opened = await createCapture(handlers, {})
    useVoiceSessionStore.setState({ micDeviceId: '', micDeviceFellBack: true })
    void writeMicDeviceId('')
    return opened
  }
}

/** 打开麦克风并进入某个待命层。已在跑时就只换等待目标（不重开设备）。 */
async function openCapture(entry: 'global' | 'standby'): Promise<void> {
  if (capture) {
    setPhase(entry)
    useVoiceSessionStore.setState({ scope: entry === 'global' ? 'global' : 'standby' })
    return
  }
  // 第一次开麦前把"上次选的麦克风"读进来（之后每次开麦都用模块里那份，不再走 IPC）。
  // ⚠️ 必须在 `createCapture` **之前**：设备 id 是开麦那一刻的入参，晚一步就变成
  // "这次先用系统默认、下次才生效" —— 用户会以为"选了没用"。
  await ensureMicDeviceLoaded()
  // 领一个"这次开麦"的号：等待期间若语音被关掉、或又发起了一次开麦，它就作废
  const epoch = ++captureEpoch
  try {
    const opened = await openCaptureWithFallback({
      onLevel: (value) => useVoiceSessionStore.setState({ level: value }),
      onSegment: (samples, rate) => void handleSegment(samples, rate),
      onError: (message) => {
        notify('语音输入中断', message)
        stopCapture()
        setPhase('off')
        // 采集是**跑起来之后**才断的（设备被拔走 / 被别的程序抢走）：与"打不开"同样处理
        // —— 状态行要留着原因并给「重试」，而不是只剩一条会自己消失的通知。
        useVoiceSessionStore.setState({ micError: message })
      },
    })
    // ⚠️ 等待期间语音可能已经被关掉、或被后一次开麦取代 —— 把刚拿到的这条流丢掉。
    // 不丢的话会出现"关掉之后麦克风又自己开了"，或者两条流同时占着设备。
    if (epoch !== captureEpoch) {
      opened.stop()
      return
    }
    capture = opened
  } catch (error) {
    // 过期的失败不该报给用户（他已经关掉或换过了，这时弹一条报错只会莫名其妙）
    if (epoch !== captureEpoch) return
    /*
      ⚠️ 这一步是**防御性**的，别指望它单独救场（第 103 批反向验证的结论）。

      失败时 `capture` 通常还是 `null` —— 赋值发生在 `await` **成功之后** ——
      所以"句柄残留成死流"其实到不了这个分支；真正兜住"还能再开一次"的是
      `retryMic()` / `setMicDevice()` 里那句**先 `stopCapture()` 再重开**。

      留着它的理由是另一条更少见的路径：`openCaptureWithFallback` 内部先拿到一条流、
      随后又抛错（回落也失败）时，句柄不会被赋值但 `audioWorklet` 那侧已经建好了 ——
      `stopCapture()` 会把这些资源一并收干净，顺带把在途代号推进（使任何还在 await 的
      那次开麦作废）。代价只有一次 `state.level = 0`。
    */
    stopCapture()
    const message = error instanceof Error ? error.message : '未知错误。'
    // 存进 store（不只是弹通知）：通知会消失，状态行要一直挂着它 + 一个重试入口
    useVoiceSessionStore.setState({ micError: message })
    notify('无法打开麦克风', message)
    setPhase('off')
    return
  }
  // 打开成功：清掉上一次的失败原因，状态行回到正常文案
  useVoiceSessionStore.setState({ micError: null })
  setPhase(entry)
  useVoiceSessionStore.setState({
    scope: entry === 'global' ? 'global' : 'standby',
    heard: '',
    lastHit: '',
  })
}

/** 一句话是不是等于某个词（先本地字面，不中再请核心按拼音判）。 */
async function matches(said: string, word: string): Promise<boolean> {
  const target = normalize(word)
  if (!target) return false
  if (normalize(said) === target) return true
  try {
    const result = await getApi().matchVoiceCommand(said, [{ id: 'w', word }])
    return result.id === 'w'
  } catch {
    return false
  }
}

async function recognize(samples: Float32Array, sampleRate: number): Promise<string> {
  try {
    const result = await getApi().voiceAsr(float32ToBase64(samples), sampleRate)
    return result.text.trim()
  } catch {
    return ''
  }
}

/**
 * 整句话是不是某个搭子/群的唤醒词（**第二层**，录音中也用它）。
 *
 * 与待命期那条路不同：那里送的是滑动窗口、问的是"这一段里有没有唤醒词"（可以
 * 只说半句）；这里要求**整句相等** —— 录音中用户就是单独喊一句名字来切换，
 * 而"帮我叫小助看一下"这种正文不该把人切走。
 *
 * 先本地字面，不中再请核心按拼音判（同音字是识别的常态）。
 */
async function matchWakeWord(text: string): Promise<WakeTarget | null> {
  const targets = listeningTargets()
  const pairs = targets.flatMap((item) =>
    item.words.map((word) => ({ id: item.id, kind: item.kind, word })),
  )
  if (pairs.length === 0) return null

  const said = normalize(text)
  if (!said) return null

  const literal = pairs.find((item) => normalize(item.word) === said)
  if (literal) return { id: literal.id, kind: literal.kind, words: [literal.word] }

  try {
    // 用下标当 id 传过去：核心只做"这句话等于哪个候选词"的判断，不需要知道
    // 那背后是搭子还是群 —— 映射关系留在这边，核心侧因此不必理解业务。
    const result = await getApi().matchVoiceCommand(
      said,
      pairs.map((item, index) => ({ id: String(index), word: item.word })),
    )
    if (result.id === null) return null
    const hit = pairs[Number(result.id)]
    return hit ? { id: hit.id, kind: hit.kind, words: [hit.word] } : null
  } catch {
    return null
  }
}

/**
 * 唤醒命中后切到那个目标（搭子或群），并把页面拉到它所在的页面。
 *
 * ## 为什么"清掉待令内容"这条要跨页面判
 *
 * 产品要求：「正在和 X 对话，却喊了别的 → 当前那个取消录入，切过去」。
 * 加群之后这个"别的"可能是**同一个 id 的另一类**，所以两样都要比 ——
 * 只比 id 的话，从群里喊到一个同 id 的搭子会被当成"没换人"，
 * 上一条群的待令内容就会跟着进到单聊输入框里。
 */
function switchToTarget(target: WakeTarget): void {
  const targetChanged =
    target.kind === 'group'
      ? useAppStore.getState().view !== 'groups' || useGroupStore.getState().selectedId !== target.id
      : useAppStore.getState().view === 'groups' ||
        useAssistantStore.getState().activeId !== target.id

  if (targetChanged) {
    pendingText = ''
    useVoiceSessionStore.setState({ pending: '' })
  }

  /*
    ⚠️ 落点交给 `switchGroup` / `switchAssistant` —— **必须与鼠标点击完全一致**：

      · 搭子 → 该搭子最近一次对话，没有则新开一条（`switchAssistant`）；
      · 群   → 该群最近有动静的那条对话（`switchGroup` → `selectGroup`）。

    两个函数的文件头都写着同一条铁律：点击与喊名字走同一条路。这里只负责
    "按 kind 分派"，**不自己碰会话/对话** —— 一旦在这里顺手做一次"如果没会话就
    新建"之类的兜底，就又多出一条会和点击分叉的路径。
  */
  if (target.kind === 'group') switchGroup(target.id)
  else switchAssistant(target.id)
}

/** 进入录音态。 */
function startRecording(): void {
  baseDraft = sink?.getDraft() ?? ''
  pendingText = ''
  useVoiceSessionStore.setState({ pending: '' })
  setPhase('listening')
}

/**
 * 处理一小段"说完了"的音频。**三层共用这一个入口**，按当前 phase 分流。
 *
 * ⚠️ 顺序不能乱：
 *   ① 全局层（「开启语音」/「关闭语音」）—— 优先级最高，**任何 phase 下都先查**，
 *      这样"正跟搭子说着话时喊关闭语音"才能立刻生效（产品明确要求）。
 *   ② 搭子层（唤醒词）—— 只在 standby，用最近几秒的滑动窗口。
 *   ③ 识别 → 命令 → 发送/取消/待令 —— 在 listening/awaiting。
 */
async function handleSegment(samples: Float32Array, sampleRate: number): Promise<void> {
  const wasRecording = phase === 'listening' || phase === 'awaiting'

  // 每一段都先识别一次 —— 三层都要拿这句话去比，只识别一次比"各层各识别一次"省得多
  const said = await recognize(samples, sampleRate)
  const cleaned = normalize(said)
  if (cleaned) useVoiceSessionStore.setState({ heard: said })

  // ===== 第一层：全局指令 =====
  //
  // ⚠️ 优先级**最高**，且**任何状态都先查**（产品要求：
  //    "关闭语音"要凌驾于所有正在进行的搭子对话之上）。
  //    原先这里只在 global/standby 下检查，于是"正跟搭子说着话"时喊关闭语音拦不住
  //    —— 那正是实测反馈问题。
  if (cleaned) {
    const words = globalWords()
    if (await matches(said, words.disable)) {
      useVoiceSessionStore.getState().disable()
      return
    }
    if (await matches(said, words.enable)) {
      notify('语音已开启', '现在可以喊搭子了 —— 叫到哪个搭子就切到哪个。', 'info')
      await openCapture('standby')
      return
    }
  }

  // 全局层只等上面那两个词（已经查过）。
  //
  // ⚠️ 原来这里是直接 `return` —— 于是"开着语音、还没喊搭子"时说「打开设置」
  // 没有任何反应实测反馈正是这个）。现在多试一次**界面命令**。
  // 仍然**不做"识别写草稿"**：正文要有落点，而落点属于某个被唤醒的主体 ——
  // 这也正是"命令能免唤醒、闲聊不能"的边界。
  if (phase === 'global') {
    if (cleaned) await dispatchCommand(said)
    return
  }

  // ===== 第二层：唤醒词 =====
  // 待命态下用滑动窗口查（用户说「你好…搭子」中间带停顿时，窗口能救回来）
  if (phase === 'standby') {
    wakeWindow.push(samples)
    let frames = wakeFrames + samples.length
    const maxFrames = (WAKE_WINDOW_MS * sampleRate) / 1000
    while (wakeWindow.length > 1 && frames > maxFrames) {
      const oldest = wakeWindow.shift()
      if (!oldest) break
      frames -= oldest.length
    }
    wakeFrames = frames

    const targets = listeningTargets()
    const words = targets.flatMap((item) => item.words)
    if (words.length === 0) return

    const { hit, text } = await getApi().voiceWake(
      float32ToBase64(takeWindow()),
      sampleRate,
      words,
    )
    useVoiceSessionStore.setState({ heard: text || '' })
    if (!hit) {
      // 唤醒词没中 —— 也可能说的是一句**界面命令**（不唤醒搭子
      // 也要能操作界面）。刻意排在唤醒词**之后**：设计稿的三层优先级里唤醒优先于
      // 命令，喊到谁就该切到谁，不能被一条同名的命令抢走。
      //
      // 用 `said`（这一段音频的整体识别）而不是 `text`（唤醒窗口那几秒的识别）：
      // 命令是独立一句说完的，整段更完整。
      if (cleaned) await dispatchCommand(said)
      return
    }

    // ⚠️ 谁先命中就归谁 —— 用 `listeningTargets()` 的顺序（当前主体排在最前，
    // 见它的实现），而不是"哪个目标的唤醒词数组里先出现"。
    //
    // 这么排是因为**唤醒词撞车必然会有人喊错人**：两个目标配了同一个词时，
    // 谁是"对的那个"没有客观答案，唯一有意义的判据是"用户多半想找眼前这个"。
    // 产品要求"后台把这个处理掉、不要拿去烦用户"，所以撞车既不报错也不提示，
    // 而是按这个确定性的顺序落位。
    const owner = targets.find((item) => item.words.includes(hit))
    resetWindow()
    useVoiceSessionStore.setState({ lastHit: hit, hitTargetId: owner?.id ?? null })
    if (owner) switchToTarget(owner)
    startRecording()
    return
  }

  if (!wasRecording) return

  if (!cleaned) {
    setPhase(pendingText ? 'awaiting' : 'listening')
    return
  }

  // ===== 第二层（录音中同样生效）：唤醒**别的**搭子 / 群 =====
  //
  // 产品要求：「正在和一个搭子对话，却喊了别的搭子 → 当前搭子取消录入，切过去」。
  // 所以说话过程中也要认唤醒词 —— 不是只有待命态才认。
  const owner = await matchWakeWord(said)
  if (owner) {
    useVoiceSessionStore.setState({ lastHit: owner.words[0] ?? '', hitTargetId: owner.id })
    // `switchToTarget` 里会把待令内容清掉（"当前那个取消录入"）
    switchToTarget(owner)
    startRecording()
    return
  }

  // ===== 第三层：语音命令 / 发送 / 取消 / 待令 =====
  const voice = globalVoice()

  // 语音命令优先于正文：「开始执行」要触发那个按钮，而不是发一条叫这个名字的消息
  const handled = await useVoiceCommandStore
    .getState()
    .dispatch(said, voice?.command_words ?? {}, voice?.disabled_commands ?? [])
  if (handled) {
    setPhase(pendingText ? 'awaiting' : 'listening')
    return
  }

  if (await matches(said, (voice?.send_word ?? '').trim() || '发送')) {
    const outgoing = pendingText.trim()
    if (!outgoing) {
      setPhase('listening')
      return
    }
    if (useChatStore.getState().streaming) {
      // 搭子还在说：不插话，待令内容**留着**（等它说完再说一次「发送」）
      setPhase('awaiting')
      return
    }
    pendingText = ''
    useVoiceSessionStore.setState({ pending: '' })
    await sink?.send()
    setPhase('listening')
    return
  }

  if (await matches(said, (voice?.cancel_word ?? '').trim() || '取消')) {
    pendingText = ''
    useVoiceSessionStore.setState({ pending: '' })
    sink?.setDraft(baseDraft)
    setPhase('listening')
    return
  }

  // 攒进待令时用**原始识别文本**（`said`），不是 `cleaned`：标点要留着，
  // 否则用户说的话会被拼成一大串没有断句的文字。
  pendingText = `${pendingText}${said}`
  useVoiceSessionStore.setState({ pending: pendingText })
  /*
    ⚠️ 写输入框时**接在他当前文本的后面**，而不是把 `pendingText` 整段盖上去 ——
    这是实测反馈那个 bug：他转完文字手动改了几个字，继续说，改动就被
    整段抹掉，只能取消重来（"这样体验很差"）。

    根因：`pendingText` 里只有**语音识别出来的字**，从来不含他手改的内容，
    而这里以前写的是 `setDraft(pendingText)` —— 一次写入就是整个输入框替换。

    为什么"接在末尾"是对的：识别是**增量**的（每段只返回新说的那一段，
    见后端 `voice/asr.py`），所以把新说的接到现有文本后面，既不丢他改的字，
    也不丢刚说的话。他要是先删掉几个识别错的字再继续说，那个删除同样保得住 ——
    这正是"继续说"最自然的期待。
  */
  const current = sink?.getDraft() ?? ''
  sink?.setDraft(`${current}${said}`)
  setPhase('awaiting')
}

export const useVoiceSessionStore = create<VoiceSessionState>((set, get) => ({
  phase: 'off',
  level: 0,
  heard: '',
  lastHit: '',
  pending: '',
  hitTargetId: null,
  scope: 'global',
  panelOpen: false,
  micError: null,
  micDeviceId: '',
  micDeviceFellBack: false,

  setPanelOpen: (open) => set({ panelOpen: open }),

  enable: () => {
    resetWindow()
    void openCapture('standby')
  },

  disable: () => {
    // "关闭整个语音功能" = 回到全局层。麦克风继续开着等「开启语音」——
    // 这是用户明确要的：关完之后不必再去点界面才能回来。
    pendingText = ''
    resetWindow()
    set({ pending: '', lastHit: '', hitTargetId: null })
    if (capture) {
      setPhase('global')
      set({ scope: 'global' })
      return
    }
    void openCapture('global')
  },

  shutdown: () => {
    pendingText = ''
    stopCapture()
    setPhase('off')
    // 主动关掉不算"失败"：留着上一条错误，状态行会挂着一句与当前状态无关的告警
    set({ scope: 'global', heard: '', lastHit: '', hitTargetId: null, micError: null })
  },

  bootstrap: () => {
    // 把"上次选的麦克风"读到 store 里（设置面板那个下拉的选中值要靠它）。
    // **不 await**：采集那条路自己会 `ensureMicDeviceLoaded()`，这里只影响下拉的
    // 初始显示，为它拖慢启动不值得（与 appStore 读 `closeAction` 同一口径）。
    void ensureMicDeviceLoaded()
    const mode = globalVoice()?.startup_mode ?? 'global'
    if (mode === 'off') {
      get().shutdown()
      return
    }
    void openCapture(mode === 'all' ? 'standby' : 'global')
  },

  /**
   * 换一台录音设备。
   *
   * ⚠️ 开着麦时必须**真的重开**，不能只改下拉的显示值：用户换设备就是为了立刻用上它
   * （选错了也要马上发现）。重开沿用当前所在的那一层（`standby` / 正在录音 = 留在
   * 待命层；其余一律回 `global`）—— 不能让"换个麦"把用户一脚踢回未唤醒状态。
   *
   * ⚠️ 没开麦时只记不改：下次 `bootstrap` / `retryMic` 自然会用上新的那个。
   */
  setMicDevice: (deviceId) => {
    micDeviceId = deviceId
    // 记下"用户手动选过了"：在途的偏好读取回来时会据此放弃写回（否则会把刚选的盖掉）
    micDeviceEpoch += 1
    micDevicePromise = Promise.resolve()
    // 用户重新选过了：把"回落过"的说明清掉（它描述的是上一次的情况）
    set({ micDeviceId: deviceId, micDeviceFellBack: false })
    void writeMicDeviceId(deviceId)
    if (!capture) return
    /*
      ⚠️ 层级映射要**保住录音流程**：`listening`/`recognizing`/`awaiting` 都属于
      "已经在跟用户对话"，换设备必须留在待命层。原先只判了 `standby`/`listening`，
      于是用户在**待令**（已经攒了内容、输入框里有字）时换麦克风会被一脚踢回 `global` ——
      那层只认开关词，`pendingText` 再也发不出去，用户已经说出的内容就卡死在输入框里。
    */
    const target: 'global' | 'standby' =
      phase !== 'off' && phase !== 'global' ? 'standby' : 'global'
    resetWindow()
    stopCapture()
    void openCapture(target)
  },

  /**
   * 失败后的自救：**先停掉再重开**。
   *
   * ⚠️ 必须先 `stopCapture()`："采集跑起来之后才断"那条路径（设备被拔走）会留下一个
   * **已经死掉的流**，而 `openCapture` 开头的 `if (capture)` 会据此判定"已经在跑"、
   * 只换等待目标 —— 于是用户点重试**什么也没发生**。顺带清掉滑动窗口：
   * 里面装的是上一台设备的音频，换设备/重开之后没有意义。
   *
   * ⚠️ `startup_mode === 'off'`（用户把语音总开关关了）时不重开：那没有意义，
   * 状态行会引导他去语音设置里开启。
   */
  retryMic: () => {
    resetWindow()
    stopCapture()
    const mode = globalVoice()?.startup_mode ?? 'global'
    if (mode === 'off') {
      setPhase('off')
      return
    }
    void openCapture(mode === 'all' ? 'standby' : 'global')
  },

  discard: () => {
    pendingText = ''
    set({ pending: '' })
    sink?.setDraft(baseDraft)
  },

  /**
   * 清空语音侧关于"当前草稿"的全部记忆。**切搭子时必须调。**
   *
   * 与 `discard` 的区别：`discard` 是"用户说取消"—— 它把草稿**退回**到进入录音时
   * 的样子（`baseDraft`），因为用户只是不要刚说的那半句；而这里是"换人了"，
   * 上一位搭子的草稿、待令内容、基准点**一个都不该留下**。
   *
   * ⚠️ 不清 `baseDraft` 会出很怪的事：切搭子后说「取消」，草稿会退回到**上一个
   * 搭子**那边的内容。实测反馈"切回来依然无法继续发送"就是这个的后遗症 ——
   * 写入与回退的基准错位之后，每一次操作对的都是另一份账。
   */
  resetDraft: () => {
    baseDraft = ''
    pendingText = ''
    set({ pending: '' })
    sink?.setDraft('')
  },
}))

/**
 * 把当前输入框登记为"识别结果的落点"。
 *
 * ⚠️ 必须成对（挂载登记、卸载注销）：不然窗口切走之后，识别结果会继续写进一个
 * **已经不在屏幕上**的输入框 —— 用户看不到那些字，也删不掉，只会觉得"它把话吃了"。
 */
export function useVoiceSink(value: VoiceSink | null): void {
  const latest = useRef(value)
  latest.current = value
  const absent = value === null

  useEffect(() => {
    if (absent) {
      sink = null
      return
    }
    // 包一层：调用时总是走 ref 里最新的那份（send/setDraft 通常是内联函数，
    // 每次渲染都是新引用，直接登记会导致"每次渲染都注销再登记"）
    sink = {
      getDraft: () => latest.current?.getDraft() ?? '',
      setDraft: (text) => latest.current?.setDraft(text),
      send: () => latest.current?.send() as void,
    }
    return () => {
      sink = null
    }
  }, [absent])
}
