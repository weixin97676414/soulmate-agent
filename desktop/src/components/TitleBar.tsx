import { isDarkTheme } from '@shared/bridge'
import { Minus, Moon, RotateCcw, Square, Sun, X } from 'lucide-react'

import { AssistantAvatar } from '@/components/chat/AssistantFormModal'
import { GroupAvatar } from '@/components/chat/GroupAvatar'
import { BrandMark } from '@/components/BrandMark'
import { IconButton } from '@/components/ui'
import { useCurrentGroup } from '@/lib/currentSubject'
import { useAppStore } from '@/stores/appStore'
import { useAssistantStore } from '@/stores/assistantStore'
import { useChatStore } from '@/stores/chatStore'

interface TitleBarProps {
  











  brandOnly?: boolean
}








export function TitleBar({ brandOnly = false }: TitleBarProps) {
  const theme = useAppStore((state) => state.theme)
  const toggleTheme = useAppStore((state) => state.toggleTheme)
  const health = useAppStore((state) => state.health)
  
  

  








  
  
  const runningAssistantId = useChatStore((state) => state.runningAssistantId)
  







  const runningCount = useChatStore((state) => Object.keys(state.runs).length)

  
  const activeAssistant = useAssistantStore((state) =>
    state.assistants.find((item) => item.id === state.activeId),
  )
  
  
  
  
  
  
  
  
  
  const runningAssistant = useAssistantStore((state) =>
    runningAssistantId
      ? state.assistants.find((item) => item.id === runningAssistantId)
      : undefined,
  )

  
  
  
  
  
  










  const shownAssistant = activeAssistant

  





  const activeGroup = useCurrentGroup()

  








  const primaryName = brandOnly
    ? 'Soulmate Agent'
    : activeGroup?.name || shownAssistant?.name || 'Soulmate Agent'
  const nickname = brandOnly || activeGroup ? '' : (shownAssistant?.nickname?.trim() ?? '')
  const showNickname = Boolean(nickname) && nickname !== primaryName

  




  const brandMark = <BrandMark size={24} radius={6} bordered={false} />

  
  
  
  return (
    <header className="drag-region flex h-10 shrink-0 items-center gap-3 bg-canvas pl-2">
      <div className="flex items-center gap-2">
        {











}
        {brandOnly ? (
          brandMark
        ) : activeGroup ? (
          <GroupAvatar group={activeGroup} size={24} />
        ) : shownAssistant ? (
          <AssistantAvatar profile={shownAssistant} size={24} />
        ) : (
          
          brandMark
        )}
        <span className="text-[13px] font-semibold whitespace-nowrap text-ink">{primaryName}</span>
        {showNickname ? (
          <span
            className="max-w-[140px] truncate text-[11.5px] whitespace-nowrap text-ink-faint"
            title={`昵称：${nickname}`}
          >
            {nickname}
          </span>
        ) : null}
      </div>

      {





}
      <div className="min-w-0 flex-1" />

      <div className="no-drag flex items-center gap-1">
        {




}
        {runningCount > 0 ? (
          <span
            className="mr-1 hidden items-center gap-1.5 text-[11.5px] text-brand lg:flex"
            title="切到任何页面、切换搭子或对话都不会中断，可以放心去做别的事"
          >
            <span className="h-[6px] w-[6px] animate-pulse rounded-full bg-brand" />
            {runningCount > 1
              ? `${runningCount} 个搭子正在工作`
              : `${runningAssistant?.name ?? '搭子'} 正在工作`}
          </span>
        ) : null}
        {health ? (
          <span
            className="mr-1 hidden items-center gap-1.5 text-[11.5px] text-ink-faint lg:flex"
            title={`数据目录：${health.data_dir}`}
          >
            {









}
            <span className="h-[6px] w-[6px] rounded-full bg-success" />
            {health.skills} 个工具
          </span>
        ) : null}
        {







}
        <IconButton
          label={isDarkTheme(theme) ? '切换到浅色主题' : '切换到深色主题'}
          onClick={toggleTheme}
        >
          {isDarkTheme(theme) ? <Sun size={16} /> : <Moon size={16} />}
        </IconButton>

        {}
        <button
          type="button"
          aria-label="最小化"
          title="最小化"
          onClick={() => window.agentBridge?.minimizeWindow()}
          className="no-drag flex h-8 w-11 items-center justify-center rounded-[6px] text-ink-soft hover:bg-hover hover:text-ink"
        >
          <Minus size={14} />
        </button>
        {













}
        <button
          type="button"
          aria-label="恢复默认大小"
          title="恢复默认大小（1366 × 768）"
          onClick={() => window.agentBridge?.resetWindowSize()}
          className="no-drag flex h-8 w-11 items-center justify-center rounded-[6px] text-ink-soft hover:bg-hover hover:text-ink"
        >
          <RotateCcw size={13} />
        </button>
        <button
          type="button"
          aria-label="最大化 / 还原"
          title="最大化 / 还原"
          onClick={() => window.agentBridge?.toggleMaximizeWindow()}
          className="no-drag flex h-8 w-11 items-center justify-center rounded-[6px] text-ink-soft hover:bg-hover hover:text-ink"
        >
          <Square size={13} />
        </button>
        <button
          type="button"
          aria-label="关闭"
          title="关闭"
          onClick={() => window.agentBridge?.closeWindow()}
          className="no-drag flex h-8 w-11 items-center justify-center rounded-[6px] text-ink-soft hover:bg-danger hover:text-white"
        >
          <X size={15} />
        </button>
      </div>
    </header>
  )
}
