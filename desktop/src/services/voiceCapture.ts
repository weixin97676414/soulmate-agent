/**
 * 麦克风采集：拿到 16kHz 单声道 Float32，并在本地判断"说完了"。
 *
 * ## 为什么不用 MediaRecorder
 *
 * 它给的是 webm/opus **压缩流**，要识别就得在核心装解码器（ffmpeg / librosa /
 * soundfile 一整套）。而 Web Audio 直接就能给裸 PCM —— 两端都干净，核心因此
 * 一个音频解码库都不需要。
 *
 * ## 为什么 VAD 放在前端
 *
 * - 核心因此不需要流式会话：**一段一请求**，说完才发一次，失败还能整段重试；
 * - 音量波形和"在听"的即时反馈本来就要实时画，本地算 RMS 才有那个手感。
 *
 * ## 采样率
 *
 * 直接向 AudioContext 要 16000Hz（Chromium 会自己重采样），省掉手写降采样。
 * 万一设备不支持，浏览器给什么就用什么 —— 核心那边实测会自动重采样
 * （喂 22050Hz 进去它自己转），所以**把真实采样率如实传过去**就行。
 */

/**
 * 判定"有人在说话"：**高于底噪多少倍**算说话。
 *
 * 为什么不是写死的绝对值：麦克风增益差得很远（笔记本内置麦与外置声卡能差十倍），
 * 写死 0.02 在一台机器上"说什么都触发"、在另一台上"喊破嗓子也不触发"。
 * 我们按每条流的实际底噪自适应 —— 第一次实测就栽在这里：用户能看到波形在抖，
 * 但音量始终没越过那条线，于是一个请求都没发出去，界面一直停在"在听唤醒词"。
 */
const SPEECH_RATIO = 2.5
/** 绝对下限。防止在**极安静**的环境里把呼吸、鼠标声都当成说话。 */
const MIN_SPEECH_RMS = 0.006
/** 底噪基线的初值（留给第一帧之前用，很快就会被实测值取代）。 */
const NOISE_FLOOR_INIT = 0.004
/** 多长的静音算"这一段说完了"。800ms 是"停顿"与"说完了"的分界，短了会切碎句子。 */
const SILENCE_MS = 800
/** 短于这个时长的片段直接丢掉（咳嗽、敲键盘、翻页声）。 */
const MIN_SPEECH_MS = 350
/** 累积到多少毫秒往主线程发一次。太小消息风暴，太大波形会一顿一顿。 */
const CHUNK_MS = 100
/** 单段上限，防止用户对着麦克风放音乐把内存吃干。 */
const MAX_SEGMENT_MS = 60_000

const TARGET_RATE = 16_000

/**
 * 降级路径（`ScriptProcessorNode`）的块大小，单位帧。
 *
 * 1024 帧 @16k ≈ 64ms，与 worklet 那条路的 100ms 同一量级 —— 换路不该让
 * 断句手感变样。取值必须是 256 的 2 的幂（该 API 只接受固定几档）。
 */
const SCRIPT_BUFFER_FRAMES = 1024

/**
 * 跑在音频线程里的小处理器。
 *
 * 内联成字符串 + Blob URL，而不是放 `public/` 下一个独立文件：那样子路径在
 * 开发与打包后会不一样（vite 的 base 不同），一个 404 会让麦克风**静默不工作**。
 * 内联就没有这个失败模式。
 */
const WORKLET_SOURCE = `
class CaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this.buffer = []
    this.count = 0
    // ⚠️ 用 worklet 全局的 sampleRate，而不是我们**请求**的 16000 —— 浏览器有权
    // 忽略那个请求（Windows 上共享模式常锁在 48k）。若按 16000 算，实际跑在 48k 时
    // "攒够 1600 帧"只有 33ms，而主线程仍按 100ms 记静音时长 → 静音判定快三倍，
    // 用户话还没说完就被切段，识别出来的永远是半句。
    this.chunkFrames = Math.max(128, Math.round((sampleRate * ${CHUNK_MS}) / 1000))
  }
  process(inputs) {
    const channel = inputs[0] && inputs[0][0]
    if (!channel) return true
    // 攒够再发：每 128 帧发一次消息（约 8ms）对主线程太吵
    this.buffer.push(new Float32Array(channel))
    this.count += channel.length
    if (this.count >= this.chunkFrames) {
      const merged = new Float32Array(this.count)
      let offset = 0
      for (const part of this.buffer) {
        merged.set(part, offset)
        offset += part.length
      }
      this.port.postMessage(merged, [merged.buffer])
      this.buffer = []
      this.count = 0
    }
    return true
  }
}
registerProcessor('voice-capture', CaptureProcessor)
`

export interface CaptureHandlers {
  /** 实时音量（0~1 左右），用来画波形。 */
  onLevel?: (level: number) => void
  /** 从静音变成有声：界面上可以切成"在听"。 */
  onSpeechStart?: () => void
  /** 一段说完了，交出这段波形。`sampleRate` 是**真实**采样率，别假设 16000。 */
  onSegment: (samples: Float32Array, sampleRate: number) => void
  onError?: (message: string) => void
}

export interface VoiceCapture {
  start: () => Promise<void>
  stop: () => void
  /** 当前音量，画波形用。 */
  level: () => number
}

function rms(chunk: Float32Array): number {
  let sum = 0
  for (let i = 0; i < chunk.length; i += 1) sum += chunk[i] * chunk[i]
  return Math.sqrt(sum / Math.max(chunk.length, 1))
}

/** 把 float32 波形编码成 base64（核心那边按 `<f4` 解）。 */
export function float32ToBase64(samples: Float32Array): string {
  const bytes = new Uint8Array(samples.buffer, samples.byteOffset, samples.byteLength)
  let binary = ''
  // 分块拼接：一次 apply 十万级参数会爆栈
  const STEP = 0x8000
  for (let i = 0; i < bytes.length; i += STEP) {
    binary += String.fromCharCode(...bytes.subarray(i, i + STEP))
  }
  return btoa(binary)
}

/** 把浏览器抛的权限/设备错误翻译成用户看得懂的话。 */
function describeCaptureError(error: unknown): string {
  const name = (error as { name?: string } | null)?.name ?? ''
  switch (name) {
    case 'NotAllowedError':
    case 'SecurityError':
      return '麦克风被拒绝。请在系统设置 → 隐私 → 麦克风里允许本应用。'
    /*
      ⚠️ 这两个原本合成一句话，第 103 批拆开：它们要用户做的事**完全不同**。
      `OverconstrainedError` 只会在"点名了某个设备、而那个设备不在了"时出现
      （见 `createCapture` 里 deviceId 用 `exact` 的说明）—— 那时用户要做的是
      **重选设备**，而不是像 `NotFoundError` 那样去"插一个麦克风"。
    */
    case 'OverconstrainedError':
      return '上次选的麦克风不在了（可能已拔掉或换了接口）。请在语音设置里重新选择设备，或改用系统默认。'
    case 'NotFoundError':
      // ⚠️ 这几条都要给出**下一步**（第 103 批）：它们会**常驻**显示在输入栏下方那块
      // 失败提示里（通知会自己消失，那块不会），只说"没找到设备"用户只能干看着
      return '没有找到可用的麦克风设备。请插好麦克风后点「重试」，或到系统设置里检查输入设备。'
    case 'NotReadableError':
      return '麦克风被别的程序占用了，关掉它再试；也可以点「重试」，或在语音设置里换一个设备。'
    default:
      return `无法打开麦克风（${name || '未知错误'}）。可点「重试」，或到系统设置里检查输入设备。`
  }
}

/** 下拉里的一项录音设备。 */
export interface AudioInput {
  deviceId: string
  label: string
}

/**
 * 采集失败。`message` 是**给人看的那句话**，`reason` 是浏览器给的原始错误名。
 *
 * ⚠️ 为什么要把原始名带出来（第 103 批）：调用方需要据此区分"该不该回落默认设备"
 * —— `OverconstrainedError` 表示**点名的那个设备不在了**（见 `createCapture` 里
 * `deviceId` 用 `exact` 的说明），那时正确的动作是改用系统默认**重试一次**；
 * 而 `NotAllowedError`（被拒绝）重试多少次都一样，必须让用户去隐私设置。
 * 光靠 `message` 去匹配中文是不可靠的。
 */
export class CaptureError extends Error {
  constructor(
    message: string,
    /** 浏览器抛的原始错误名（`NotAllowedError` / `NotReadableError` / `OverconstrainedError` …） */
    readonly reason: string,
  ) {
    super(message)
    this.name = 'CaptureError'
  }
}

/**
 * 设备列表缓存。
 *
 * ⚠️ 必须缓存，并且必须能在**权限状态变化**时失效：没有麦克风权限时
 * `enumerateDevices()` 返回的 `label` **全是空串**，拿到权限之后才有名字。
 * 不失效的话用户会看到一排空白选项（而他并不知道那要先授权）。
 * 所以下面挂了一个 `devicechange` 监听 —— 授权、插拔、切换默认设备都会触发它。
 */
let inputsCache: AudioInput[] | null = null

/**
 * 列出可用的录音设备。
 *
 * ⚠️ 一个都没有时返回**空数组**而不是抛错：调用方据此只显示"系统默认"，
 * 不该因为枚举不到设备就让整个语音设置面板打不开。
 */
export async function listAudioInputs(): Promise<AudioInput[]> {
  if (inputsCache) return inputsCache
  if (!navigator.mediaDevices?.enumerateDevices) return []
  try {
    const devices = await navigator.mediaDevices.enumerateDevices()
    inputsCache = devices
      .filter((item) => item.kind === 'audioinput')
      .map((item, index) => ({
        deviceId: item.deviceId,
        // 没权限时 label 是空串 —— 给个占位名，不然下拉里是一排空白
        label: item.label || `麦克风 ${index + 1}`,
      }))
    return inputsCache
  } catch {
    return []
  }
}

/** 仅供测试：清掉设备缓存（生产路径由 `devicechange` 负责失效）。 */
export function resetAudioInputsCache(): void {
  inputsCache = null
}

if (typeof navigator !== 'undefined' && navigator.mediaDevices) {
  navigator.mediaDevices.addEventListener?.('devicechange', () => {
    inputsCache = null
  })
}

/**
 * 打开麦克风并开始断句。
 *
 * 失败一律**明确报错**，绝不静默退回系统识别 —— 那会让用户以为语音还能用，
 * 实际上音频可能已经出了本机（这正是这套本地识别要替换掉的东西）。
 *
 * `options.deviceId` 为空/不传 = 用**系统默认**设备（用户没在下拉里选过就是这条）。
 */
export async function createCapture(
  handlers: CaptureHandlers,
  options?: { deviceId?: string },
): Promise<VoiceCapture> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new CaptureError('当前环境不支持麦克风采集。', 'UnsupportedError')
  }

  let stream: MediaStream
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        /*
          ⚠️ `deviceId` 用 **`exact`** 而不是宽松匹配（第 103 批）。

          用户在下拉里点名了某个设备，就该**要么用它、要么明确报错**。宽松匹配会在
          那个设备不在时静默换一个 —— 于是"我明明选了耳麦，实际却在用笔记本内置麦"，
          而且从界面上看不出来。`exact` 失败时抛 `OverconstrainedError`，
          正好对应"你选的那个设备不在了"这句人话（见 `describeCaptureError`）。

          不传 / 空串 = **不带这个约束**，交给系统默认设备。
        */
        ...(options?.deviceId ? { deviceId: { exact: options.deviceId } } : {}),
        channelCount: 1,
        echoCancellation: true, // 免提外放时不开会把搭子的声音也录进来
        noiseSuppression: true,
        autoGainControl: true,
      },
    })
  } catch (error) {
    // ⚠️ 诊断留痕（第 103 批）：只弹一句"无法打开麦克风"的话，用户和我们都看不出
    // 到底是被占用、没设备、还是被系统拒绝 —— 而这三者的处置动作完全不同
    // （关掉占用的程序 / 插回设备 / 去隐私设置放行）。日志只记错误类型与选定的设备，
    // **不落任何音频内容、不落设备指纹**。
    console.error('[voice] getUserMedia 失败', {
      name: (error as { name?: string } | null)?.name,
      message: error instanceof Error ? error.message : String(error),
      deviceId: options?.deviceId || '(系统默认)',
    })
    throw new CaptureError(
      describeCaptureError(error),
      (error as { name?: string } | null)?.name ?? '',
    )
  }

  const context = new AudioContext({ sampleRate: TARGET_RATE })

  /*
    ---- 采集的两条路（第 103 批）----

    优先 `AudioWorklet`（跑在音频线程，不占主线程）。但它有个**彻底失败**的模式：
    `audioWorklet.addModule(blob:…)` 在部分环境下直接抛
    `Unable to load a worklet's module.`（用户实测截图报的就是这条），而它一失败
    **语音就整个不能用**。

    所以失败时降级到 `ScriptProcessorNode`：这个 API 已被标记废弃、性能也差一档
    （`onaudioprocess` 跑在主线程），但"能听见用户说话"比"用最新 API"重要得多。

    ⚠️ 降级**必须留痕**（`console.warn`）：本项目对"静默降级"零容忍 ——
    悄悄换一条更差的路，以后所有音频问题都会变得无法解释、也没人知道该查哪条。

    ⚠️ blob URL **不再 revoke**：它要在工作线程真正取到时还活着。原先在 `finally`
    里立刻 revoke —— 而 `addModule` 的取用时机不由我们控制，这本身就是嫌疑之一。
    一条几十行脚本的常驻代价可以忽略，不值得为它冒"语音整个用不了"的风险。
  */
  let node: AudioWorkletNode | null = null
  let scriptNode: ScriptProcessorNode | null = null

  if (context.audioWorklet) {
    const moduleUrl = URL.createObjectURL(
      new Blob([WORKLET_SOURCE], { type: 'application/javascript' }),
    )
    try {
      await context.audioWorklet.addModule(moduleUrl)
      node = new AudioWorkletNode(context, 'voice-capture')
    } catch (error) {
      console.warn(
        '[voice] AudioWorklet 加载失败，降级到 ScriptProcessorNode：',
        (error as { name?: string } | null)?.name,
        (error as { message?: string } | null)?.message,
        // ⚠️ 安全访问：这行只是诊断信息，不该因为拿不到 location（测试 / 非浏览器环境）
        // 而把整个 catch 变成一次新异常
        `origin=${globalThis.location?.origin ?? '(unknown)'}`,
      )
    }
  } else {
    console.warn('[voice] 当前环境没有 AudioWorklet，降级到 ScriptProcessorNode')
  }

  if (!node) {
    // ⚠️ 必须串一个**增益为 0** 的节点再连 destination：`ScriptProcessorNode`
    // 只有被拉到 destination 才会被驱动，而直连会把麦克风原声从扬声器放出来（啸叫）。
    const mute = context.createGain()
    mute.gain.value = 0
    scriptNode = context.createScriptProcessor(SCRIPT_BUFFER_FRAMES, 1, 1)
    scriptNode.connect(mute)
    mute.connect(context.destination)
  }

  const source = context.createMediaStreamSource(stream)
  // 不接 destination：接了会把麦克风原声从扬声器放出来（啸叫）
  const sink: AudioNode | null = node ?? scriptNode
  if (!sink) {
    throw new CaptureError(
      '语音采集无法启动（音频工作线程与降级通道都不可用）。',
      'AudioNodeUnavailable',
    )
  }
  source.connect(sink)

  let speaking = false
  let silenceMs = 0
  let currentLevel = 0
  /** 底噪基线（自适应，见 SPEECH_RATIO 的说明）。 */
  let noiseFloor = NOISE_FLOOR_INIT
  let pending: Float32Array[] = []
  let pendingLen = 0
  let stopped = false

  const rate = context.sampleRate

  const reset = () => {
    speaking = false
    silenceMs = 0
    pending = []
    pendingLen = 0
  }

  const flush = () => {
    const total = pendingLen
    const durationMs = (total * 1000) / rate
    const parts = pending
    reset()
    if (durationMs < MIN_SPEECH_MS) return // 太短：多半是噪声，不是话

    const merged = new Float32Array(total)
    let offset = 0
    for (const part of parts) {
      merged.set(part, offset)
      offset += part.length
    }
    handlers.onSegment(merged, rate)
  }

  /*
    ---- 设备中途消失（第 103 批补）----

    ⚠️ 为什么必须有这两条监听：拔掉 USB 麦 / 蓝牙断连 / 设备被别的程序独占时，
    `getUserMedia` **不会**抛错，之后也**不会**再有音频块 —— 于是界面一直显示
    "在听"，实际什么也听不到。这正是这个 store 文件头警告过的"静默失败"，
    而它此前只会表现为"喊半天没反应"，用户与我们都查不出原因。

    ⚠️ 只在 `stopped === false` 时报：用户**主动** `stop()` 时 track 结束、
    context 关闭都是正常的，报出来会变成"每次关语音都弹一条错误"。
  */
  const reportInterrupted = (reason: string): void => {
    if (stopped) return
    stopped = true
    handlers.onError?.(reason)
  }

  const track = stream.getAudioTracks()[0]
  if (track) {
    track.onended = () => {
      reportInterrupted('麦克风已断开（设备被拔掉、或已被其它程序占用）。')
    }
  }
  context.onstatechange = () => {
    if (context.state === 'closed') reportInterrupted('麦克风采集已中止。')
  }

  /**
   * 一个音频块进来（两条采集路径**共用**）。
   *
   * worklet 那条是块通过 `postMessage` 过来，降级那条是 `onaudioprocess` 直接给。
   * VAD 与断句逻辑只该有一份 —— 两条路各写一遍的话，迟早会长成"worklet 下正常、
   * 降级后断句变样"这类只在部分用户机器上出现的问题。
   */
  const handleChunk = (chunk: Float32Array): void => {
    if (stopped) return
    const level = rms(chunk)
    // ×12：正常说话 RMS 只有 0.05 上下，不放大波形几乎是平的一条直线，
    // 用户会以为"麦克风没工作"。放大到能看到明显起伏，但不至于满格糊住。
    currentLevel = Math.min(1, level * 12)
    handlers.onLevel?.(currentLevel)

    // 底噪自适应：只在"当前听着安静"时更新，且**慢慢升、立刻降** ——
    // 慢升是为了不被一次咳嗽带跑，快降是为了说完话后马上恢复基准。
    if (level < noiseFloor * SPEECH_RATIO) {
      noiseFloor = level < noiseFloor ? level : noiseFloor * 0.95 + level * 0.05
    }
    const speakingThreshold = Math.max(MIN_SPEECH_RMS, noiseFloor * SPEECH_RATIO)

    if (level > speakingThreshold) {
      if (!speaking) {
        speaking = true
        handlers.onSpeechStart?.()
      }
      silenceMs = 0
      pending.push(chunk)
      pendingLen += chunk.length
    } else if (speaking) {
      // 尾部静音也留着：切在最后一个音节上会让识别丢掉尾字
      pending.push(chunk)
      pendingLen += chunk.length
      silenceMs += CHUNK_MS
      if (silenceMs >= SILENCE_MS) flush()
    }

    if ((pendingLen * 1000) / rate > MAX_SEGMENT_MS) flush()
  }

  if (node) {
    node.port.onmessage = (event: MessageEvent<Float32Array>) => handleChunk(event.data)
  } else if (scriptNode) {
    scriptNode.onaudioprocess = (event: AudioProcessingEvent) => {
      // ⚠️ 必须**拷一份**：`getChannelData` 返回的是**复用**缓冲，下一次回调就会把它
      // 改写。不拷贝的话送进识别的是"说话过程中随机的一块"，听起来像乱码。
      handleChunk(new Float32Array(event.inputBuffer.getChannelData(0)))
    }
  }

  await context.resume()

  return {
    start: async () => {
      if (context.state === 'suspended') await context.resume()
    },
    stop: () => {
      stopped = true
      node?.port.close()
      if (scriptNode) scriptNode.onaudioprocess = null
      try {
        source.disconnect()
        node?.disconnect()
        // 降级那条路还要断开增益节点：它一直连着 destination，不断会拖着音频图不释放
        scriptNode?.disconnect()
      } catch {
        /* 已经断开 */
      }
      for (const track of stream.getTracks()) track.stop()
      void context.close()
    },
    level: () => currentLevel,
  }
}
