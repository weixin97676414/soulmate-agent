import {
  Blocks,
  CalendarDays,
  CircleUser,
  Coins,
  Cpu,
  FolderOpen,
  Mail,
  MessageSquare,
  Palette,
  Plug,
  ScrollText,
  ShieldCheck,
  Sparkles,
  Users,
  Workflow,
} from 'lucide-react'

import { FeedbackDialog, openFeedback } from '@/components/FeedbackDialog'
import { useAppStore, type ViewKey } from '@/stores/appStore'
import { useAccountStore } from '@/stores/accountStore'

interface RailItem {
  
  key: ViewKey | 'feedback'
  label: string
  icon: typeof MessageSquare
  








  hidden?: boolean
  






  bottom?: boolean
}






















const ITEMS: RailItem[] = [
  { key: 'chat', label: '对话', icon: MessageSquare },
  { key: 'groups', label: '群聊', icon: Users },
  { key: 'models', label: '模型', icon: Cpu },
  
  
  
  
  { key: 'tasks', label: '任务', icon: Workflow },
  { key: 'appearance', label: '外观', icon: Palette },
  { key: 'skills', label: '技能', icon: Blocks },
  { key: 'usage', label: '消耗', icon: Coins },
  
  
  { key: 'mcp', label: 'MCP', icon: Plug },
  { key: 'workspace', label: '产物', icon: FolderOpen },
  { key: 'calendar', label: '日历', icon: CalendarDays },
  { key: 'audit', label: '日志', icon: ScrollText },
  { key: 'preference', label: '安全', icon: ShieldCheck },
  
  { key: 'benefits', label: '社区', icon: CircleUser, bottom: true },
  { key: 'feedback', label: '反馈', icon: Mail, bottom: true },
  { key: 'about', label: '关于', icon: Sparkles, bottom: true },
]

export function IconRail() {
  const view = useAppStore((state) => state.view)
  const setView = useAppStore((state) => state.setView)
  const appInfo = useAppStore((state) => state.appInfo)
  const snapshot = useAccountStore((state) => state.snapshot)

  
  
  const dot = (item: { key: string }): string => {
    if (item.key !== 'benefits') return ''
    if (!snapshot) return ''
    if (!snapshot.deviceUsable) return 'bg-danger'
    if (snapshot.offline) return 'bg-warning'
    return ''
  }

  const renderItem = (item: RailItem) => {
    const Icon = item.icon
    
    const active = item.key !== 'feedback' && view === item.key
    const statusDot = dot(item)
    return (
      <button
        key={item.key}
        type="button"
        title={item.label}
        aria-label={item.label}
        
        
        aria-current={active ? 'page' : undefined}
        onClick={() => {
          if (item.key === 'feedback') {
            openFeedback()
            return
          }
          setView(item.key)
        }}
        
        
        
        className={`no-drag relative flex h-9 w-9 shrink-0 flex-col items-center justify-center gap-0.5 rounded-[10px] transition-colors ${
          active ? 'bg-brand-soft text-brand' : 'text-ink-soft hover:bg-hover hover:text-ink'
        }`}
      >
        {statusDot ? (
          <span
            className={`absolute right-1 top-1 h-1.5 w-1.5 rounded-full ${statusDot}`}
            aria-hidden
          />
        ) : null}
        <Icon size={17} />
        {






}
        <span className="text-[10px] leading-none">{item.label}</span>
      </button>
    )
  }

  
  
  
  
  
  
  
  const visibleItems = ITEMS.filter((item) => !item.hidden && !item.bottom)
  const bottomItems = ITEMS.filter((item) => item.bottom)

  return (
    <nav className="flex w-10 shrink-0 flex-col items-center gap-2 bg-canvas pb-2">
      {









}
      <div className="flex min-h-0 w-full flex-1 flex-col items-center gap-2 overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {visibleItems.map(renderItem)}
      </div>

      {



}
      <div className="flex flex-col items-center gap-2">
        {bottomItems.map(renderItem)}
      </div>

      <div className="pb-1 text-center text-[10px] leading-tight text-ink-faint">
        v{appInfo?.version ?? '1.0.1'}
      </div>

      {}
      <FeedbackDialog />
    </nav>
  )
}
