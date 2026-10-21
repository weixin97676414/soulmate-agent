import { useEffect, useMemo, useState } from 'react'
import clsx from 'clsx'
import { Activity, PictureInPicture2 } from 'lucide-react'

import { ComposerShell } from '@/components/chat/ComposerShell'
import { ConfirmModeButton } from '@/components/chat/ConfirmModeButton'
import { ContextUsagePill } from '@/components/chat/ContextUsagePill'
import { ModelSelector } from '@/components/chat/ModelSelector'
import { ReasoningEffortButton } from '@/components/chat/ReasoningEffortButton'
import {
  SLASH_COMMANDS,
  matchCommands,
  type PaletteItem,
} from '@/components/chat/SlashCommandPanel'
import { useAssistantStore } from '@/stores/assistantStore'
import { useAppStore } from '@/stores/appStore'
import { useChatStore } from '@/stores/chatStore'
import { useNotificationStore } from '@/stores/notificationStore'













export function Composer() {
  const draft = useChatStore((state) => state.draft)
  const setDraft = useChatStore((state) => state.setDraft)
  const send = useChatStore((state) => state.send)
  const stop = useChatStore((state) => state.stop)
  const streaming = useChatStore((state) => state.streaming)
  const addFiles = useChatStore((state) => state.addFiles)
  const attachments = useChatStore((state) => state.attachments)
  const removeAttachment = useChatStore((state) => state.removeAttachment)
  const startNewSession = useChatStore((state) => state.startNewSession)
  const clearHistory = useChatStore((state) => state.clearHistory)
  const setModelId = useChatStore((state) => state.setModelId)
  const models = useAppStore((state) => state.models)
  const effectiveDefaultModelId = useAppStore((state) => state.modelDefaults.effectiveDefault)
  const sessionModelId = useChatStore((state) => state.modelId)

  
  
  
  
  const drawerOpen = useChatStore((state) => state.drawerOpen)
  const setDrawerOpen = useChatStore((state) => state.setDrawerOpen)
  
  
  const activeSessionId = useChatStore((state) => state.activeSessionId)
  const activeAssistant = useAssistantStore((state) =>
    state.assistants.find((item) => item.id === state.activeId),
  )
  
  const isChatWindow = window.agentBridge?.getWindowArgs?.()?.mode === 'chat'
  
  
  const assistantLabel =
    useAssistantStore((state) => {
      const current = state.assistants.find((item) => item.id === state.activeId)
      return current ? current.nickname || current.name : ''
    }) || '助手'

  
  
  
  
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [paletteMode, setPaletteMode] = useState<'command' | 'model' | 'clear'>('command')

  
  const paletteQuery =
    paletteOpen && paletteMode === 'command' && draft.startsWith('/')
      ? draft.slice(1).split(/\s+/)[0]
      : ''

  const paletteItems = useMemo<PaletteItem[]>(() => {
    if (!paletteOpen) return []
    if (paletteMode === 'model') {
      return models
        .filter((model) => model.enabled)
        .map((model) => ({ key: model.id, title: model.display_name, detail: model.provider }))
    }
    if (paletteMode === 'clear') {
      return [
        {
          key: 'confirm',
          title: '确认清空',
          detail: '删除本对话的全部消息',
          tone: 'danger' as const,
        },
        { key: 'cancel', title: '取消', detail: '什么都不做' },
      ]
    }
    return matchCommands(paletteQuery).map((command) => ({
      key: command.name,
      title: `/${command.name}`,
      detail: command.hint ? `${command.label} · ${command.hint}` : command.label,
    }))
  }, [paletteOpen, paletteMode, paletteQuery, models])

  const closePalette = () => {
    setPaletteOpen(false)
    setPaletteMode('command')
  }

  useEffect(() => {
    
    
    if (paletteMode !== 'command') return
    const shouldOpen = draft.startsWith('/') && !streaming
    if (shouldOpen && !paletteOpen) {
      setPaletteOpen(true)
    } else if (!shouldOpen && paletteOpen) {
      setPaletteOpen(false)
    }
  }, [draft, streaming, paletteOpen, paletteMode])

  const runPaletteItem = (item: PaletteItem) => {
    if (paletteMode === 'clear') {
      if (item.key === 'confirm') {
        setDraft('')
        void clearHistory()
      }
      closePalette()
      return
    }

    if (paletteMode === 'model') {
      setModelId(item.key)
      setDraft('')
      closePalette()
      return
    }

    const name = item.key
    setDraft('')
    if (name === 'new') {
      closePalette()
      startNewSession()
      return
    }
    if (name === 'stop') {
      closePalette()
      void stop()
      return
    }
    
    if (name === 'clear') {
      setPaletteMode('clear')
      return
    }
    if (name === 'model') {
      setPaletteMode('model')
      return
    }
    if (name === 'help') {
      closePalette()
      useNotificationStore.getState().push({
        level: 'info',
        title: '可用的快捷命令',
        message: SLASH_COMMANDS.map((command) => `/${command.name} — ${command.label}`).join(
          '\n',
        ),
        autoDismissMs: 0,
      })
      return
    }
    if (name === 'compact') {
      closePalette()
      const sessionId = useChatStore.getState().activeSessionId
      const api = useAppStore.getState().api
      if (!sessionId || !api) {
        useNotificationStore.getState().push({
          level: 'warning',
          title: '无法压缩',
          message: '当前没有进行中的对话，先发一条消息再压缩。',
        })
        return
      }
      void api
        .compressSession(sessionId)
        .then((result) => {
          useNotificationStore.getState().push({
            level: result.compressed ? 'success' : 'info',
            title: result.compressed ? '上下文已压缩' : '无需压缩',
            message: result.message,
          })
          
          useAppStore.getState().reloadHealth?.()
        })
        .catch((error: unknown) => {
          useNotificationStore.getState().push({
            level: 'error',
            title: '压缩失败',
            message: error instanceof Error ? error.message : String(error),
          })
        })
      return
    }
    closePalette()
  }

  
  
  const activeModel = useMemo(() => {
    const id = sessionModelId ?? effectiveDefaultModelId
    if (!id) return null
    return models.find((item) => item.id === id) ?? null
  }, [sessionModelId, effectiveDefaultModelId, models])

  const imageHint =
    activeModel && !activeModel.supports_vision && attachments.some((item) => item.kind === 'image')
      ? `当前模型「${activeModel.display_name}」不接收图片：图片会作为附件（文件路径）发过去，模型看不到画面。要真正把图片发给模型，请到「模型服务商」里选一个支持图片的模型，并勾上「支持图片输入」。`
      : undefined

  return (
    <ComposerShell
      value={draft}
      onChange={setDraft}
      onSubmit={() => void send()}
      busy={streaming}
      onStop={() => void stop()}
      placeholder={`给 ${assistantLabel} 发消息，Enter 发送，Shift + Enter 换行；输入 / 查看快捷命令`}
      attachments={attachments}
      onFiles={(files) => void addFiles(files)}
      onRemoveAttachment={removeAttachment}
      hint={imageHint}
      footerLeft={
        isChatWindow ? null : (
          <button
            type="button"
            onClick={() => {
              if (!activeAssistant?.id) return
              
              
              window.agentBridge?.openChatWindow(activeAssistant.id, activeSessionId ?? '')
            }}
            disabled={!activeAssistant}
            className="flex items-center gap-1 rounded-[6px] px-1.5 py-0.5 hover:bg-hover hover:text-ink disabled:opacity-40"
          >
            <PictureInPicture2 size={13} />
            打开独立窗口
          </button>
        )
      }
      footerCenter={<ModelSelector />}
      footerRight={
        <button
          type="button"
          onClick={() => setDrawerOpen(!drawerOpen)}
          












          


          aria-pressed={drawerOpen}
          className={clsx(
            'flex items-center gap-1 rounded-[6px] px-1.5 py-0.5 transition-colors disabled:opacity-40',
            drawerOpen
              ? 'bg-brand-soft font-medium text-brand hover:bg-brand/15'
              : 'hover:bg-hover hover:text-ink',
          )}
        >
          打开链路与产物
          <Activity size={13} />
        </button>
      }
      paletteOpen={paletteOpen}
      paletteItems={paletteItems}
      paletteEmptyText={paletteMode === 'model' ? '没有启用的模型' : '没有匹配的命令'}
      onPaletteSelect={runPaletteItem}
      onNewSession={startNewSession}
      toolbarLeft={
        <>
          <span className="mx-0.5 h-4 w-px shrink-0 bg-line" aria-hidden />
          <ReasoningEffortButton />
          <ContextUsagePill />
          <ConfirmModeButton />
        </>
      }
    />
  )
}
