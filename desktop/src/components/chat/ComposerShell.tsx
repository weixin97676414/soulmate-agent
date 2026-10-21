import clsx from 'clsx'
import {
  AlertCircle,
  CornerDownLeft,
  Download,
  FolderPlus,
  Loader2,
  Mic,
  Paperclip,
  Square,
  SquarePen,
  X,
} from 'lucide-react'
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from 'react'

import { SlashCommandPanel, type PaletteItem } from '@/components/chat/SlashCommandPanel'


import { formatSpeed } from '@/components/ModelDownloadCard'
import {
  MAX_FILES,
  collectFromDataTransfer,
  collectFromFileList,
  hasDirectory,
  type CollectResult,
} from '@/lib/folderUpload'
import { VoiceGuide, markVoiceGuideSeen, voiceGuideSeen } from '@/components/chat/VoiceGuide'
import { useCurrentGroup } from '@/lib/currentSubject'
import { VOICE_COMMAND_BY_ID, commandWord } from '@/services/voiceCommands'
import { useVoiceCommand } from '@/stores/voiceCommandStore'
import { useVoiceSessionStore, useVoiceSink } from '@/stores/voiceSessionStore'
import { useVoiceStore } from '@/stores/voiceStore'
import { useAppStore } from '@/stores/appStore'
import { useAssistantStore } from '@/stores/assistantStore'
import { useGroupStore } from '@/stores/groupStore'
import { useModelHubStore } from '@/stores/modelHubStore'
import { useNotificationStore } from '@/stores/notificationStore'
import type { PendingAttachment } from '@/types'

const MAX_HEIGHT = 200

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}








function ImageThumb({ id }: { id: string }) {
  const api = useAppStore((state) => state.api)
  const [url, setUrl] = useState<string | null>(null)

  useEffect(() => {
    if (!api) return
    let cancelled = false
    let objectUrl: string | null = null

    void (async () => {
      try {
        const blob = await api.fetchFileBlob(id, 'upload')
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      } catch {
        
      }
    })()

    return () => {
      cancelled = true
      
      
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [api, id])

  if (!url) {
    return <div className="h-full w-full animate-pulse bg-hover" />
  }
  return <img src={url} alt="待发送图片" className="h-full w-full object-cover" />
}







function ImageTiles({
  attachments,
  onRemove,
}: {
  attachments: PendingAttachment[]
  onRemove: (id: string) => void
}) {
  const images = attachments.filter((item) => item.kind === 'image')
  if (images.length === 0) return null

  return (
    <div className="mb-2 flex flex-wrap gap-2">
      {images.map((item) => (
        <div key={item.id} className="group relative">
          <div
            title={item.error ?? item.name}
            className={clsx(
              'h-[62px] w-[62px] overflow-hidden rounded-[8px] border',
              item.status === 'error' ? 'border-danger/40' : 'border-line',
            )}
          >
            {item.status === 'uploading' ? (
              <div className="flex h-full w-full items-center justify-center bg-panel">
                <Loader2 size={14} className="animate-spin text-brand" />
              </div>
            ) : item.status === 'error' ? (
              <div className="flex h-full w-full items-center justify-center bg-danger-soft">
                <AlertCircle size={14} className="text-danger" />
              </div>
            ) : (
              <ImageThumb id={item.id} />
            )}
          </div>
          <button
            type="button"
            onClick={() => onRemove(item.id)}
            aria-label={`移除 ${item.name}`}
            className="no-drag absolute -top-1.5 -right-1.5 flex h-4 w-4 items-center justify-center rounded-full border border-line bg-canvas text-ink-soft opacity-0 transition-opacity group-hover:opacity-100 hover:text-ink focus:opacity-100"
          >
            <X size={10} />
          </button>
        </div>
      ))}
    </div>
  )
}

function AttachmentChips({
  attachments,
  onRemove,
}: {
  attachments: PendingAttachment[]
  onRemove: (id: string) => void
}) {
  
  const files = attachments.filter((item) => item.kind === 'file')
  if (files.length === 0) return null

  return (
    <div className="mb-2 flex flex-wrap gap-1.5">
      {files.map((item) => (
        <div
          key={item.id}
          title={item.error ?? item.name}
          className={clsx(
            'group flex max-w-[240px] items-center gap-1.5 rounded-[8px] border px-2 py-1 text-[12px]',
            item.status === 'error'
              ? 'border-danger/30 bg-danger-soft text-danger'
              : 'border-line bg-panel text-ink-soft',
          )}
        >
          {item.status === 'uploading' ? (
            <Loader2 size={11} className="shrink-0 animate-spin text-brand" />
          ) : item.status === 'error' ? (
            <AlertCircle size={11} className="shrink-0" />
          ) : (
            <Paperclip size={11} className="shrink-0" />
          )}
          <span className="min-w-0 flex-1 truncate text-ink">{item.name}</span>
          <span className="shrink-0 text-[10.5px] text-ink-faint">
            {item.status === 'error' ? '失败' : formatSize(item.size)}
          </span>
          <button
            type="button"
            onClick={() => onRemove(item.id)}
            aria-label={`移除 ${item.name}`}
            className="no-drag flex h-4 w-4 shrink-0 items-center justify-center rounded-[4px] text-ink-faint hover:bg-canvas hover:text-ink"
          >
            <X size={11} />
          </button>
        </div>
      ))}
    </div>
  )
}

export interface ComposerShellProps {
  
  value: string
  onChange: (value: string) => void
  
  onSubmit: () => void | Promise<void>
  
  busy: boolean
  onStop?: () => void
  placeholder: string
  
  attachments: PendingAttachment[]
  onFiles: (files: File[]) => void | Promise<void>
  onRemoveAttachment: (id: string) => void
  






  paletteOpen?: boolean
  paletteItems?: PaletteItem[]
  paletteEmptyText?: string
  onPaletteSelect?: (item: PaletteItem) => void
  
  showVoiceInput?: boolean
  
  toolbarLeft?: ReactNode
  
  onNewSession?: () => void
  





  hint?: ReactNode
  
  footerNote?: ReactNode
  








  footerLeft?: ReactNode
  footerCenter?: ReactNode
  footerRight?: ReactNode
  
  className?: string
}



















export function ComposerShell({
  value,
  onChange,
  onSubmit,
  busy,
  onStop,
  placeholder,
  attachments,
  onFiles,
  onRemoveAttachment,
  paletteOpen = false,
  paletteItems = [],
  paletteEmptyText = '没有匹配的命令',
  onPaletteSelect,
  showVoiceInput = true,
  toolbarLeft,
  onNewSession,
  hint,
  footerNote,
  footerLeft,
  footerCenter,
  footerRight,
  className,
}: ComposerShellProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const folderInputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)

  
  
  
  
  
  const availability = useVoiceStore((state) => state.availability)
  










  const isMainWindow = (() => {
    const mode = window.agentBridge?.getWindowArgs?.()?.mode
    return mode !== 'chat' && mode !== 'group'
  })()
  
  
  
  
  
  
  
  
  











  const voiceEntryVisible = showVoiceInput
  const canRecord = availability?.asr === true

  









  const modelHubLoaded = useModelHubStore((state) => state.loaded)
  const voiceModelEntry = useModelHubStore((state) => state.models.voice)
  const voiceModelBusy = useModelHubStore((state) => state.busy.voice === true)
  const startVoiceModel = useModelHubStore((state) => state.start)
  const cancelVoiceModel = useModelHubStore((state) => state.cancel)
  const voiceModelMissing = modelHubLoaded && !voiceModelEntry?.installed
  const voiceModelRunning = voiceModelEntry?.state === 'running'
  
  
  const voiceModelPercent = Math.min(
    100,
    Math.round(((voiceModelEntry?.done_bytes ?? 0) * 100) / (voiceModelEntry?.total_bytes || 1)),
  )
  const voiceModelSpeed = voiceModelRunning ? formatSpeed(voiceModelEntry?.speed ?? 0) : ''

  










  const backendReady = useAppStore((state) => state.backendStatus.state === 'ready')
  useEffect(() => {
    if (showVoiceInput && isMainWindow && backendReady) {
      void useVoiceStore.getState().refresh()
    }
  }, [showVoiceInput, isMainWindow, backendReady])

  
  const submitRef = useRef<() => void>(() => {})
  
  
  const voiceSendingRef = useRef(false)

  const phase = useVoiceSessionStore((state) => state.phase)
  const scope = useVoiceSessionStore((state) => state.scope)
  const heard = useVoiceSessionStore((state) => state.heard)
  const level = useVoiceSessionStore((state) => state.level)
  
  
  const micError = useVoiceSessionStore((state) => state.micError)
  const retryMic = useVoiceSessionStore((state) => state.retryMic)

  








  const globalVoice = useAppStore((state) => state.settings?.voice)
  const activeAssistantProfile = useAssistantStore((state) =>
    state.assistants.find((item) => item.id === state.activeId),
  )
  







  const activeGroup = useCurrentGroup()
  const wakeWords = activeGroup
    ? activeGroup.wake_words
    : (activeAssistantProfile?.voice?.wake_words ?? globalVoice?.wake_words)

  
  
  useVoiceSink(
    useMemo(
      () => ({
        getDraft: () => value,
        setDraft: onChange,
        send: async () => {
          voiceSendingRef.current = true
          try {
            
            
            
            await new Promise((resolve) => {
              window.setTimeout(resolve, 0)
            })
            submitRef.current()
          } finally {
            voiceSendingRef.current = false
          }
        },
      }),
      [value, onChange],
    ),
  )

  
  
  
  
  useVoiceCommand('chat.stop', busy && onStop ? () => void onStop() : null)
  useVoiceCommand('chat.new', onNewSession ? () => onNewSession() : null)

  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  const activeAssistantId = useAssistantStore((state) => state.activeId)
  const activeThreadId = useGroupStore((state) => state.activeThreadId)
  const subjectKey = activeGroup
    ? `group:${activeGroup.id}:${activeThreadId ?? ''}`
    : `assistant:${activeAssistantId ?? ''}`
  const firstAssistantRef = useRef(true)
  useEffect(() => {
    
    if (firstAssistantRef.current) {
      firstAssistantRef.current = false
      return
    }
    
    useVoiceSessionStore.getState().resetDraft()
    onChange('')
    
    
    
  }, [subjectKey])

  
  
  
  
  
  
  
  
  
  const voiceActive = Boolean(showVoiceInput) && isMainWindow && phase !== 'off'
  const recording = phase === 'listening' || phase === 'recognizing' || phase === 'awaiting'
  const [guideOpen, setGuideOpen] = useState(false)
  
  
  const panelOpen = useVoiceSessionStore((state) => state.panelOpen)
  const setPanelOpen = useVoiceSessionStore((state) => state.setPanelOpen)

  const toggleMic = () => {
    
    
    
    
    if (!voiceGuideSeen()) setGuideOpen(true)
    setPanelOpen(!panelOpen)
  }

  useEffect(() => {
    const element = textareaRef.current
    if (!element) return
    element.style.height = 'auto'
    element.style.height = `${Math.min(element.scrollHeight, MAX_HEIGHT)}px`
  }, [value])

  const uploading = attachments.some((item) => item.status === 'uploading')
  





  const [queued, setQueued] = useState(false)
  
  
  const onSubmitRef = useRef(onSubmit)
  onSubmitRef.current = onSubmit

  useEffect(() => {
    if (!queued || uploading) return
    setQueued(false)
    
    if (attachments.some((item) => item.status === 'error')) return
    void onSubmitRef.current()
  }, [queued, uploading, attachments])

  
  const paletteActive = paletteOpen && paletteItems.length > 0

  
  
  useEffect(() => {
    setActiveIndex(0)
  }, [paletteItems.length])

  const submit = () => {
    
    
    
    
    
    
    
    void voiceSendingRef.current
    if (busy) return
    if (uploading) {
      
      setQueued((prev) => !prev)
      return
    }
    void onSubmit()
  }
  
  submitRef.current = submit

  const pickFiles = (files: FileList | File[] | null) => {
    const list = files ? Array.from(files) : []
    if (list.length) void onFiles(list)
  }

  





  const applyCollected = (result: CollectResult) => {
    if (result.skipped.length || result.truncated) {
      const head = result.truncated
        ? `一次最多发送 ${MAX_FILES} 个文件，多出来的没有加入。`
        : '有些文件没有加入。'
      const detail = result.skipped
        .slice(0, 5)
        .map((item) => `${item.name}（${item.reason}）`)
        .join('、')
      const more = result.skipped.length > 5 ? ` 等共 ${result.skipped.length} 个` : ''
      useNotificationStore.getState().push({
        level: 'warning',
        title: '部分文件没有加入',
        message: `${head}${detail ? `\n跳过的：${detail}${more}` : ''}`,
        
        autoDismissMs: 0,
      })
    }
    if (result.files.length) pickFiles(result.files)
  }

  const selectPalette = (item: PaletteItem | undefined) => {
    if (!item) return
    onPaletteSelect?.(item)
    setActiveIndex(0)
  }

  const onKeyDown = (event: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    
    if (paletteActive) {
      if (event.key === 'ArrowDown') {
        event.preventDefault()
        setActiveIndex((index) => (index + 1) % paletteItems.length)
        return
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault()
        setActiveIndex((index) => (index - 1 + paletteItems.length) % paletteItems.length)
        return
      }
      if (event.key === 'Escape') {
        event.preventDefault()
        setActiveIndex(0)
        return
      }
      
      if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
        event.preventDefault()
        selectPalette(paletteItems[activeIndex] ?? paletteItems[0])
        return
      }
    }
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <div
      className={clsx(
        
        'shrink-0 rounded-[12px] border border-line bg-panel px-4 pt-3 pb-3',
        










        '@container',
        className,
      )}
    >
      {
}
      <div className="relative mx-auto w-full">
        {



}
        {guideOpen ? (
          <VoiceGuide
            enableWord={(globalVoice?.enable_word ?? '').trim() || '打开语音'}
            disableWord={(globalVoice?.disable_word ?? '').trim() || '关闭语音'}
            
            
            wakeWord={(wakeWords ?? [])[0] ?? (activeGroup ? '你好群聊' : '你好搭子')}
            sendWord={(globalVoice?.send_word ?? '').trim() || '发送'}
            cancelWord={(globalVoice?.cancel_word ?? '').trim() || '清空'}
            
            
            
            confirmWord={commandWord(
              VOICE_COMMAND_BY_ID['confirm.allow'],
              globalVoice?.command_words ?? {},
            )}
            rejectWord={commandWord(
              VOICE_COMMAND_BY_ID['confirm.reject'],
              globalVoice?.command_words ?? {},
            )}
            onClose={() => {
              markVoiceGuideSeen()
              setGuideOpen(false)
            }}
          />
        ) : null}

        {paletteOpen ? (
          <SlashCommandPanel
            items={paletteItems}
            activeIndex={activeIndex}
            emptyText={paletteEmptyText}
            onPick={selectPalette}
            onHover={setActiveIndex}
          />
        ) : null}

        <ImageTiles attachments={attachments} onRemove={onRemoveAttachment} />
        <AttachmentChips attachments={attachments} onRemove={onRemoveAttachment} />

        {}
        <div
          onDragOver={(event) => {
            
            event.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault()
            setDragging(false)
            
            
            
            if (hasDirectory(event.dataTransfer)) {
              void collectFromDataTransfer(event.dataTransfer).then(applyCollected)
              return
            }
            pickFiles(event.dataTransfer.files)
          }}
          className={clsx(
            'rounded-[14px] border bg-canvas px-3 pt-2.5 pb-2 transition-colors',
            dragging ? 'border-brand bg-brand-soft/40' : 'border-line focus-within:border-brand',
          )}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            hidden
            onChange={(event) => {
              pickFiles(event.target.files)
              
              event.target.value = ''
            }}
          />
          {}
          <input
            ref={folderInputRef}
            type="file"
            hidden
            {...({ webkitdirectory: 'true', directory: 'true' } as Record<string, string>)}
            onChange={(event) => {
              applyCollected(collectFromFileList(event.target.files))
              event.target.value = ''
            }}
          />

          <textarea
            ref={textareaRef}
            rows={1}
            value={value}
            
            
            
            aria-label="输入消息"
            placeholder={dragging ? '松开以添加附件或文件夹' : placeholder}
            onChange={(event) => onChange(event.target.value)}
            onPaste={(event) => {
              const files = Array.from(event.clipboardData.files)
              if (files.length) {
                event.preventDefault()
                pickFiles(files)
              }
            }}
            onKeyDown={onKeyDown}
            className="max-h-[200px] min-h-[26px] w-full resize-none bg-transparent py-1 text-[13.5px] leading-relaxed text-ink placeholder:text-ink-faint focus:outline-none"
          />

          {}
          <div className="mt-1 flex items-center gap-1">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              title="添加附件"
              aria-label="添加附件"
              className="no-drag flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] text-ink-faint hover:bg-hover hover:text-ink"
            >
              <Paperclip size={15} />
            </button>

            {}
            <button
              type="button"
              onClick={() => folderInputRef.current?.click()}
              title="添加整个文件夹"
              aria-label="添加整个文件夹"
              className="no-drag flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] text-ink-faint hover:bg-hover hover:text-ink"
            >
              <FolderPlus size={15} />
            </button>

            {onNewSession ? (
              <button
                type="button"
                onClick={onNewSession}
                title="开启新对话 (Ctrl+N)"
                aria-label="开启新对话"
                className="no-drag flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] text-ink-faint hover:bg-hover hover:text-ink"
              >
                <SquarePen size={15} />
              </button>
            ) : null}

            {toolbarLeft}

            <span className="min-w-2 flex-1" />

            {voiceEntryVisible ? (
              <button
                type="button"
                onClick={toggleMic}
                title={
                  canRecord
                    ? panelOpen
                      ? '收起语音设置'
                      : '打开语音设置'
                    : '语音模型未下载 —— 点这里去设置里下载'
                }
                
                aria-label={canRecord ? '语音设置' : '语音设置（语音模型未下载）'}
                aria-pressed={panelOpen}
                className={clsx(
                  'no-drag relative flex h-8 shrink-0 items-center gap-1.5 rounded-[8px] px-2 text-[12px]',
                  




















                  !canRecord
                    ? 'border border-dashed border-line text-ink-faint hover:bg-hover hover:text-ink'
                    : phase === 'global' || phase === 'standby'
                      ? 'bg-brand-soft text-brand'
                      : recording
                        ? 'bg-success-soft text-success'
                        : 'text-ink-faint hover:bg-hover hover:text-ink',
                )}
              >
                {






}
                {phase === 'recognizing' ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Mic size={14} />
                )}
                <span>语音设置</span>
                {










}
                {voiceActive ? (
                  <span
                    className="pointer-events-none absolute inset-0 rounded-[8px] bg-current"
                    style={{ opacity: 0.08 + level * 0.5 }}
                  />
                ) : null}
              </button>
            ) : null}

            {busy ? (
              <button
                type="button"
                onClick={() => onStop?.()}
                title="停止生成"
                className="no-drag flex h-8 items-center gap-1.5 rounded-[8px] border border-line px-2.5 text-[12.5px] text-ink-soft hover:bg-hover hover:text-ink"
              >
                <Square size={12} className="fill-current" />
                停止
              </button>
            ) : (
              <button
                type="button"
                onClick={submit}
                
                
                
                disabled={!value.trim() && attachments.length === 0}
                title={
                  uploading && queued
                    ? '附件上传中，传完自动发送'
                    : uploading
                      ? '附件上传中，点一下可以排队发送'
                      : value.trim() || attachments.length === 0
                        ? '发送 (Enter)'
                        : '发送附件 (Enter)'}
                className="no-drag flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] bg-brand text-white transition-opacity disabled:bg-brand/35"
              >
                {uploading && queued ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <CornerDownLeft size={14} />
                )}
              </button>
            )}
          </div>
        </div>

        {



}
        {voiceActive ? (
          <div
            className={clsx(
              'mt-1.5 flex items-center gap-2 rounded-[8px] px-2.5 py-1.5 text-[11.5px] leading-relaxed',
              phase === 'awaiting' ? 'bg-brand-soft text-brand' : 'bg-canvas text-ink-faint',
            )}
          >
            {
}
            <span
              className={clsx(
                'h-1.5 w-1.5 shrink-0 rounded-full',
                recording ? 'bg-success' : 'bg-brand',
              )}
              style={phase === 'listening' ? { opacity: 0.4 + level * 0.6 } : undefined}
            />
            <span>
              {phase === 'global'
                ? 
                  
                  `在等「${(globalVoice?.enable_word ?? '打开语音').trim() || '打开语音'}」…${heard ? ` 刚听到「${heard}」` : ''}`
                : phase === 'standby'
                  ? 
                    
                    
                    `在听唤醒词（${scope === 'standby' ? '各搭子与各群自己的词' : '—'}）…${heard ? ` 刚听到「${heard}」` : ''}`
                  : phase === 'recognizing'
                    ? '正在识别…'
                    : phase === 'awaiting'
                      ? busy
                        ? `等它说完再说「${globalVoice?.send_word ?? '发送'}」发出（内容已留住）· 说「${globalVoice?.cancel_word ?? '清空'}」放弃`
                        : `说「${globalVoice?.send_word ?? '发送'}」发出 · 说「${globalVoice?.cancel_word ?? '清空'}」放弃`
                      : '我在听，说完停顿一下…'}
            </span>
          </div>
        ) : null}

        {
















}
        {voiceEntryVisible && isMainWindow && voiceModelMissing ? (
          <div className="mt-1.5 flex items-center gap-2 rounded-[8px] bg-canvas px-2.5 py-1.5 text-[11.5px] leading-relaxed text-ink-faint">
            <Download size={13} className="shrink-0" aria-hidden="true" />
            <span className="shrink-0">
              {}
              {voiceModelRunning ? '正在下载语音模型…' : '语音模型未下载'}
            </span>
            {voiceModelRunning ? (
              <>
                <div
                  role="progressbar"
                  aria-valuenow={voiceModelPercent}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  



                  aria-label={`语音模型下载进度 ${voiceModelPercent}%${
                    voiceModelSpeed ? `，${voiceModelSpeed}` : ''
                  }`}
                  className="h-1 w-24 shrink-0 overflow-hidden rounded-full bg-brand-soft"
                >
                  <div
                    className="h-full rounded-full bg-brand transition-[width] duration-150 ease-out motion-reduce:transition-none"
                    style={{ width: `${voiceModelPercent}%` }}
                  />
                </div>
                <span className="shrink-0 tabular-nums">{voiceModelPercent}%</span>
                {voiceModelSpeed ? (
                  <span className="shrink-0 tabular-nums">{voiceModelSpeed}</span>
                ) : null}
              </>
            ) : null}
            <span className="min-w-0 flex-1" />
            <button
              type="button"
              
              disabled={voiceModelBusy}
              onClick={() =>
                void (voiceModelRunning
                  ? cancelVoiceModel('voice')
                  : startVoiceModel('voice'))
              }
              aria-label={voiceModelRunning ? '取消下载语音模型' : '下载语音模型'}
              className="no-drag shrink-0 rounded-[6px] px-1.5 py-0.5 text-[11.5px] text-brand transition-colors hover:bg-hover focus-visible:ring-2 focus-visible:ring-brand/60 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
            >
              {voiceModelRunning ? '清空' : '下载'}
            </button>
          </div>
        ) : null}

        {

}
        {showVoiceInput && !isMainWindow ? (
          <div className="mt-1.5 px-1 text-[11px] leading-relaxed text-ink-faint">
            语音输入与唤醒只在主窗口使用（同一台麦克风不能同时在两个窗口打开）。
          </div>
        ) : null}

        {












}
        {showVoiceInput && isMainWindow && !voiceActive && micError ? (
          <div
            




            role="status"
            className="mt-1.5 flex items-start gap-2 rounded-[8px] bg-canvas px-2.5 py-1.5 text-[11.5px] leading-relaxed text-warning"
          >
            <span
              aria-hidden="true"
              className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-warning"
            />
            {

}
            <span className="min-w-0 flex-1">{micError}</span>
            <button
              type="button"
              onClick={retryMic}
              
              aria-label="重试打开麦克风"
              
              className="no-drag shrink-0 rounded-[6px] px-2 py-0.5 text-[11.5px] font-medium text-brand hover:bg-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
            >
              重试
            </button>
          </div>
        ) : null}

        {hint ? (
          <div className="mt-1.5 px-1 text-[11px] leading-relaxed text-warning">{hint}</div>
        ) : null}

        {







}
        {footerLeft || footerCenter || footerRight ? (
          











          <div className="mt-1.5 grid grid-cols-3 items-center gap-3 px-1 text-[11px] text-ink-faint">
            <div className="flex min-w-0 items-center gap-1.5">{footerLeft}</div>
            <div className="flex min-w-0 items-center justify-center">{footerCenter}</div>
            <div className="flex min-w-0 items-center justify-end gap-1.5">{footerRight}</div>
          </div>
        ) : null}

        {footerNote ? (
          <div className="mt-1.5 px-1 text-[11px] text-ink-faint">{footerNote}</div>
        ) : null}
      </div>
    </div>
  )
}
