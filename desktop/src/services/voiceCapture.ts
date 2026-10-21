




























const SPEECH_RATIO = 2.5

const MIN_SPEECH_RMS = 0.006

const NOISE_FLOOR_INIT = 0.004

const SILENCE_MS = 800

const MIN_SPEECH_MS = 350

const CHUNK_MS = 100

const MAX_SEGMENT_MS = 60_000

const TARGET_RATE = 16_000







const SCRIPT_BUFFER_FRAMES = 1024








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
  
  onLevel?: (level: number) => void
  
  onSpeechStart?: () => void
  
  onSegment: (samples: Float32Array, sampleRate: number) => void
  onError?: (message: string) => void
}

export interface VoiceCapture {
  start: () => Promise<void>
  stop: () => void
  
  level: () => number
}

function rms(chunk: Float32Array): number {
  let sum = 0
  for (let i = 0; i < chunk.length; i += 1) sum += chunk[i] * chunk[i]
  return Math.sqrt(sum / Math.max(chunk.length, 1))
}


export function float32ToBase64(samples: Float32Array): string {
  const bytes = new Uint8Array(samples.buffer, samples.byteOffset, samples.byteLength)
  let binary = ''
  
  const STEP = 0x8000
  for (let i = 0; i < bytes.length; i += STEP) {
    binary += String.fromCharCode(...bytes.subarray(i, i + STEP))
  }
  return btoa(binary)
}


function describeCaptureError(error: unknown): string {
  const name = (error as { name?: string } | null)?.name ?? ''
  switch (name) {
    case 'NotAllowedError':
    case 'SecurityError':
      return '麦克风被拒绝。请在系统设置 → 隐私 → 麦克风里允许本应用。'
    





    case 'OverconstrainedError':
      return '上次选的麦克风不在了（可能已拔掉或换了接口）。请在语音设置里重新选择设备，或改用系统默认。'
    case 'NotFoundError':
      
      
      return '没有找到可用的麦克风设备。请插好麦克风后点「重试」，或到系统设置里检查输入设备。'
    case 'NotReadableError':
      return '麦克风被别的程序占用了，关掉它再试；也可以点「重试」，或在语音设置里换一个设备。'
    default:
      return `无法打开麦克风（${name || '未知错误'}）。可点「重试」，或到系统设置里检查输入设备。`
  }
}


export interface AudioInput {
  deviceId: string
  label: string
}










export class CaptureError extends Error {
  constructor(
    message: string,
    
    readonly reason: string,
  ) {
    super(message)
    this.name = 'CaptureError'
  }
}









let inputsCache: AudioInput[] | null = null







export async function listAudioInputs(): Promise<AudioInput[]> {
  if (inputsCache) return inputsCache
  if (!navigator.mediaDevices?.enumerateDevices) return []
  try {
    const devices = await navigator.mediaDevices.enumerateDevices()
    inputsCache = devices
      .filter((item) => item.kind === 'audioinput')
      .map((item, index) => ({
        deviceId: item.deviceId,
        
        label: item.label || `麦克风 ${index + 1}`,
      }))
    return inputsCache
  } catch {
    return []
  }
}


export function resetAudioInputsCache(): void {
  inputsCache = null
}

if (typeof navigator !== 'undefined' && navigator.mediaDevices) {
  navigator.mediaDevices.addEventListener?.('devicechange', () => {
    inputsCache = null
  })
}









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
        









        ...(options?.deviceId ? { deviceId: { exact: options.deviceId } } : {}),
        channelCount: 1,
        echoCancellation: true, 
        noiseSuppression: true,
        autoGainControl: true,
      },
    })
  } catch (error) {
    
    
    
    
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
        
        
        `origin=${globalThis.location?.origin ?? '(unknown)'}`,
      )
    }
  } else {
    console.warn('[voice] 当前环境没有 AudioWorklet，降级到 ScriptProcessorNode')
  }

  if (!node) {
    
    
    const mute = context.createGain()
    mute.gain.value = 0
    scriptNode = context.createScriptProcessor(SCRIPT_BUFFER_FRAMES, 1, 1)
    scriptNode.connect(mute)
    mute.connect(context.destination)
  }

  const source = context.createMediaStreamSource(stream)
  
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
    if (durationMs < MIN_SPEECH_MS) return 

    const merged = new Float32Array(total)
    let offset = 0
    for (const part of parts) {
      merged.set(part, offset)
      offset += part.length
    }
    handlers.onSegment(merged, rate)
  }

  










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

  






  const handleChunk = (chunk: Float32Array): void => {
    if (stopped) return
    const level = rms(chunk)
    
    
    currentLevel = Math.min(1, level * 12)
    handlers.onLevel?.(currentLevel)

    
    
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
        
        scriptNode?.disconnect()
      } catch {
        
      }
      for (const track of stream.getTracks()) track.stop()
      void context.close()
    },
    level: () => currentLevel,
  }
}
