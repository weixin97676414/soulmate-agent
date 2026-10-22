import clsx from 'clsx'
import {
  AlertCircle,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Eraser,
  Loader2,
  PanelLeftClose,
  PanelRightClose,
  PictureInPicture2,
  Plus,
  Settings2,
  MessageSquarePlus,
  Trash2,
  Users,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { AssistantAvatar } from '@/components/chat/AssistantFormModal'
import { ComposerShell } from '@/components/chat/ComposerShell'



import { ConfirmModeButton } from '@/components/chat/ConfirmModeButton'


import { GroupAvatar } from '@/components/chat/GroupAvatar'
import { Markdown } from '@/components/chat/Markdown'


import { ReasoningBlock } from '@/components/chat/MessageItem'
import { ToolCallCard } from '@/components/chat/ToolCallCard'


import { VoicePanel } from '@/components/chat/VoicePanel'
import { ReasoningEffortButton } from '@/components/chat/ReasoningEffortButton'
import type { PaletteItem } from '@/components/chat/SlashCommandPanel'
import { UserProfileDialog } from '@/components/chat/UserProfileDialog'
import { GroupContextMenu, GroupThreadContextMenu } from '@/components/pages/GroupContextMenu'
import { Button, IconButton, Modal } from '@/components/ui'
import { useCollapsed } from '@/lib/collapse'

import { switchGroup } from '@/services/groupSwitch'
import { readImageAsDataUrl, AVATAR_MAX_SIZE } from '@/lib/image'
import { formatFull } from '@/lib/time'
import { loadUserProfile, subscribeUserProfile } from '@/lib/userProfile'
import { useStickToBottom } from '@/lib/useStickToBottom'
import { useVoiceSessionStore } from '@/stores/voiceSessionStore'
import { useAppStore } from '@/stores/appStore'
import { useAssistantStore } from '@/stores/assistantStore'
import { useGroupStore } from '@/stores/groupStore'
import { useNotificationStore } from '@/stores/notificationStore'
import { useUserProfileDialogStore } from '@/stores/userProfileDialogStore'
import { useVoiceCommand } from '@/stores/voiceCommandStore'
import type { GroupProfile, GroupThread, GroupUpdate, RunRecord } from '@/types'














const GROUP_COMMANDS: Array<{ name: string; label: string; tone?: 'danger' }> = [
  { name: 'clear', label: '清空本群的讨论记录', tone: 'danger' },
  { name: 'stop', label: '停止正在进行的讨论' },
  { name: 'help', label: '查看群聊里可用的命令' },
]

function matchGroupCommands(query: string): typeof GROUP_COMMANDS {
  const lower = query.trim().toLowerCase()
  if (!lower) return GROUP_COMMANDS
  return GROUP_COMMANDS.filter((command) =>
    `${command.name} ${command.label}`.toLowerCase().includes(lower),
  )
}


































function MemberLine({ names }: { names: string[] }) {
  const [expanded, setExpanded] = useState(false)
  const [overflowing, setOverflowing] = useState(false)
  const ref = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    const element = ref.current
    if (!element) return
    
    
    const measure = () => setOverflowing(element.scrollWidth > element.clientWidth + 1)
    measure()
    
    
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
  }, [names])

  if (names.length === 0) {
    return <div className="mt-0.5 text-[11px] text-ink-faint">还没有成员</div>
  }

  return (
    <div className="mt-0.5 flex items-start gap-1">
      <span
        ref={ref}
        title={names.join('、')}
        className={clsx(
          'min-w-0 flex-1 text-[11px] text-ink-faint',
          expanded ? 'break-all' : 'truncate',
        )}
      >
        {names.join('、')}
      </span>
      {
}
      {overflowing || expanded ? (
        <button
          type="button"
          aria-expanded={expanded}
          aria-label={expanded ? '收起群成员' : '展开全部群成员'}
          onClick={(event) => {
            
            event.stopPropagation()
            setExpanded((prev) => !prev)
          }}
          className="mt-[1px] shrink-0 rounded-[4px] text-ink-faint transition-colors hover:text-ink"
        >
          <ChevronDown
            size={11}
            className={clsx('transition-transform', expanded && 'rotate-180')}
          />
        </button>
      ) : null}
    </div>
  )
}








function GroupAvatarPicker({
  value,
  onChange,
  hint,
}: {
  value: string
  hint: string
  onChange: (next: string) => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)

  const pick = async (file: File | undefined) => {
    if (!file) return
    try {
      
      
      onChange(await readImageAsDataUrl(file, AVATAR_MAX_SIZE))
    } catch (error) {
      useNotificationStore.getState().push({
        level: 'error',
        title: '这张图用不了',
        message: error instanceof Error ? error.message : String(error),
      })
    }
  }

  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        title="选择群头像（不选的话会自动配一张）"
        className="group relative h-11 w-11 shrink-0 cursor-pointer overflow-hidden rounded-[10px] border border-line bg-canvas"
      >
        {value ? (
          <img
            src={value}
            alt=""
            draggable={false}
            className="h-full w-full object-cover select-none"
          />
        ) : (
          <span className="flex h-full w-full items-center justify-center text-ink-faint group-hover:text-ink-soft">
            <Plus size={14} />
          </span>
        )}
      </button>
      <div className="min-w-0 flex-1 text-[11.5px] leading-relaxed text-ink-faint">
        <div className="text-ink-soft">群头像</div>
        <div>{value ? "已选好这张；点它可换。" : hint}</div>
      </div>
      {value ? (
        <button
          type="button"
          onClick={() => onChange('')}
          className="shrink-0 rounded-[6px] px-1.5 py-0.5 text-[11.5px] text-ink-faint hover:bg-hover hover:text-ink"
        >
          取消
        </button>
      ) : null}
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(event) => void pick(event.target.files?.[0])}
      />
    </div>
  )
}

export function GroupChatPage({
  groupId = '',
  readonly = false,
  threadId = '',
}: {
  
  groupId?: string
  





  threadId?: string
  





  readonly?: boolean
} = {}) {
  const assistants = useAssistantStore((state) => state.assistants)
  
  const standalone = Boolean(groupId)
  




  const [isReadonly, setIsReadonly] = useState(readonly)
  
  const [stopping, setStopping] = useState(false)

  const groups = useGroupStore((state) => state.groups)
  const selectedId = useGroupStore((state) => state.selectedId)
  const bubbles = useGroupStore((state) => state.bubbles)
  const busy = useGroupStore((state) => state.busy)
  const loadGroups = useGroupStore((state) => state.loadGroups)
  const selectGroup = useGroupStore((state) => state.selectGroup)
  const createGroup = useGroupStore((state) => state.createGroup)
  const deleteGroup = useGroupStore((state) => state.deleteGroup)
  const clearMessages = useGroupStore((state) => state.clearMessages)
  
  const profileDialogOpen = useUserProfileDialogStore((state) => state.open)

  





  const [groupsCollapsed, toggleGroupsCollapsed, setGroupsCollapsed] =
    useCollapsed('rail:groups')
  const [threadsCollapsed, toggleThreadsCollapsed, setThreadsCollapsed] =
    useCollapsed('rail:group-threads')

  const threads = useGroupStore((state) => state.threads)
  const activeThreadId = useGroupStore((state) => state.activeThreadId)
  const selectThread = useGroupStore((state) => state.selectThread)
  const startNewThread = useGroupStore((state) => state.startNewThread)
  const deleteThread = useGroupStore((state) => state.deleteThread)
  const renameThread = useGroupStore((state) => state.renameThread)
  const discuss = useGroupStore((state) => state.discuss)

  









  const voicePanelOpen = useVoiceSessionStore((state) => state.panelOpen)
  const setVoicePanelOpen = useVoiceSessionStore((state) => state.setPanelOpen)
  const voicePhase = useVoiceSessionStore((state) => state.phase)
  const voiceScope = useVoiceSessionStore((state) => state.scope)
  const voiceHeard = useVoiceSessionStore((state) => state.heard)
  const voiceLastHit = useVoiceSessionStore((state) => state.lastHit)
  const voicePending = useVoiceSessionStore((state) => state.pending)
  const disableVoice = useVoiceSessionStore((state) => state.disable)
  const stop = useGroupStore((state) => state.stop)
  const updateGroup = useGroupStore((state) => state.updateGroup)
  const draft = useGroupStore((state) => state.draft)
  const attachments = useGroupStore((state) => state.attachments)
  const setDraft = useGroupStore((state) => state.setDraft)
  
  const api = useAppStore((state) => state.api)
  const addFiles = useGroupStore((state) => state.addFiles)
  const removeAttachment = useGroupStore((state) => state.removeAttachment)

  const [paletteOpen, setPaletteOpen] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  





  const [newAvatar, setNewAvatar] = useState('')
  const [picked, setPicked] = useState<string[]>([])
  const [pendingDelete, setPendingDelete] = useState(false)
  const [pendingClear, setPendingClear] = useState(false)
  
  const [renamingId, setRenamingId] = useState<string | null>(null)
  
  const [pendingDeleteThread, setPendingDeleteThread] = useState<GroupThread | null>(null)
  






  const [threadMenu, setThreadMenu] = useState<{
    groupId: string
    thread: GroupThread
    x: number
    y: number
  } | null>(null)
  
  const [savingSettings, setSavingSettings] = useState(false)
  
  const [showSettings, setShowSettings] = useState(false)
  const [editName, setEditName] = useState('')
  
  const [editAvatar, setEditAvatar] = useState('')
  const [editPicked, setEditPicked] = useState<string[]>([])
  
  const [menu, setMenu] = useState<{ group: GroupProfile; x: number; y: number } | null>(null)

  
  
  
  
  
  
  
  const bubbleSignature = `${busy ? 'busy' : ''}|${bubbles
    .map(
      (item) =>
        `${item.id}:${item.content.length}:${(item.reasoning ?? '').length}:` +
        (item.toolCalls ?? []).map((tool) => `${tool.name}:${tool.status}`).join(','),
    )
    .join('|')}`

  






  const { ref: scrollRef, showJump, onScroll, jumpToBottom } = useStickToBottom(
    bubbleSignature,
    selectedId,
  )

  






  const [resumable, setResumable] = useState<RunRecord | null>(null)
  const loadResumable = useCallback(async () => {
    if (!api || !selectedId) {
      setResumable(null)
      return
    }
    try {
      const payload = await api.getRuns()
      setResumable(
        payload.runs.find((run) => run.kind === 'group' && run.ref_id === selectedId) ?? null,
      )
    } catch {
      
      setResumable(null)
    }
  }, [api, selectedId])

  
  useEffect(() => {
    void loadResumable()
  }, [loadResumable, busy])

  const resumeDiscussion = async () => {
    if (!api || !resumable) return
    try {
      const payload = await api.resumeRun(resumable.id)
      if (!payload.topic) {
        useNotificationStore.getState().push({
          level: 'warning',
          title: '没法继续这场讨论',
          message: payload.message ?? '这条记录已经不能续跑了。',
        })
        setResumable(null)
        return
      }
      setResumable(null)
      
      setDraft(payload.topic)
      await discuss()
    } catch (error) {
      useNotificationStore.getState().push({
        level: 'error',
        title: '续跑失败',
        message: error instanceof Error ? error.message : String(error),
        autoDismissMs: 0,
      })
    }
  }

  const dropResumable = async () => {
    if (!api || !resumable) return
    try {
      await api.dismissRun(resumable.id)
    } catch {
      
    } finally {
      setResumable(null)
    }
  }

  
  
  useVoiceCommand('chat.continue', resumable && !busy ? () => void resumeDiscussion() : null)

  
  
  
  useVoiceCommand('panel.groupThreads', () => setThreadsCollapsed(true))
  useVoiceCommand('panel.groupThreadsExpand', () => setThreadsCollapsed(false))
  useVoiceCommand('panel.groupList', () => setGroupsCollapsed(true))
  useVoiceCommand('panel.groupListExpand', () => setGroupsCollapsed(false))

  const byId = useMemo(() => new Map(assistants.map((item) => [item.id, item])), [assistants])
  const selected = groups.find((item) => item.id === selectedId) ?? null
  
  const memberNames = useMemo(
    () => (selected?.member_assistant_ids ?? []).map((id) => byId.get(id)?.name ?? id),
    [selected, byId],
  )

  










  const appliedInitialThread = useRef(false)
  useEffect(() => {
    if (!standalone || !threadId || appliedInitialThread.current) return
    if (!threads.some((item) => item.id === threadId)) return
    appliedInitialThread.current = true
    if (activeThreadId !== threadId) void selectThread(threadId)
  }, [standalone, threadId, threads, activeThreadId, selectThread])

  const settingsRequestId = useGroupStore((state) => state.settingsRequestId)
  const clearGroupSettingsRequest = useGroupStore((state) => state.clearGroupSettingsRequest)

  









  useEffect(() => {
    if (!settingsRequestId) return
    const group = useGroupStore.getState().groups.find((item) => item.id === settingsRequestId)
    if (group) {
      void selectGroup(group.id)
      setEditName(group.name)
      setEditAvatar(group.avatar)
      setEditPicked([...group.member_assistant_ids])
      setShowSettings(true)
    }
    clearGroupSettingsRequest()
  }, [settingsRequestId, clearGroupSettingsRequest, selectGroup])

  






  const [userAvatar, setUserAvatar] = useState(() => loadUserProfile().avatar)
  useEffect(
    () => subscribeUserProfile(() => setUserAvatar(loadUserProfile().avatar)),
    [],
  )

  





  const pauseTask = async () => {
    if (!api || !selected || stopping) return
    setStopping(true)
    try {
      await api.stopGroupDiscussion(selected.id)
      setIsReadonly(false)
    } catch (error) {
      useNotificationStore.getState().push({
        level: 'error',
        title: '暂停失败',
        message: error instanceof Error ? error.message : String(error),
      })
    } finally {
      setStopping(false)
    }
  }

  useEffect(() => {
    if (!standalone) {
      void loadGroups()
      return
    }
    
    
    
    void (async () => {
      await loadGroups()
      await selectGroup(groupId)
    })()
    
  }, [standalone, groupId])

  const submitCreate = async () => {
    if (!newName.trim() || picked.length === 0) return
    try {
      await createGroup({
        name: newName.trim(),
        member_assistant_ids: picked,
        
        speaking_order: picked,
        
        avatar: newAvatar,
      })
    } catch (error) {
      
      
      useNotificationStore.getState().push({
        level: 'error',
        title: '建群失败',
        message: error instanceof Error ? error.message : String(error),
        autoDismissMs: 0,
      })
      return
    }
    setShowCreate(false)
    setNewName('')
    setPicked([])
    setNewAvatar('')
  }

  const togglePick = (id: string) =>
    setPicked((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]))

  






  const saveGroupPolicy = async (patch: GroupUpdate) => {
    if (!selected) return
    setSavingSettings(true)
    try {
      await updateGroup(selected.id, patch)
    } finally {
      setSavingSettings(false)
    }
  }

  
  const submitSettings = async () => {
    
    
    if (!selected || !editName.trim()) return
    setSavingSettings(true)
    try {
      const patch: {
        name?: string
        member_assistant_ids: string[]
        speaking_order: string[]
        avatar?: string
      } = {
        member_assistant_ids: editPicked,
        speaking_order: editPicked,
      }
      if (editName.trim() !== selected.name) patch.name = editName.trim()
      
      
      if (editAvatar !== selected.avatar) patch.avatar = editAvatar
      await updateGroup(selected.id, patch)
      setShowSettings(false)
    } finally {
      setSavingSettings(false)
    }
  }

  
  const movePick = (index: number, delta: number) =>
    setPicked((prev) => {
      const target = index + delta
      if (target < 0 || target >= prev.length) return prev
      const next = [...prev]
      ;[next[index], next[target]] = [next[target], next[index]]
      return next
    })

  
  
  
  
  
  
  
  const paletteItems = useMemo<PaletteItem[]>(() => {
    if (!paletteOpen) return []
    const query = (draft.startsWith('/') ? draft.slice(1).split(/\s+/)[0] : '').toLowerCase()
    const matched = matchGroupCommands(query)
    return matched.map((command) => ({
      key: command.name,
      title: `/${command.name}`,
      detail: command.label,
      tone: command.tone,
    }))
  }, [paletteOpen, draft])

  useEffect(() => {
    const shouldOpen = draft.startsWith('/') && !busy
    setPaletteOpen(shouldOpen)
  }, [draft, busy])

  const runGroupCommand = (item: PaletteItem) => {
    setDraft('')
    setPaletteOpen(false)
    if (item.key === 'clear') {
      
      setPendingClear(true)
      return
    }
    if (item.key === 'stop') {
      stop()
      return
    }
    if (item.key === 'help') {
      useNotificationStore.getState().push({
        level: 'info',
        title: '群聊里可用的命令',
        message:
          GROUP_COMMANDS.map((command) => `/${command.name} — ${command.label}`).join('\n') +
          '\n\n换模型与压缩上下文是"单个对话"的概念：群里每个搭子有自己的模型，' +
          '上下文也是逐条记录，所以这两个命令在群里不适用。',
        autoDismissMs: 0,
      })
    }
  }

  return (
    
    
    
    <div className="flex h-full min-h-0 min-w-0 flex-1 gap-[3px]">
      {











}
      {groupsCollapsed ? (
        <aside
          className={clsx(
            'flex w-[44px] shrink-0 flex-col items-center overflow-hidden rounded-[12px] border border-line bg-panel py-2.5',
            standalone && 'hidden',
          )}
        >
          {
}
          <IconButton
            label="展开群聊列表"
            onClick={toggleGroupsCollapsed}
            className="text-ink-faint"
          >
            <PanelRightClose size={15} />
          </IconButton>
          <IconButton
            label="新建群"
            onClick={() => setShowCreate(true)}
            className="mt-3 border border-line bg-canvas text-ink-soft"
          >
            <Plus size={16} />
          </IconButton>
        </aside>
      ) : (
      <aside
        className={clsx(
          
          'flex w-[240px] shrink-0 flex-col overflow-hidden rounded-[12px] border border-line bg-panel',
          standalone && 'hidden',
        )}
      >
        {
}
        <div className="flex h-11 shrink-0 items-center justify-between px-2.5">
          <div className="flex items-center gap-1.5 pl-0.5 text-[13px] font-medium text-ink">
            <Users size={14} className="text-brand" />
            群聊
          </div>
          <IconButton
            label="隐藏群聊列表"
            onClick={toggleGroupsCollapsed}
            className="mt-0.5 shrink-0 text-ink-faint"
          >
            <PanelLeftClose size={15} />
          </IconButton>
        </div>
        {







}
        <div className="shrink-0 px-2 pb-1.5">
          <Button
            variant="secondary"
            size="sm"
            icon={<Plus size={13} />}
            className="h-8 w-full justify-center"
            onClick={() => setShowCreate(true)}
          >
            新建群
          </Button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
          {groups.length === 0 ? (
            <p className="px-2 py-8 text-center text-[12px] text-ink-faint">
              还没有搭子群。点上面的「新建群」把几个搭子拉进来，抛个话题让它们自己聊。
            </p>
          ) : (
            groups.map((group) => (
              
              
              
              
              <div
                key={group.id}
                role="button"
                tabIndex={0}
                
                
                
                onClick={() => switchGroup(group.id)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    switchGroup(group.id)
                  }
                }}
                onContextMenu={(event) => {
                  event.preventDefault()
                  
                  setThreadMenu(null)
                  setMenu({ group, x: event.clientX, y: event.clientY })
                }}
                className={clsx(
                  'no-drag group mb-0.5 flex w-full cursor-pointer items-center gap-1 rounded-[8px] px-2.5 py-2 text-left transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-brand',
                  selected?.id === group.id ? 'bg-brand-soft' : 'hover:bg-hover',
                )}
              >
                {










}
                <GroupAvatar group={group} size={32} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] text-ink">{group.name}</div>
                  {
}
                  <MemberLine
                    names={group.member_assistant_ids.map((id) => byId.get(id)?.name ?? id)}
                  />

                </div>
                {







}
              </div>
            ))
          )}
        </div>
      </aside>
      )}

      {









}
      {threadsCollapsed ? (
        <aside
          className={clsx(
            'flex w-[44px] shrink-0 flex-col items-center overflow-hidden rounded-[12px] border border-line bg-panel py-2.5',
            standalone && 'hidden',
          )}
        >
          <IconButton
            label="展开对话列表"
            onClick={toggleThreadsCollapsed}
            className="text-ink-faint"
          >
            <PanelRightClose size={15} />
          </IconButton>
          {isReadonly ? null : (
            <IconButton
              label="开启新对话"
              onClick={() => void startNewThread()}
              className="mt-3 border border-line bg-canvas text-ink-soft"
            >
              <MessageSquarePlus size={16} />
            </IconButton>
          )}
        </aside>
      ) : (
      <aside
        className={clsx(
          
          
          'flex w-[240px] shrink-0 flex-col overflow-hidden rounded-[12px] border border-line bg-panel',
          standalone && 'hidden',
        )}
      >
        {
}
        <div className="flex h-11 shrink-0 items-center justify-between px-2.5">
          <div className="flex items-center gap-1.5 pl-0.5 text-[13px] font-medium text-ink">
            <MessageSquarePlus size={14} className="text-brand" />
            对话
          </div>
          <IconButton
            label="隐藏对话列表"
            onClick={toggleThreadsCollapsed}
            className="mt-0.5 shrink-0 text-ink-faint"
          >
            <PanelLeftClose size={15} />
          </IconButton>
        </div>
        {





}
        {isReadonly || !selected ? null : (
          <div className="shrink-0 px-2 pb-1.5">
            <Button
              variant="secondary"
              size="sm"
              icon={<Settings2 size={13} />}
              className="h-8 w-full justify-center"
              onClick={() => {
                
                setEditName(selected.name)
                setEditAvatar(selected.avatar)
                setEditPicked([...selected.member_assistant_ids])
                setShowSettings(true)
              }}
            >
              群设置
            </Button>
          </div>
        )}
        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
          {threads.length === 0 ? (
            <p className="px-2 py-8 text-center text-[12px] text-ink-faint">正在载入对话…</p>
          ) : (
            threads.map((thread) => {
              const activeItem = thread.id === activeThreadId
              const editingThis = renamingId === thread.id
              return (
                <div
                  key={thread.id}
                  
                  
                  role="button"
                  tabIndex={0}
                  onClick={() => void selectThread(thread.id)}
                  
                  onDoubleClick={() => setRenamingId(thread.id)}
                  onContextMenu={(event) => {
                    event.preventDefault()
                    
                    
                    
                    setMenu(null)
                    setThreadMenu({
                      groupId: selectedId ?? '',
                      thread,
                      x: event.clientX,
                      y: event.clientY,
                    })
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      void selectThread(thread.id)
                    }
                  }}
                  className={clsx(
                    'group mb-0.5 flex w-full cursor-pointer items-center gap-1 rounded-[8px] px-2.5 py-2 text-left transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-brand',
                    activeItem ? 'bg-brand-soft' : 'hover:bg-hover',
                  )}
                >
                  {editingThis ? (
                    <input
                      autoFocus
                      defaultValue={thread.title}
                      onClick={(event) => event.stopPropagation()}
                      onBlur={(event) => {
                        setRenamingId(null)
                        const next = event.target.value.trim()
                        if (next && next !== thread.title) void renameThread(thread.id, next)
                      }}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') event.currentTarget.blur()
                        if (event.key === 'Escape') setRenamingId(null)
                      }}
                      className="h-6 min-w-0 flex-1 rounded-[6px] border border-line bg-canvas px-1.5 text-[12.5px] text-ink focus:border-brand focus:outline-none"
                    />
                  ) : (
                    







                    <div className="min-w-0 flex-1">
                      <div
                        className={clsx(
                          'truncate text-[13px]',
                          activeItem ? 'text-brand' : 'text-ink',
                        )}
                        title={thread.title}
                      >
                        {thread.title}
                      </div>
                      <div className="mt-0.5 text-[11px] text-ink-faint">
                        {formatFull(new Date(thread.updated_at).getTime())}
                      </div>
                    </div>
                  )}
                  {isReadonly || editingThis ? null : (
                    <button
                      type="button"
                      aria-label="删除这条对话"
                      title="删除这条对话"
                      onClick={(event) => {
                        event.stopPropagation()
                        setPendingDeleteThread(thread)
                      }}
                      className="hidden shrink-0 rounded-[6px] p-1 text-ink-faint hover:bg-hover hover:text-danger group-hover:block"
                    >
                      <Trash2 size={12} />
                    </button>
                  )}
                </div>
              )
            })
          )}
        </div>
      </aside>
      )}

      {











}
      <div className="flex min-w-0 flex-1 flex-col gap-[3px]">
        {selected ? (
          <>
            {











}
            {isReadonly ? (
              
              
              
              <div className="flex h-11 shrink-0 items-center gap-2 border-b border-line bg-canvas px-4">
                <span className="rounded-full bg-brand-soft px-2 py-0.5 text-[11px] text-brand">
                  观察窗（只读）
                </span>
                <span className="min-w-0 flex-1 truncate text-[11px] text-ink-faint">
                  AI 正在后台讨论这一场，这里只能看
                </span>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={stopping}
                  onClick={() => void pauseTask()}
                >
                  {stopping ? '暂停中…' : '暂停任务'}
                </Button>
              </div>
            ) : null}

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

              <div
                ref={scrollRef}
                onScroll={onScroll}
                className="h-full overflow-y-auto px-4 py-4"
              >
              {bubbles.length === 0 ? (
                








                <div className="mx-auto flex h-full w-full flex-col items-center px-6 py-10">
                  {




}
                  <div className="flex min-h-0 w-full flex-1 flex-col items-center justify-end">
                    {







}
                    <GroupAvatar group={selected} size={176} />
                  </div>
                  <div className="flex min-h-0 w-full flex-1 flex-col items-center pt-3">
                    <h1 className="shrink-0 text-[19px] font-semibold text-ink">
                      {selected.name}
                    </h1>
                    <div className="mt-1.5 min-h-0 w-full flex-1 overflow-y-auto px-1">
                      <div className="mx-auto max-w-[520px] text-center text-[13px] leading-relaxed text-ink-soft">
                        {memberNames.length > 0 ? (
                          <p>{memberNames.join('、')}</p>
                        ) : (
                          <p>这个群还没有搭子，去「群设置」拉几个进来。</p>
                        )}
                        <p className="mt-1">
                          抛出一个话题（例如「帮我定一下这周的学习计划」），它们会自己讨论到达成结论。
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                
                
                
                <div className="flex w-full flex-col gap-3">
                  {bubbles.map((item) =>
                    item.kind === 'system' ? (
                      <div key={item.id} className="flex items-center justify-center">
                        <span className="rounded-full bg-panel px-2.5 py-0.5 text-[11px] text-ink-faint">
                          {item.content}
                        </span>
                      </div>
                    ) : (
                      <div
                        key={item.id}
                        className={clsx('flex gap-2.5', item.kind === 'user' ? 'flex-row-reverse' : '')}
                      >
                        {









}
                        {item.kind === 'user' ? (
                          <button
                            type="button"
                            onClick={() => useUserProfileDialogStore.getState().show()}
                            title="修改我的资料"
                            aria-label="修改我的资料"
                            className="mt-0.5 shrink-0 cursor-pointer overflow-hidden"
                            style={{ width: 26, height: 26, borderRadius: Math.round(26 * (6 / 22)) }}
                          >
                            {userAvatar ? (
                              <img
                                src={userAvatar}
                                alt="我"
                                width={26}
                                height={26}
                                draggable={false}
                                className="h-full w-full object-cover select-none"
                              />
                            ) : (
                              <span className="flex h-full w-full items-center justify-center bg-brand-soft text-[11px] text-brand">
                                我
                              </span>
                            )}
                          </button>
                        ) : (
                          <AssistantAvatar
                            profile={byId.get(item.assistantId ?? '') ?? { name: item.name, emoji: '🤖', avatar: '' }}
                            size={26}
                          />
                        )}
                        {



}
                        <div className="max-w-[78%]">
                          <div
                            className={clsx(
                              'mb-0.5 flex items-center gap-1.5 text-[11px] text-ink-faint',
                              item.kind === 'user' && 'justify-end',
                            )}
                          >
                            {item.kind === 'user' ? '我' : item.name}
                            {item.badge ? (
                              <span className="rounded bg-brand-soft px-1 py-px text-[10px] text-brand">
                                {item.badge}
                              </span>
                            ) : null}
                          </div>
                          {











}
                          {item.kind === 'assistant' && item.reasoning ? (
                            <ReasoningBlock text={item.reasoning} />
                          ) : null}
                          {item.kind === 'assistant'
                            ? (item.toolCalls ?? []).map((tool) => (
                                <ToolCallCard key={tool.id} tool={tool} />
                              ))
                            : null}
                          <div
                            className={clsx(
                              'inline-block rounded-[10px] px-3 py-2 text-left text-[13px] leading-relaxed',
                              item.kind === 'user'
                                ? 'bg-brand whitespace-pre-wrap text-white'
                                : item.kind === 'summary'
                                  ? 'border border-brand/40 bg-brand-soft/40 text-ink'
                                  : 'border border-line bg-canvas text-ink',
                            )}
                          >
                            {

}
                            {item.kind === 'user' ? item.content : <Markdown content={item.content} />}
                            {item.streaming ? (
                              <span className="ml-0.5 inline-block animate-pulse">▍</span>
                            ) : null}
                          </div>
                        </div>
                      </div>
                    ),
                  )}
                  {busy ? (
                    <div className="flex items-center gap-2 text-[12px] text-ink-faint">
                      <Loader2 size={13} className="animate-spin" />
                      搭子们正在讨论…
                    </div>
                  ) : null}
                </div>
              )}

              {


}
              {showJump ? (
                <button
                  type="button"
                  onClick={jumpToBottom}
                  className={clsx(
                    'no-drag sticky bottom-2 mx-auto flex w-fit items-center gap-1.5 rounded-full',
                    'border border-line bg-canvas px-3 py-1 text-[12px] text-ink-soft shadow-[0_4px_12px_rgba(0,0,0,0.10)] hover:text-ink',
                  )}
                >
                  <ChevronDown size={13} />
                  回到最新
                </button>
              ) : null}
              </div>
            </div>

            {

}
            {resumable && !isReadonly ? (
              <div className="mx-4 mb-1.5 flex items-start gap-2 rounded-[10px] border border-warning/30 bg-warning-soft px-3 py-2">
                <AlertTriangle size={13} className="mt-0.5 shrink-0 text-warning" />
                <div className="min-w-0 flex-1">
                  <div className="text-[12px] text-ink">{resumable.summary}</div>
                  <div className="mt-0.5 text-[11px] text-ink-faint">
                    共 {resumable.step} 条发言 · {formatFull(resumable.updated_at * 1000)}
                  </div>
                </div>
                <Button size="sm" variant="primary" onClick={() => void resumeDiscussion()}>
                  继续讨论
                </Button>
                <Button size="sm" variant="secondary" onClick={() => void dropResumable()}>
                  忽略
                </Button>
              </div>
            ) : null}

            {isReadonly ? (
              
              
              
              <div className="border-t border-line bg-canvas px-4 py-3 text-[12px] leading-relaxed text-ink-faint">
                这是 AI 在后台讨论的**观察窗**：只能看，不能在这里发言。
                想参与讨论，请到主窗口的「群聊」页，或在大厅里用「新窗口打开」开一个可操作的群窗口。
              </div>
            ) : (
              <ComposerShell
                










                







                onNewSession={isReadonly ? undefined : () => void startNewThread()}
                









                toolbarLeft={
                  isReadonly || !selected ? undefined : (
                    <>
                      <ReasoningEffortButton
                        value={selected.reasoning_effort}
                        visible
                        disabled={savingSettings}
                        
                        
                        nullLabel="跟随每个搭子"
                        nullDetail="这个群不统一指定，各自按搭子档案里的档位"
                        note="只对这个群生效，会覆盖每个搭子自己的思考强度设置。"
                        onChange={(next) =>
                          
                          
                          
                          void saveGroupPolicy({
                            reasoning_effort: (next ?? '') as GroupUpdate['reasoning_effort'],
                          })
                        }
                      />
                      <ConfirmModeButton
                        value={selected.confirm_mode ?? 'interactive'}
                        disabled={savingSettings}
                        note={
                          selected.confirm_mode === null
                            ? '当前跟随每个搭子自己的设置；在这里选一档就固定为群级设置。高危操作始终会弹窗询问。'
                            : '群设置优先于搭子档案；高危操作始终会弹窗询问。'
                        }
                        onChange={(next) => void saveGroupPolicy({ confirm_mode: next })}
                      />
                    </>
                  )
                }
                









                footerLeft={
                  isReadonly ? null : (
                    <button
                      type="button"
                      
                      
                      onClick={() => window.agentBridge?.openGroupWindow?.(selected.id, false)}
                      className="flex items-center gap-1 rounded-[6px] px-1.5 py-0.5 hover:bg-hover hover:text-ink"
                    >
                      <PictureInPicture2 size={13} />
                      打开独立窗口
                    </button>
                  )
                }
                footerCenter={
                  isReadonly ? null : (
                    <button
                      type="button"
                      disabled={busy || bubbles.length === 0}
                      onClick={() => setPendingClear(true)}
                      className="flex items-center gap-1 rounded-[6px] px-1.5 py-0.5 hover:bg-hover hover:text-ink disabled:opacity-40 disabled:hover:bg-transparent"
                    >
                      <Eraser size={13} />
                      {
}
                      清空这条对话
                    </button>
                  )
                }
                footerRight={
                  isReadonly ? null : (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => setPendingDelete(true)}
                      className="flex items-center gap-1 rounded-[6px] px-1.5 py-0.5 hover:bg-hover hover:text-danger disabled:opacity-40 disabled:hover:bg-transparent"
                    >
                      删除群
                      <Trash2 size={13} />
                    </button>
                  )
                }
                value={draft}
                onChange={setDraft}
                onSubmit={() => void discuss()}
                busy={busy}
                onStop={stop}
                placeholder="抛出一个话题，搭子们会自己讨论到收敛；可以拖入文件或粘贴图片"
                attachments={attachments}
                onFiles={(files) => void addFiles(files)}
                onRemoveAttachment={removeAttachment}
                paletteOpen={paletteOpen}
                paletteItems={paletteItems}
                paletteEmptyText="群里没有这个命令"
                onPaletteSelect={runGroupCommand}
                






              />
            )}
          </>
        ) : (
          <div className="flex flex-1 items-center justify-center text-[12.5px] text-ink-faint">
            选择左侧的搭子群开始。
          </div>
        )}
      </div>

      {



}
      <UserProfileDialog
        open={profileDialogOpen}
        onClose={() => useUserProfileDialogStore.getState().hide()}
      />

      {


}
      <Modal
        open={pendingDeleteThread !== null}
        onClose={() => setPendingDeleteThread(null)}
        width="max-w-sm"
        title="删除这条对话？"
        description={
          pendingDeleteThread
            ? `「${pendingDeleteThread.title}」里的全部记录会被一起删掉，无法恢复。群本身和其它对话不受影响。`
            : ''
        }
        footer={
          <>
            <Button onClick={() => setPendingDeleteThread(null)}>取消</Button>
            <Button
              variant="primary"
              onClick={() => {
                const target = pendingDeleteThread
                setPendingDeleteThread(null)
                if (target) void deleteThread(target.id)
              }}
            >
              删除
            </Button>
          </>
        }
      >
        {}
        {null}
      </Modal>

      {}
      <Modal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        width="max-w-md"
        title="新建搭子群"
        description="勾选要拉进群的搭子；抛出一个话题后，它们会自己讨论、互相接话。"
        footer={
          <>
            <Button onClick={() => setShowCreate(false)}>取消</Button>
            {







}
            <Button
              variant="primary"
              disabled={!newName.trim()}
              onClick={() => void submitCreate()}
            >
              创建
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {







}
          <input
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
            placeholder="群名称（必填），例如 我的智囊团"
            className="h-9 w-full rounded-[8px] border-2 border-brand/40 bg-canvas px-3 text-[13px] text-ink transition-colors placeholder:font-medium placeholder:text-brand/60 focus:border-brand focus:outline-none"
          />

          {


}
          <GroupAvatarPicker
            value={newAvatar}
            onChange={setNewAvatar}
            hint="不上传也行，会自动配一张。"
          />
          <div className="max-h-[240px] overflow-y-auto rounded-[8px] border border-line">
            {assistants.map((assistant) => (
              <label
                key={assistant.id}
                className="flex cursor-pointer items-center gap-2.5 border-b border-line-soft px-3 py-2 last:border-b-0 hover:bg-hover"
              >
                <input
                  type="checkbox"
                  checked={picked.includes(assistant.id)}
                  onChange={() => togglePick(assistant.id)}
                  className="h-3.5 w-3.5 accent-[var(--app-brand)]"
                />
                <AssistantAvatar profile={assistant} size={22} />
                <span className="text-[13px] text-ink">{assistant.name}</span>
              </label>
            ))}
          </div>
          {}
          {picked.length > 0 ? (
            <div className="rounded-[8px] border border-line px-3 py-2">
              <div className="mb-1.5 text-[11.5px] text-ink-soft">
                发言顺序（从上到下依次发言，可调整）
              </div>
              <div className="space-y-1">
                {picked.map((id, index) => (
                  <div key={id} className="flex items-center gap-2">
                    <span className="w-4 shrink-0 text-[11px] text-ink-faint">{index + 1}.</span>
                    <AssistantAvatar profile={byId.get(id) ?? { name: id, emoji: '🤖', avatar: '' }} size={18} />
                    <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink">
                      {byId.get(id)?.name ?? id}
                    </span>
                    <button
                      type="button"
                      disabled={index === 0}
                      onClick={() => movePick(index, -1)}
                      title="上移"
                      aria-label="上移"
                      className="no-drag flex h-6 w-6 items-center justify-center rounded-[5px] text-ink-faint hover:bg-hover hover:text-ink disabled:opacity-30 disabled:hover:bg-transparent"
                    >
                      <ChevronUp size={13} />
                    </button>
                    <button
                      type="button"
                      disabled={index === picked.length - 1}
                      onClick={() => movePick(index, 1)}
                      title="下移"
                      aria-label="下移"
                      className="no-drag flex h-6 w-6 items-center justify-center rounded-[5px] text-ink-faint hover:bg-hover hover:text-ink disabled:opacity-30 disabled:hover:bg-transparent"
                    >
                      <ChevronDown size={13} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          <div className="flex items-start gap-2 rounded-[8px] border border-line-soft bg-panel px-3 py-2 text-[11.5px] leading-relaxed text-ink-faint">
            <AlertCircle size={13} className="mt-0.5 shrink-0" />
            <span>
              填好群名称、并至少勾选一个搭子，「创建」按钮才会变为可用。
              <br />
              注意：群聊中搭子们会相互讨论、多轮发言，可能消耗较多 token。
            </span>
          </div>
        </div>
      </Modal>

      {}
      <Modal
        open={showSettings}
        onClose={() => setShowSettings(false)}
        width="max-w-md"
        title="群设置"
        description="改群名、增减搭子、调整发言顺序；保存后立刻生效。"
        footer={
          <>
            <Button onClick={() => setShowSettings(false)}>取消</Button>
            <Button
              variant="primary"
              disabled={!editName.trim() || savingSettings}
              onClick={() => void submitSettings()}
            >
              {savingSettings ? '保存中…' : '保存'}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {}
          <GroupAvatarPicker
            value={editAvatar}
            onChange={setEditAvatar}
            hint="不上传也行，会自动配一张。"
          />
          <input
            value={editName}
            onChange={(event) => setEditName(event.target.value)}
            placeholder="群名称"
            className="h-9 w-full rounded-[8px] border border-line bg-canvas px-3 text-[13px] text-ink placeholder:text-ink-faint focus:border-brand focus:outline-none"
          />
          <div className="max-h-[220px] overflow-y-auto rounded-[8px] border border-line">
            {assistants.map((assistant) => (
              <label
                key={assistant.id}
                className="flex cursor-pointer items-center gap-2.5 border-b border-line-soft px-3 py-2 last:border-b-0 hover:bg-hover"
              >
                <input
                  type="checkbox"
                  checked={editPicked.includes(assistant.id)}
                  onChange={() =>
                    setEditPicked((prev) =>
                      prev.includes(assistant.id)
                        ? prev.filter((item) => item !== assistant.id)
                        : [...prev, assistant.id],
                    )
                  }
                  className="h-3.5 w-3.5 accent-[var(--app-brand)]"
                />
                <AssistantAvatar profile={assistant} size={22} />
                <span className="text-[13px] text-ink">{assistant.name}</span>
              </label>
            ))}
          </div>
          {editPicked.length > 0 ? (
            <div className="rounded-[8px] border border-line px-3 py-2">
              <div className="mb-1.5 text-[11.5px] text-ink-soft">
                发言顺序（从上到下依次发言，可调整）
              </div>
              <div className="space-y-1">
                {editPicked.map((id, index) => (
                  <div key={id} className="flex items-center gap-2">
                    <span className="w-4 shrink-0 text-[11px] text-ink-faint">{index + 1}.</span>
                    <AssistantAvatar profile={byId.get(id) ?? { name: id, emoji: '🤖', avatar: '' }} size={18} />
                    <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink">
                      {byId.get(id)?.name ?? id}
                    </span>
                    <button
                      type="button"
                      disabled={index === 0}
                      onClick={() =>
                        setEditPicked((prev) => {
                          const next = [...prev]
                          ;[next[index], next[index - 1]] = [next[index - 1], next[index]]
                          return next
                        })
                      }
                      title="上移"
                      aria-label="上移"
                      className="no-drag flex h-6 w-6 items-center justify-center rounded-[5px] text-ink-faint hover:bg-hover hover:text-ink disabled:opacity-30 disabled:hover:bg-transparent"
                    >
                      <ChevronUp size={13} />
                    </button>
                    <button
                      type="button"
                      disabled={index === editPicked.length - 1}
                      onClick={() =>
                        setEditPicked((prev) => {
                          const next = [...prev]
                          ;[next[index], next[index + 1]] = [next[index + 1], next[index]]
                          return next
                        })
                      }
                      title="下移"
                      aria-label="下移"
                      className="no-drag flex h-6 w-6 items-center justify-center rounded-[5px] text-ink-faint hover:bg-hover hover:text-ink disabled:opacity-30 disabled:hover:bg-transparent"
                    >
                      <ChevronDown size={13} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          <div className="flex items-start gap-2 rounded-[8px] border border-line-soft bg-panel px-3 py-2 text-[11.5px] leading-relaxed text-ink-faint">
            <AlertCircle size={13} className="mt-0.5 shrink-0" />
            <span>至少要留两个搭子，否则讨论不起来。</span>
          </div>
        </div>
      </Modal>

      {}
      <Modal
        open={pendingClear}
        onClose={() => setPendingClear(false)}
        width="max-w-md"
        title="清空群聊记录"
        description="只清掉这个群的讨论记录，群本身和成员都保留。"
        footer={
          <>
            <Button onClick={() => setPendingClear(false)}>取消</Button>
            <Button
              variant="danger"
              onClick={() => {
                setPendingClear(false)
                void clearMessages()
              }}
            >
              清空
            </Button>
          </>
        }
      >
        <p className="text-[13px] text-ink">
          确定清空「{selected?.name}」的 {bubbles.length} 条记录吗？清空后无法恢复。
        </p>
      </Modal>

      {}
      <Modal
        open={pendingDelete}
        onClose={() => setPendingDelete(false)}
        width="max-w-md"
        title="删除搭子群"
        description="群和它的讨论记录都会被删除。"
        footer={
          <>
            <Button onClick={() => setPendingDelete(false)}>取消</Button>
            <Button
              variant="danger"
              onClick={() => {
                setPendingDelete(false)
                if (selected) void deleteGroup(selected.id)
              }}
            >
              删除
            </Button>
          </>
        }
      >
        <p className="text-[13px] text-ink">
          确定删除「{selected?.name}」吗？成员搭子本身不会被删除。
        </p>
      </Modal>

      {






}
      {menu ? (
        <GroupContextMenu
          name={menu.group.name}
          x={menu.x}
          y={menu.y}
          onSettings={() => {
            void selectGroup(menu.group.id)
            
            
            const fresh =
              useGroupStore.getState().groups.find((item) => item.id === menu.group.id) ??
              menu.group
            setEditName(fresh.name)
            setEditAvatar(fresh.avatar)
            setEditPicked([...fresh.member_assistant_ids])
            setShowSettings(true)
            setMenu(null)
          }}
          onDelete={() => {
            void selectGroup(menu.group.id)
            setPendingDelete(true)
            setMenu(null)
          }}
          onClose={() => setMenu(null)}
        />
      ) : null}

      {







}
      {threadMenu ? (
        <GroupThreadContextMenu
          title={threadMenu.thread.title}
          x={threadMenu.x}
          y={threadMenu.y}
          onRename={() => {
            setRenamingId(threadMenu.thread.id)
            setThreadMenu(null)
          }}
          onOpenWindow={() => {
            
            window.agentBridge?.openGroupWindow?.(
              threadMenu.groupId,
              false,
              threadMenu.thread.id,
            )
            setThreadMenu(null)
          }}
          onClear={() => {
            const target = threadMenu.thread
            void selectThread(target.id).then(() => setPendingClear(true))
            setThreadMenu(null)
          }}
          onDelete={() => {
            setPendingDeleteThread(threadMenu.thread)
            setThreadMenu(null)
          }}
          onClose={() => setThreadMenu(null)}
        />
      ) : null}
    </div>
  )
}
