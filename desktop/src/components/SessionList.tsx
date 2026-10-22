import clsx from 'clsx'
import {
  MessageSquarePlus,
  MoreHorizontal,
  PanelLeftClose,
  PanelRightClose,
  Pencil,
  PictureInPicture2,
  Search,
  Trash2,
  Eraser,
  AlertTriangle,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

import {
  ContextMenu,
  ContextMenuDivider,
  ContextMenuItem,
  ContextMenuLabel,
} from '@/components/ContextMenu'
import { Markdown } from '@/components/chat/Markdown'
import { QuickSetupCard } from '@/components/chat/QuickSetupCard'
import { Button, EmptyState, IconButton, Modal } from '@/components/ui'
import { useCollapsed } from '@/lib/collapse'
import { useAssistantStore } from '@/stores/assistantStore'
import { useChatStore } from '@/stores/chatStore'
import { useVoiceCommand } from '@/stores/voiceCommandStore'
import type { SessionSummary } from '@/types'

type Group = { label: string; items: SessionSummary[] }

const TODAY = '今天'
const YESTERDAY = '昨天'
const THIS_WEEK = '最近 7 天'
const EARLIER = '更早'

function groupSessions(sessions: SessionSummary[]): Group[] {
  const now = new Date()
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const startOfYesterday = startOfToday - 24 * 60 * 60 * 1000
  const startOfWeek = startOfToday - 6 * 24 * 60 * 60 * 1000

  const buckets: Record<string, SessionSummary[]> = {
    [TODAY]: [],
    [YESTERDAY]: [],
    [THIS_WEEK]: [],
    [EARLIER]: [],
  }
  for (const session of sessions) {
    const stamp = session.updated_at * 1000
    if (stamp >= startOfToday) buckets[TODAY].push(session)
    else if (stamp >= startOfYesterday) buckets[YESTERDAY].push(session)
    else if (stamp >= startOfWeek) buckets[THIS_WEEK].push(session)
    else buckets[EARLIER].push(session)
  }
  return [TODAY, YESTERDAY, THIS_WEEK, EARLIER]
    .map((label) => ({ label, items: buckets[label] }))
    .filter((group) => group.items.length > 0)
}

export function SessionList() {
  const sessions = useChatStore((state) => state.sessions)
  const activeSessionId = useChatStore((state) => state.activeSessionId)
  const persistent = useChatStore((state) => state.persistent)
  const selectSession = useChatStore((state) => state.selectSession)
  const startNewSession = useChatStore((state) => state.startNewSession)
  const deleteSession = useChatStore((state) => state.deleteSession)
  const renameSession = useChatStore((state) => state.renameSession)
  const clearHistory = useChatStore((state) => state.clearHistory)

  
  const activeAssistantId = useAssistantStore((state) => state.activeId)
  const activeAssistant = useAssistantStore(
    (state) => state.assistants.find((item) => item.id === state.activeId) ?? null,
  )
  const assistantName = useAssistantStore(
    (state) => state.assistants.find((item) => item.id === state.activeId)?.name ?? '这个助手',
  )

  const [keyword, setKeyword] = useState('')
  







  const [menu, setMenu] = useState<{ session: SessionSummary; x: number; y: number } | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingTitle, setEditingTitle] = useState('')
  const [pendingDelete, setPendingDelete] = useState<SessionSummary | null>(null)
  const [pendingClear, setPendingClear] = useState(false)

  const editRef = useRef<HTMLInputElement>(null)
  useEffect(() => {
    if (editingId) editRef.current?.focus()
  }, [editingId])

  const groups = useMemo(() => {
    const lower = keyword.trim().toLowerCase()
    
    
    
    
    const scoped = activeAssistantId
      ? sessions.filter((session) => session.assistant_id === activeAssistantId)
      : sessions
    const filtered = lower
      ? scoped.filter((session) => session.title.toLowerCase().includes(lower))
      : scoped
    return groupSessions(filtered)
  }, [sessions, keyword, activeAssistantId])

  const beginRename = (session: SessionSummary) => {
    setMenu(null)
    setEditingId(session.id)
    setEditingTitle(session.title)
  }

  const commitRename = async () => {
    const id = editingId
    const title = editingTitle.trim()
    setEditingId(null)
    if (!id || !title) return
    await renameSession(id, title)
  }

  
  
  const [collapsed, toggleCollapsed, setCollapsed] = useCollapsed('rail:sessions')

  
  
  
  useVoiceCommand('panel.sessionRail', () => setCollapsed(true))
  useVoiceCommand('panel.sessionRailExpand', () => setCollapsed(false))

  if (collapsed) {
    return (
      <aside className="flex w-[44px] shrink-0 flex-col items-center overflow-hidden rounded-[12px] border border-line bg-panel py-2.5">
        {











}
        <IconButton label="展开对话列表" onClick={toggleCollapsed} className="text-ink-faint">
          <PanelRightClose size={15} />
        </IconButton>
        <IconButton
          label="新建对话 (Ctrl+N)"
          onClick={startNewSession}
          className="mt-3 border border-line bg-canvas text-ink-soft"
        >
          <MessageSquarePlus size={16} />
        </IconButton>
      </aside>
    )
  }

  return (
    <aside className="flex w-[240px] shrink-0 flex-col overflow-hidden rounded-[12px] border border-line bg-panel">
      {




}
      {





}
      <div className="flex h-11 shrink-0 items-center gap-1.5 px-2.5">
        <div className="relative min-w-0 flex-1">
          <Search
            size={14}
            className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-ink-faint"
          />
          <input
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            placeholder="搜索对话"
            
            
            
            aria-label="搜索对话"
            












            









            className="h-8 w-full rounded-[8px] border border-line bg-canvas pr-2 pl-7 text-[12.5px] text-ink placeholder:text-ink-faint focus:border-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 dark:border-brand/25"
          />
        </div>
        {



}
        {

}
        <IconButton
          label="隐藏对话列表"
          onClick={toggleCollapsed}
          className="mt-0.5 shrink-0 text-ink-faint"
        >
          <PanelLeftClose size={15} />
        </IconButton>
      </div>

      {}
      {activeAssistant ? (
        <div className="mx-2.5 mb-1 flex items-center gap-2 rounded-[8px] border border-line-soft bg-canvas px-2.5 py-2">
          {




}
          <div className="min-w-0 flex-1">
            {





}
            <div className="truncate text-[12px] font-medium text-ink">
              {activeAssistant.nickname || activeAssistant.name}
            </div>
            {


}
            {activeAssistant.description ? (
              <div className="text-[11px] leading-relaxed break-words text-ink-faint">
                <Markdown content={activeAssistant.description} compact />
              </div>
            ) : (
              <p className="text-[11px] text-ink-faint">这个助手还没有简介</p>
            )}
          </div>
        </div>
      ) : null}

      {

}
      {activeAssistant?.locked ? (
        <QuickSetupCard key={activeAssistant.id} assistant={activeAssistant} />
      ) : null}

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {groups.length === 0 ? (
          <div className="pt-16">
            <EmptyState
              title={
                keyword
                  ? '没有匹配的对话'
                  : activeAssistantId
                    ? '这个助手还没有对话'
                    : '还没有对话'
              }
              
              description={
                keyword
                  ? undefined
                  : activeAssistantId
                    ? `发一条消息就会在这里生成「${assistantName}」的对话。`
                    : '点击右上角的加号开始第一次对话。'
              }
            />
          </div>
        ) : (
          groups.map((group) => (
            <section key={group.label} className="mb-3">
              <div className="px-2 py-1.5 text-[11px] font-medium tracking-wide text-ink-faint">
                {group.label}
              </div>
              {group.items.map((session) => {
                const active = session.id === activeSessionId
                const editing = editingId === session.id

                return (
                  <div
                    key={session.id}
                    










                    role="button"
                    tabIndex={editing ? -1 : 0}
                    
                    aria-current={active ? 'true' : undefined}
                    className={clsx(
                      'group relative mb-0.5 flex cursor-pointer items-center rounded-[8px] px-2 py-1.5 transition-colors',
                      
                      
                      
                      'cv-session-row',
                      
                      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/50',
                      active ? 'bg-brand-soft' : 'hover:bg-hover',
                    )}
                    onClick={() => !editing && void selectSession(session.id)}
                    onDoubleClick={() => beginRename(session)}
                    onKeyDown={(event) => {
                      
                      
                      
                      if (event.target !== event.currentTarget) return
                      if (event.key !== 'Enter' && event.key !== ' ') return
                      event.preventDefault()
                      if (!editing) void selectSession(session.id)
                    }}
                    
                    
                    onContextMenu={(event) => {
                      event.preventDefault()
                      setMenu({ session, x: event.clientX, y: event.clientY })
                    }}
                  >
                    <div className="min-w-0 flex-1">
                      {editing ? (
                        <input
                          ref={editRef}
                          value={editingTitle}
                          onChange={(event) => setEditingTitle(event.target.value)}
                          onClick={(event) => event.stopPropagation()}
                          onBlur={() => void commitRename()}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter') void commitRename()
                            if (event.key === 'Escape') setEditingId(null)
                          }}
                          
                          
                          
                          
                          className="h-6 w-full rounded-[5px] border border-brand bg-canvas px-1.5 text-[13px] text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
                        />
                      ) : (
                        <div
                          className={clsx(
                            'truncate text-[13px]',
                            active ? 'font-medium text-brand' : 'text-ink',
                          )}
                        >
                          {session.title}
                        </div>
                      )}
                      <div className="mt-0.5 text-[11px] text-ink-faint">
                        {session.message_count} 条消息
                      </div>
                    </div>

                    {!editing ? (
                      <button
                        type="button"
                        aria-label="更多操作"
                        onClick={(event) => {
                          event.stopPropagation()
                          if (menu?.session.id === session.id) {
                            setMenu(null)
                            return
                          }
                          
                          
                          const rect = event.currentTarget.getBoundingClientRect()
                          setMenu({ session, x: rect.right, y: rect.bottom + 4 })
                        }}
                        className={clsx(
                          'no-drag flex h-6 w-6 shrink-0 items-center justify-center rounded-[6px] text-ink-faint hover:bg-canvas hover:text-ink',
                          
                          
                          menu?.session.id === session.id
                            ? 'opacity-100'
                            : 
                              
                              
                              
                              
                              
                              'opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100 focus-visible:opacity-100',
                        )}
                      >
                        <MoreHorizontal size={14} />
                      </button>
                    ) : null}
                  </div>
                )
              })}
            </section>
          ))
        )}
      </div>

      {









}
      {!persistent ? (
        <div className="shrink-0 border-t border-line px-3 py-2">
          <div className="flex items-start gap-1.5 px-1 text-[10.5px] leading-relaxed text-warning">
            <AlertTriangle size={11} className="mt-[2px] shrink-0" />
            当前为内存模式，对话不会保留到下次启动
          </div>
        </div>
      ) : null}

      {}
      {menu ? (
        <ContextMenu
          x={menu.x}
          y={menu.y}
          width={168}
          onClose={() => setMenu(null)}
        >
          <ContextMenuLabel>{menu.session.title}</ContextMenuLabel>

          {menu.session.assistant_id ? (
            <ContextMenuItem
              icon={<PictureInPicture2 size={13} className="text-ink-faint" />}
              onSelect={() => {
                
                const target = menu.session
                setMenu(null)
                window.agentBridge?.openChatWindow(target.assistant_id ?? '', target.id)
              }}
            >
              独立窗口对话
            </ContextMenuItem>
          ) : null}
          <ContextMenuItem
            icon={<Pencil size={13} className="text-ink-faint" />}
            onSelect={() => beginRename(menu.session)}
          >
            重命名
          </ContextMenuItem>

          <ContextMenuDivider />

          <ContextMenuItem
            icon={<Eraser size={13} className="text-ink-faint" />}
            onSelect={() => {
              const target = menu.session
              setMenu(null)
              
              void selectSession(target.id).then(() => setPendingClear(true))
            }}
          >
            清空对话内容
          </ContextMenuItem>
          <ContextMenuItem
            icon={<Trash2 size={13} />}
            danger
            onSelect={() => {
              const target = menu.session
              setMenu(null)
              setPendingDelete(target)
            }}
          >
            删除对话
          </ContextMenuItem>
        </ContextMenu>
      ) : null}

      {}
      <Modal
        open={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        width="max-w-md"
        title="删除对话"
        description="删除后该对话及其全部消息将无法恢复。"
        footer={
          <>
            <Button onClick={() => setPendingDelete(null)}>取消</Button>
            <Button
              variant="danger"
              onClick={() => {
                const target = pendingDelete
                setPendingDelete(null)
                if (target) void deleteSession(target.id)
              }}
            >
              删除
            </Button>
          </>
        }
      >
        <p className="text-[13px] text-ink">
          确定要删除「
          <span className="font-medium">{pendingDelete?.title}</span>
          」吗？该对话共有 {pendingDelete?.message_count ?? 0} 条消息。
        </p>
      </Modal>

      {}
      <Modal
        open={pendingClear}
        onClose={() => setPendingClear(false)}
        width="max-w-md"
        title="清空对话内容"
        description="会删除该对话的全部消息，但保留对话本身。"
        footer={
          <>
            <Button onClick={() => setPendingClear(false)}>取消</Button>
            <Button
              variant="danger"
              onClick={() => {
                setPendingClear(false)
                void clearHistory()
              }}
            >
              清空
            </Button>
          </>
        }
      >
        <p className="text-[13px] text-ink">此操作不可撤销，确定继续吗？</p>
      </Modal>
    </aside>
  )
}
