























import { useAppStore } from '@/stores/appStore'
import { useAssistantStore } from '@/stores/assistantStore'
import { useChatStore } from '@/stores/chatStore'











export function switchAssistant(assistantId: string): void {
  
  
  
  
  
  useAppStore.getState().setView('chat')

  const { activeId, setActive } = useAssistantStore.getState()
  if (activeId !== assistantId) setActive(assistantId)

  const { sessions, selectSession, startNewSession } = useChatStore.getState()
  const latest = sessions
    .filter((session) => session.assistant_id === assistantId)
    .sort((a, b) => b.updated_at - a.updated_at)[0]

  if (latest) void selectSession(latest.id)
  else startNewSession()
}
