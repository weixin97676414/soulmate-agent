import { useEffect, useRef } from 'react'

import { AddSkillDialog, openAddSkill } from '@/components/AddSkillDialog'
import { AuroraBackground } from '@/components/AuroraBackground'
import { ClosePrompt } from '@/components/ClosePrompt'
import { openFeedback } from '@/components/FeedbackDialog'
import { AssistantRail } from '@/components/chat/AssistantRail'
import { AvatarPreview } from '@/components/chat/AvatarPreview'
import { ConfirmDialog } from '@/components/chat/ConfirmDialog'
import { ChatView } from '@/components/chat/ChatView'
import { IconRail } from '@/components/IconRail'
import { SessionList } from '@/components/SessionList'
import { AppearanceSettings } from '@/components/settings/AppearanceSettings'
import { AuditSettings } from '@/components/settings/AuditSettings'
import { CalendarSettings } from '@/components/settings/CalendarSettings'
import { McpSettings } from '@/components/settings/McpSettings'
import { ModelSettings } from '@/components/settings/ModelSettings'
import { PreferenceSettings } from '@/components/settings/PreferenceSettings'
import { SkillSettings } from '@/components/settings/SkillSettings'
import { UsageSettings } from '@/components/settings/UsageSettings'
import { WorkspaceSettings } from '@/components/settings/WorkspaceSettings'
import { AboutPage } from '@/components/pages/AboutPage'
import { BenefitsPage } from '@/components/pages/BenefitsPage'
import { TasksPage } from '@/components/pages/TasksPage'
import { GroupChatPage } from '@/components/pages/GroupChatPage'
import { BootScreen } from '@/components/BootScreen'
import { OfflineDialog } from '@/components/OfflineDialog'
import { Onboarding } from '@/components/Onboarding'
import { InteractionDialog } from '@/components/chat/InteractionDialog'
import { TitleBar } from '@/components/TitleBar'
import { Toaster } from '@/components/Toaster'
import { usePanScroll } from '@/lib/usePanScroll'
import { useAppStore } from '@/stores/appStore'
import { useAssistantStore } from '@/stores/assistantStore'
import { useAccountStore } from '@/stores/accountStore'
import { useChatStore } from '@/stores/chatStore'
import { useNotificationStore } from '@/stores/notificationStore'
import { closeAllTransientDialogs, useTransientDialogsStore } from '@/stores/transientDialogs'
import { useVoiceCommand } from '@/stores/voiceCommandStore'
import { useVoiceSessionStore } from '@/stores/voiceSessionStore'

export default function App() {
  const bootstrap = useAppStore((state) => state.bootstrap)
  const bootstrapping = useAppStore((state) => state.bootstrapping)
  const bootstrapError = useAppStore((state) => state.bootstrapError)
  const view = useAppStore((state) => state.view)
  const onboardingActive = useAppStore((state) => state.onboardingActive)

  
  
  const windowArgs = window.agentBridge?.getWindowArgs?.()
  const isChatWindow = windowArgs?.mode === 'chat'
  
  
  const isGroupWindow = windowArgs?.mode === 'group'
  
  
  
  
  
  
  
  
  
  const onboarding = onboardingActive

  const loadSessions = useChatStore((state) => state.loadSessions)
  const startNewSession = useChatStore((state) => state.startNewSession)
  const loadAssistants = useAssistantStore((state) => state.load)
  const startEventStream = useNotificationStore((state) => state.startEventStream)
  const stopEventStream = useNotificationStore((state) => state.stopEventStream)
  const setView = useAppStore((state) => state.setView)

  
  
  
  const panRef = usePanScroll()

  









  const canNavigate =
    !isChatWindow && !isGroupWindow && !onboarding && !bootstrapping && !bootstrapError
  
  
  const transientOpenCount = useTransientDialogsStore((state) => state.openCount)
  useVoiceCommand('nav.chat', canNavigate ? () => setView('chat') : null)
  useVoiceCommand('nav.groups', canNavigate ? () => setView('groups') : null)
  useVoiceCommand('nav.tasks', canNavigate ? () => setView('tasks') : null)
  useVoiceCommand('nav.appearance', canNavigate ? () => setView('appearance') : null)
  useVoiceCommand('nav.benefits', canNavigate ? () => setView('benefits') : null)
  useVoiceCommand('nav.about', canNavigate ? () => setView('about') : null)
  




  useVoiceCommand('nav.models', canNavigate ? () => setView('models') : null)
  useVoiceCommand('nav.skills', canNavigate ? () => setView('skills') : null)
  useVoiceCommand('nav.mcp', canNavigate ? () => setView('mcp') : null)
  useVoiceCommand('nav.workspace', canNavigate ? () => setView('workspace') : null)
  useVoiceCommand('nav.usage', canNavigate ? () => setView('usage') : null)
  useVoiceCommand('nav.calendar', canNavigate ? () => setView('calendar') : null)
  useVoiceCommand('nav.audit', canNavigate ? () => setView('audit') : null)
  useVoiceCommand('nav.preference', canNavigate ? () => setView('preference') : null)
  
  
  
  useVoiceCommand('action.feedback', canNavigate ? () => openFeedback() : null)
  
  
  useVoiceCommand('action.addSkill', canNavigate ? () => openAddSkill() : null)
  








  useVoiceCommand(
    'action.closeDialog',
    
    
    canNavigate && transientOpenCount > 0 ? () => void closeAllTransientDialogs() : null,
  )

  useEffect(() => {
    void bootstrap()
  }, [bootstrap])

  
  
  const bootAccount = useAccountStore((state) => state.boot)
  useEffect(() => bootAccount(), [bootAccount])

  
  
  
  
  
  
  
  
  const activeLine = useAccountStore((state) => state.snapshot?.line?.preferred)
  const coreApi = useAppStore((state) => state.api)
  useEffect(() => {
    if (!coreApi || !activeLine) return
    void coreApi.setLine(activeLine).catch(() => {
      
      
    })
  }, [coreApi, activeLine])

  useEffect(() => {
    if (bootstrapping || bootstrapError) return
    void loadSessions()
    
    void loadAssistants()
    
    startEventStream()
    return () => stopEventStream()
  }, [
    bootstrapping,
    bootstrapError,
    loadSessions,
    loadAssistants,
    startEventStream,
    stopEventStream,
  ])

  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  
  const settingsReady = useAppStore((state) => state.settings !== null)
  const voiceBooted = useRef(false)
  
  
  const isMainWindow = windowArgs?.mode !== 'chat' && windowArgs?.mode !== 'group'
  useEffect(() => {
    if (!settingsReady || voiceBooted.current) return
    voiceBooted.current = true
    if (!isMainWindow) return
    useVoiceSessionStore.getState().bootstrap()
  }, [settingsReady, isMainWindow])

  
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'n') {
        event.preventDefault()
        startNewSession()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [startNewSession])

  
  
  
  
  
  useEffect(() => {
    if (!isChatWindow || bootstrapping || bootstrapError) return
    const assistantId = windowArgs?.assistantId
    if (!assistantId) return
    useAssistantStore.getState().setActive(assistantId)
    const sessionId = windowArgs?.sessionId
    const active = useChatStore.getState().activeSessionId
    if (sessionId) {
      if (active !== sessionId) void useChatStore.getState().selectSession(sessionId)
      return
    }
    const sessions = useChatStore.getState().sessions
    const recent = sessions.find((item) => item.assistant_id === assistantId)
    if (recent && active !== recent.id) {
      void useChatStore.getState().selectSession(recent.id)
    }
  }, [
    isChatWindow,
    bootstrapping,
    bootstrapError,
    windowArgs?.assistantId,
    windowArgs?.sessionId,
  ])

  
  
  
  if (bootstrapping || bootstrapError) {
    return (
      <div className="flex h-full flex-col">
        <AuroraBackground />
        {}
        <TitleBar brandOnly />
        <BootScreen />
        <ClosePrompt />
      </div>
    )
  }

  
  if (isChatWindow) {
    return (
      <div className="flex h-full flex-col overflow-hidden">
        <AuroraBackground />
        <TitleBar />
        {







}
        <div className="flex min-h-0 flex-1 flex-col">
          <ChatView />
        </div>
        <ConfirmDialog />
        {
}
        <InteractionDialog />
        <ClosePrompt />
        <AvatarPreview />
        <Toaster />
      </div>
    )
  }

  
  
  if (isGroupWindow) {
    return (
      <div className="flex h-full flex-col overflow-hidden">
        <AuroraBackground />
        <TitleBar />
        {


}
        <div className="flex min-h-0 flex-1 flex-col">
          <GroupChatPage
            groupId={windowArgs?.groupId ?? ''}
            readonly={windowArgs?.readonly === true}
            
            threadId={windowArgs?.threadId ?? ''}
          />
        </div>
        <ConfirmDialog />
        <InteractionDialog />
        <ClosePrompt />
        <AvatarPreview />
        <Toaster />
      </div>
    )
  }

  
  if (onboarding) {
    return (
      <div className="flex h-full flex-col overflow-hidden">
        <AuroraBackground />
        {}
        <TitleBar brandOnly />
        <div className="min-h-0 flex-1">
          <Onboarding />
        </div>
        <OfflineDialog />
        <ClosePrompt />
        <Toaster />
      </div>
    )
  }

  






  const panelContent =
    view === 'appearance' ? (
      <AppearanceSettings />
    ) : view === 'models' ? (
      <ModelSettings />
    ) : view === 'skills' ? (
      <SkillSettings />
    ) : view === 'mcp' ? (
      <McpSettings />
    ) : view === 'workspace' ? (
      <WorkspaceSettings />
    ) : view === 'usage' ? (
      <UsageSettings />
    ) : view === 'calendar' ? (
      <CalendarSettings />
    ) : view === 'audit' ? (
      <AuditSettings />
    ) : view === 'preference' ? (
      <PreferenceSettings />
    ) : null

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {}
      <AuroraBackground />
      <TitleBar />
      <div className="flex min-h-0 flex-1">
        <IconRail />
        {view === 'chat' ? (
          
          
          
          <div className="flex min-h-0 min-w-0 flex-1 gap-[3px] pb-[3px] pr-[3px]">
            {}
            <AssistantRail />
            <SessionList />
            <ChatView />
          </div>
        ) : view === 'groups' ? (
          <div className="flex min-h-0 min-w-0 flex-1 gap-[3px] pb-[3px] pr-[3px]">
            <GroupChatPage />
          </div>
        ) : view === 'tasks' ? (
          <div className="flex min-h-0 min-w-0 flex-1 gap-[3px] pb-[3px] pr-[3px]">
            <TasksPage />
          </div>
        ) : view === 'benefits' ? (
          <div className="flex min-h-0 min-w-0 flex-1 gap-[3px] pb-[3px] pr-[3px]">
            <BenefitsPage />
          </div>
        ) : view === 'about' ? (
          <div className="flex min-h-0 min-w-0 flex-1 gap-[3px] pb-[3px] pr-[3px]">
            <AboutPage />
          </div>
        ) : panelContent ? (
          
          
          
          
          <div className="flex min-h-0 min-w-0 flex-1 gap-[3px] pb-[3px] pr-[3px]">
            <div
              ref={panRef}
              className="min-w-0 flex-1 overflow-auto rounded-[12px] border border-line bg-panel px-10 py-5"
            >
              {panelContent}
            </div>
          </div>
        ) : (
          






          <div className="flex min-h-0 min-w-0 flex-1 gap-[3px] pb-[3px] pr-[3px]">
            <AssistantRail />
            <SessionList />
            <ChatView />
          </div>
        )}
      </div>
      <ConfirmDialog />
      <InteractionDialog />
      <OfflineDialog />
      <ClosePrompt />
      {}
      <AvatarPreview />
      {


}
      <AddSkillDialog />
      <Toaster />
    </div>
  )
}
