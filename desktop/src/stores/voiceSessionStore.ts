














































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


const WAKE_WINDOW_MS = 3000

const NOISE = /[\s，。！？、；：""''《》…—·.,!?;:"'()[\]{}]/g

function normalize(text: string): string {
  return (text ?? '').replace(NOISE, '')
}











interface WakeTarget {
  






  id: string
  kind: 'assistant' | 'group'
  words: string[]
}


export interface VoiceSink {
  getDraft: () => string
  setDraft: (text: string) => void
  
  send: () => void | Promise<void>
}

interface VoiceSessionState {
  phase: VoicePhase
  level: number
  heard: string
  
  lastHit: string
  pending: string
  





  hitTargetId: string | null
  







  scope: 'global' | 'standby'
  






  panelOpen: boolean
  setPanelOpen: (open: boolean) => void

  






  micError: string | null
  





  retryMic: () => void
  
  micDeviceId: string
  
  setMicDevice: (deviceId: string) => void
  





  micDeviceFellBack: boolean

  enable: () => void
  disable: () => void
  
  shutdown: () => void
  
  bootstrap: () => void
  discard: () => void
  
  resetDraft: () => void
}





let capture: VoiceCapture | null = null










let captureEpoch = 0
let sink: VoiceSink | null = null








let micDeviceId = ''

let micDevicePromise: Promise<void> | null = null








let micDeviceEpoch = 0


function ensureMicDeviceLoaded(): Promise<void> {
  micDevicePromise ??= readMicDeviceId().then((id) => {
    if (micDeviceEpoch !== 0) return 
    micDeviceId = id
    useVoiceSessionStore.setState({ micDeviceId: id })
  })
  return micDevicePromise
}








export function resetMicDeviceCacheForTest(): void {
  micDeviceId = ''
  micDevicePromise = null
  
  
  micDeviceEpoch = 0
}
let wakeWindow: Float32Array[] = []
let wakeFrames = 0

let baseDraft = ''

let phase: VoicePhase = 'off'
let pendingText = ''

function setPhase(next: VoicePhase): void {
  phase = next
  useVoiceSessionStore.setState({ phase: next })
}


function globalVoice() {
  return useAppStore.getState().settings?.voice
}

function globalWords(): { enable: string; disable: string } {
  const voice = globalVoice()
  return {
    enable: (voice?.enable_word ?? '').trim() || '打开语音',
    disable: (voice?.disable_word ?? '').trim() || '关闭语音',
  }
}






const DANGEROUS_COMMAND_IDS = VOICE_COMMANDS.filter((item) => item.dangerous).map(
  (item) => item.id,
)















async function dispatchCommand(text: string): Promise<boolean> {
  const voice = globalVoice()
  const blocked = [...(voice?.disabled_commands ?? []), ...DANGEROUS_COMMAND_IDS]
  return useVoiceCommandStore.getState().dispatch(text, voice?.command_words ?? {}, blocked)
}






















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
  
  captureEpoch += 1
  capture?.stop()
  capture = null
  resetWindow()
  useVoiceSessionStore.setState({ level: 0 })
}












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
    
    
    const opened = await createCapture(handlers, {})
    useVoiceSessionStore.setState({ micDeviceId: '', micDeviceFellBack: true })
    void writeMicDeviceId('')
    return opened
  }
}


async function openCapture(entry: 'global' | 'standby'): Promise<void> {
  if (capture) {
    setPhase(entry)
    useVoiceSessionStore.setState({ scope: entry === 'global' ? 'global' : 'standby' })
    return
  }
  
  
  
  await ensureMicDeviceLoaded()
  
  const epoch = ++captureEpoch
  try {
    const opened = await openCaptureWithFallback({
      onLevel: (value) => useVoiceSessionStore.setState({ level: value }),
      onSegment: (samples, rate) => void handleSegment(samples, rate),
      onError: (message) => {
        notify('语音输入中断', message)
        stopCapture()
        setPhase('off')
        
        
        useVoiceSessionStore.setState({ micError: message })
      },
    })
    
    
    if (epoch !== captureEpoch) {
      opened.stop()
      return
    }
    capture = opened
  } catch (error) {
    
    if (epoch !== captureEpoch) return
    











    stopCapture()
    const message = error instanceof Error ? error.message : '未知错误。'
    
    useVoiceSessionStore.setState({ micError: message })
    notify('无法打开麦克风', message)
    setPhase('off')
    return
  }
  
  useVoiceSessionStore.setState({ micError: null })
  setPhase(entry)
  useVoiceSessionStore.setState({
    scope: entry === 'global' ? 'global' : 'standby',
    heard: '',
    lastHit: '',
  })
}


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

  









  if (target.kind === 'group') switchGroup(target.id)
  else switchAssistant(target.id)
}


function startRecording(): void {
  baseDraft = sink?.getDraft() ?? ''
  pendingText = ''
  useVoiceSessionStore.setState({ pending: '' })
  setPhase('listening')
}










async function handleSegment(samples: Float32Array, sampleRate: number): Promise<void> {
  const wasRecording = phase === 'listening' || phase === 'awaiting'

  
  const said = await recognize(samples, sampleRate)
  const cleaned = normalize(said)
  if (cleaned) useVoiceSessionStore.setState({ heard: said })

  
  
  
  
  
  
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

  
  
  
  
  
  
  if (phase === 'global') {
    if (cleaned) await dispatchCommand(said)
    return
  }

  
  
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
      
      
      
      
      
      
      if (cleaned) await dispatchCommand(said)
      return
    }

    
    
    
    
    
    
    
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

  
  
  
  
  const owner = await matchWakeWord(said)
  if (owner) {
    useVoiceSessionStore.setState({ lastHit: owner.words[0] ?? '', hitTargetId: owner.id })
    
    switchToTarget(owner)
    startRecording()
    return
  }

  
  const voice = globalVoice()

  
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
      
      setPhase('awaiting')
      return
    }
    pendingText = ''
    useVoiceSessionStore.setState({ pending: '' })
    await sink?.send()
    setPhase('listening')
    return
  }

  if (await matches(said, (voice?.cancel_word ?? '').trim() || '清空')) {
    pendingText = ''
    useVoiceSessionStore.setState({ pending: '' })
    sink?.setDraft(baseDraft)
    setPhase('listening')
    return
  }

  
  
  
  
  
  
  
  if (useChatStore.getState().streaming) {
    setPhase(pendingText ? 'awaiting' : 'listening')
    return
  }

  
  
  pendingText = `${pendingText}${said}`
  useVoiceSessionStore.setState({ pending: pendingText })
  












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
    
    set({ scope: 'global', heard: '', lastHit: '', hitTargetId: null, micError: null })
  },

  bootstrap: () => {
    
    
    
    void ensureMicDeviceLoaded()
    const mode = globalVoice()?.startup_mode ?? 'global'
    if (mode === 'off') {
      get().shutdown()
      return
    }
    void openCapture(mode === 'all' ? 'standby' : 'global')
  },

  








  setMicDevice: (deviceId) => {
    micDeviceId = deviceId
    
    micDeviceEpoch += 1
    micDevicePromise = Promise.resolve()
    
    set({ micDeviceId: deviceId, micDeviceFellBack: false })
    void writeMicDeviceId(deviceId)
    if (!capture) return
    





    const target: 'global' | 'standby' =
      phase !== 'off' && phase !== 'global' ? 'standby' : 'global'
    resetWindow()
    stopCapture()
    void openCapture(target)
  },

  










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

  










  resetDraft: () => {
    baseDraft = ''
    pendingText = ''
    set({ pending: '' })
    sink?.setDraft('')
  },
}))







export function useVoiceSink(value: VoiceSink | null): void {
  const latest = useRef(value)
  latest.current = value
  const absent = value === null

  useEffect(() => {
    if (absent) {
      sink = null
      return
    }
    
    
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
