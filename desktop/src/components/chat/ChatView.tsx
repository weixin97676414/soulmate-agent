import clsx from 'clsx'
import { AlertTriangle, ChevronDown } from 'lucide-react'
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'

import { BrandMark } from '@/components/BrandMark'
import { AssistantAvatar } from '@/components/chat/AssistantFormModal'
import { Composer } from '@/components/chat/Composer'
import { DRAWER_GAP, DRAWER_WIDTH, DetailDrawer } from '@/components/chat/DetailDrawer'
import { ComputerUseBar } from '@/components/chat/ComputerUseBar'
import { Markdown } from '@/components/chat/Markdown'
import { MessageItem } from '@/components/chat/MessageItem'
import { PlanBar } from '@/components/chat/PlanBar'
import { UserProfileDialog } from '@/components/chat/UserProfileDialog'
import { VoicePanel } from '@/components/chat/VoicePanel'
import { welcomePresetsFor } from '@/components/chat/welcomePresets'
import { Button } from '@/components/ui'
import { useVoiceSessionStore } from '@/stores/voiceSessionStore'
import { useStickToBottom } from '@/lib/useStickToBottom'
import { useAppStore } from '@/stores/appStore'
import { useAssistantStore } from '@/stores/assistantStore'
import { useChatStore } from '@/stores/chatStore'
import { useVoiceCommand } from '@/stores/voiceCommandStore'
import { useUserProfileDialogStore } from '@/stores/userProfileDialogStore'
import { useNotificationStore } from '@/stores/notificationStore'
import type { AssistantProfile, RunRecord } from '@/types'





















const WELCOME_INTRO: Record<string, string> = {
  soulmate: [
    '我是这个世界上最懂你的人',
    








    '不需要你开口我就能知道你最新的状态',
    '我会陪着你，而且会一直都在',
  ].join('\n'),
  LoveBuddy: [
    '我是你的婚恋情感搭子',
    '帮你运营好你的情感关系',
    '我比你更了解你的另一半哦',
  ].join('\n'),
  RelationBuddy: [
    '我是你的职场人际关系运营助手',
    '日常社交问题同样也能分析与解答',
    '深度剖析一个人的行为和内在的心理运作模式',
  ].join('\n'),
}





const INITIAL_VISIBLE = 60


const VISIBLE_STEP = 60

function WelcomePanel({ assistant }: { assistant?: AssistantProfile }) {
  const builtinId = assistant?.builtin ? assistant.id : ''

  
  
  
  const presets = welcomePresetsFor(assistant)
  const send = useChatStore((state) => state.send)

  







  const sendPreset = (template: string) => {
    void send(template)
  }

  
  
  
  const description = !assistant
    ? ''
    : !builtinId
      ? (assistant.description ?? '')
      : builtinId === 'BuddyManager'
        ? assistant.description
        : (WELCOME_INTRO[builtinId] ?? assistant.description)

  return (
    
    
    
    <div className="mx-auto flex h-full w-full flex-col items-center px-6 py-10">
      {






}
      <div className="flex min-h-0 w-full flex-1 flex-col items-center justify-end">
      {




}
      {assistant ? (
        







        <AssistantAvatar profile={assistant} size={176} />
      ) : (
        
        
        
        <BrandMark size={176} radius={44} />
      )}
      </div>

      {

}
      <div className="flex min-h-0 w-full flex-1 flex-col items-center pt-3">
        {}
        <h1 className="shrink-0 text-[19px] font-semibold text-ink">
          {assistant?.nickname?.trim() || assistant?.name || '有什么可以帮你的？'}
        </h1>
        {


}
        {description ? (
          <div className="mt-1.5 min-h-0 w-full flex-1 overflow-y-auto px-1">
            {


}
            <div className="mx-auto max-w-[520px] text-center text-[13px] leading-relaxed text-ink-soft">
              <Markdown content={description} compact />
            </div>
          </div>
        ) : null}

        {

}
        {presets.length > 0 ? (
          







          <div className="mx-auto mt-3 flex w-full max-w-[520px] shrink-0 justify-center px-1">
            <div className="relative flex flex-wrap justify-center gap-2">
              <span className="absolute right-full top-1/2 mr-2 -translate-y-1/2 whitespace-nowrap text-[12px] text-ink-faint">
                快捷模版：
              </span>
              {presets.map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  
                  
                  title={preset.template}
                  onClick={() => sendPreset(preset.template)}
                  

















                  className="shrink-0 rounded-[5px] border border-brand bg-canvas px-2.5 py-1 text-[12px] text-ink-soft transition-colors duration-150 hover:bg-brand-soft hover:text-brand active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}












const DRAWER_WIDTH_DELTA = DRAWER_WIDTH + DRAWER_GAP

export function ChatView() {
  const messages = useChatStore((state) => state.messages)
  const profileDialogOpen = useUserProfileDialogStore((state) => state.open)

  
















  const drawerOpen = useChatStore((state) => state.drawerOpen)
  const loadArtifacts = useChatStore((state) => state.loadArtifacts)
  const streaming = useChatStore((state) => state.streaming)
  
  
  const activeSessionId = useChatStore((state) => state.activeSessionId)
  
  const activeAssistant = useAssistantStore((state) =>
    state.assistants.find((item) => item.id === state.activeId),
  )
  
  
  

  
  const voicePanelOpen = useVoiceSessionStore((state) => state.panelOpen)
  const setVoicePanelOpen = useVoiceSessionStore((state) => state.setPanelOpen)

  
















  const showDrawer = drawerOpen && !voicePanelOpen
  

























  useLayoutEffect(() => {
    if (!showDrawer) return
    window.agentBridge?.resizeWindowBySync?.(DRAWER_WIDTH_DELTA)
    return () => {
      window.agentBridge?.resizeWindowBySync?.(-DRAWER_WIDTH_DELTA)
    }
  }, [showDrawer])
  const voicePhase = useVoiceSessionStore((state) => state.phase)
  const voiceScope = useVoiceSessionStore((state) => state.scope)
  const voiceHeard = useVoiceSessionStore((state) => state.heard)
  const voiceLastHit = useVoiceSessionStore((state) => state.lastHit)
  const voicePending = useVoiceSessionStore((state) => state.pending)
  
  const disableVoice = useVoiceSessionStore((state) => state.disable)

  








  const [resumable, setResumable] = useState<RunRecord | null>(null)

  const loadResumable = useCallback(async () => {
    const api = useAppStore.getState().api
    if (!api || !activeSessionId) {
      setResumable(null)
      return
    }
    try {
      const payload = await api.getRuns()
      setResumable(
        payload.runs.find(
          (run) => run.kind === 'chat' && run.session_id === activeSessionId,
        ) ?? null,
      )
    } catch {
      
      setResumable(null)
    }
  }, [activeSessionId])

  
  useEffect(() => {
    void loadResumable()
  }, [loadResumable, streaming])

  const resume = async () => {
    const api = useAppStore.getState().api
    if (!api || !resumable) return
    try {
      const payload = await api.resumeRun(resumable.id)
      if (!payload.topic) {
        useNotificationStore.getState().push({
          level: 'warning',
          title: '没法接着做',
          message: payload.message ?? '这条记录已经不能续跑了。',
        })
        return
      }
      
      
      setResumable(null)
      
      
      await useChatStore.getState().send(payload.topic, '继续')
    } catch (error) {
      useNotificationStore.getState().push({
        level: 'error',
        title: '没能接着做',
        message: error instanceof Error ? error.message : String(error),
        autoDismissMs: 0,
      })
    }
  }

  const dismissResumable = async () => {
    const api = useAppStore.getState().api
    if (!api || !resumable) return
    try {
      await api.dismissRun(resumable.id)
    } catch {
      
    } finally {
      setResumable(null)
    }
  }

  





  
  useVoiceCommand('panel.drawer', () => {
    const store = useChatStore.getState()
    store.setDrawerOpen(true)
    store.setDrawerTab('trace')
  })
  
  
  
  
  useVoiceCommand('panel.drawerClose', () => {
    useChatStore.getState().setDrawerOpen(false)
  })
  
  
  useVoiceCommand('chat.continue', resumable && !streaming ? () => void resume() : null)

  
  useEffect(() => {
    void loadArtifacts()
  }, [loadArtifacts])

  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  const contentSignature = useMemo(
    () =>
      messages
        .map((message) =>
          [
            message.content.length,
            message.reasoning?.length ?? 0,
            message.status,
            message.toolCalls
              .map((tool) => `${tool.name}:${tool.status}:${(tool.result ?? '').length}`)
              .join(','),
          ].join(':'),
        )
        .join('|'),
    [messages],
  )

  
  
  const { ref: scrollRef, showJump, onScroll, jumpToBottom } = useStickToBottom(
    contentSignature,
    activeSessionId,
  )

  
  
  
  
  
  
  
  
  
  
  
  
  const [visibleCount, setVisibleCount] = useState(INITIAL_VISIBLE)
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  const lastResetSession = useRef(activeSessionId)
  useEffect(() => {
    if (lastResetSession.current === activeSessionId) return
    lastResetSession.current = activeSessionId
    setVisibleCount(INITIAL_VISIBLE)
  }, [activeSessionId])
  
  
  const anchorHeight = useRef<number | null>(null)

  const hiddenCount = Math.max(0, messages.length - visibleCount)
  const visibleMessages = hiddenCount > 0 ? messages.slice(-visibleCount) : messages

  const loadEarlier = () => {
    const element = scrollRef.current
    if (element) anchorHeight.current = element.scrollHeight
    setVisibleCount((count) => count + VISIBLE_STEP)
  }

  useLayoutEffect(() => {
    const before = anchorHeight.current
    if (before === null) return
    anchorHeight.current = null
    const element = scrollRef.current
    if (element) element.scrollTop += element.scrollHeight - before
  }, [visibleCount])

  return (
    














    <div className="flex min-h-0 min-w-0 flex-1 gap-[3px]">
      {

}
    <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-[3px]">
        {



}
        {
}
        <div className="relative min-h-0 flex-1 overflow-hidden rounded-[12px] border border-line bg-chat-surface">
          {



}

          {voicePanelOpen ? (
            <VoicePanel
              phase={voicePhase}
              scope={voiceScope}
              heard={voiceHeard}
              lastHit={voiceLastHit}
              pending={voicePending}
              onDisable={disableVoice}
              onClose={() => setVoicePanelOpen(false)}
            />
          ) : null}

          {







}
          <div
            ref={scrollRef}
            onScroll={onScroll}
            className="h-full overflow-y-auto"
            style={
              activeAssistant?.chat_background
                ? {
                    backgroundImage: `url("${activeAssistant.chat_background}")`,
                    backgroundSize: '100% 100%',
                  }
                : undefined
            }
          >
            {messages.length === 0 ? (
              
              
              <WelcomePanel assistant={activeAssistant} />
            ) : (
              <div className="mx-auto flex w-full flex-col gap-5 px-4 py-5">
                {hiddenCount > 0 ? (
                  <div className="flex justify-center">
                    <button
                      type="button"
                      onClick={loadEarlier}
                      className="rounded-[8px] border border-line bg-canvas px-3 py-1.5 text-[12px] text-ink-soft hover:border-brand/40 hover:text-ink"
                    >
                      载入更早的 {Math.min(VISIBLE_STEP, hiddenCount)} 条
                      <span className="ml-1 text-ink-faint">（还有 {hiddenCount} 条未显示）</span>
                    </button>
                  </div>
                ) : null}

                {visibleMessages.map((message) => (
                  <MessageItem key={message.id} message={message} />
                ))}

                {


}
                {resumable && !streaming ? (
                  <div className="rounded-[10px] border border-warning/30 bg-warning-soft px-3.5 py-3">
                    <div className="flex items-start gap-2.5">
                      <AlertTriangle size={15} className="mt-0.5 shrink-0 text-warning" />
                      <div className="min-w-0 flex-1">
                        <div className="text-[13px] font-medium text-ink">
                          要我接着往下做吗？
                        </div>
                        <p className="mt-1 text-[12px] leading-relaxed text-ink-soft">
                          {resumable.summary}
                        </p>
                        <div className="mt-2.5 flex items-center gap-2">
                          <Button size="sm" variant="primary" onClick={() => void resume()}>
                            继续
                          </Button>
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => void dismissResumable()}
                          >
                            不用了
                          </Button>
                        </div>
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>
            )}
          </div>

          {showJump ? (
            <button
              type="button"
              onClick={jumpToBottom}
              className={clsx(
                'no-drag absolute bottom-4 left-1/2 flex -translate-x-1/2 items-center gap-1.5 rounded-full',
                'border border-line bg-canvas px-3 py-1 text-[12px] text-ink-soft shadow-[0_4px_12px_rgba(0,0,0,0.10)] hover:text-ink',
              )}
            >
              <ChevronDown size={13} />
              回到最新
            </button>
          ) : null}
        </div>

        {




}
        <PlanBar messages={messages} />

        {


}
        <ComputerUseBar messages={messages} />

        <Composer />

        {

}
        <UserProfileDialog
          open={profileDialogOpen}
          onClose={() => useUserProfileDialogStore.getState().hide()}
        />
      </div>

      {








}
      {showDrawer ? <DetailDrawer streaming={streaming} /> : null}
    </div>
  )
}
