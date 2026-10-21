import clsx from 'clsx'
import { PanelLeftClose, PanelRightClose, Plus } from 'lucide-react'
import { Fragment, useEffect, useState } from 'react'

import {
  AssistantAvatar,
  AssistantFormModal,
  blankProfile,
} from '@/components/chat/AssistantFormModal'
import { AssistantContextMenu } from '@/components/chat/AssistantContextMenu'
import { NewBuddyFlow } from '@/components/chat/NewBuddyDialog'
import { Button, IconButton, Modal } from '@/components/ui'
import { useCollapsed } from '@/lib/collapse'
import { switchAssistant } from '@/services/assistantSwitch'
import { useAssistantStore } from '@/stores/assistantStore'
import { useVoiceCommand } from '@/stores/voiceCommandStore'
import type { AssistantProfile } from '@/types'












export function AssistantRail() {
  const assistants = useAssistantStore((state) => state.assistants)
  const activeId = useAssistantStore((state) => state.activeId)
  const remove = useAssistantStore((state) => state.remove)

  
  
  
  

  const [menu, setMenu] = useState<{ profile: AssistantProfile; x: number; y: number } | null>(null)
  
  const [newOpen, setNewOpen] = useState(false)
  const [editing, setEditing] = useState<{ profile: AssistantProfile; isNew: boolean } | null>(
    null,
  )
  const [pendingDelete, setPendingDelete] = useState<AssistantProfile | null>(null)

  





  const editRequestId = useAssistantStore((state) => state.editRequestId)
  const clearEditRequest = useAssistantStore((state) => state.clearEditRequest)
  useEffect(() => {
    if (!editRequestId) return
    const target = assistants.find((item) => item.id === editRequestId)
    clearEditRequest()
    if (target) setEditing({ profile: target, isNew: false })
  }, [editRequestId, assistants, clearEditRequest])

  






  const newRequest = useAssistantStore((state) => state.newRequest)
  const clearNewRequest = useAssistantStore((state) => state.clearNewRequest)
  useEffect(() => {
    if (!newRequest) return
    clearNewRequest()
    setNewOpen(true)
  }, [newRequest, clearNewRequest])

  

















  const switchTo = (id: string) => {
    
    
    if (id === activeId) return
    
    
    
    switchAssistant(id)
  }

  const confirmDelete = async () => {
    const target = pendingDelete
    setPendingDelete(null)
    if (!target) return

    const wasActive = target.id === useAssistantStore.getState().activeId
    await remove(target.id)

    
    
    if (!wasActive) return
    const rest = useAssistantStore.getState().assistants
    if (rest.length > 0) switchTo(rest[0].id)
  }

  
  
  const [collapsed, toggleCollapsed, setCollapsed] = useCollapsed('rail:assistants')

  
  
  
  
  
  
  useVoiceCommand('panel.assistantRail', () => setCollapsed(true))
  useVoiceCommand('panel.assistantRailExpand', () => setCollapsed(false))
  useVoiceCommand('buddy.new', () => setNewOpen(true))

  if (collapsed) {
    return (
      <aside className="flex w-[44px] shrink-0 flex-col items-center overflow-hidden rounded-[12px] border border-line bg-panel py-2.5">
        {
}
        {



}
        <IconButton label="展开助手栏" onClick={toggleCollapsed} className="text-ink-faint">
          <PanelRightClose size={15} />
        </IconButton>
        <div className="mt-3 flex min-h-0 flex-1 flex-col items-center gap-1.5 overflow-y-auto">
          {assistants.map((profile) => (
            <button
              key={profile.id}
              type="button"
              title={profile.name}
              onClick={() => switchTo(profile.id)}
              className={clsx(
                'rounded-[7px] p-0.5 transition-opacity',
                profile.id === activeId ? 'ring-1 ring-brand/50' : 'opacity-70 hover:opacity-100',
              )}
            >
              <AssistantAvatar profile={profile} size={22} />
            </button>
          ))}
        </div>
      </aside>
    )
  }

  return (
    <aside className="flex w-[240px] shrink-0 flex-col overflow-hidden rounded-[12px] border border-line bg-panel">
      {}
      <div className="flex h-11 shrink-0 items-center gap-1.5 px-2.5">
        <Button
          variant="secondary"
          size="sm"
          icon={<Plus size={13} />}
          








          className="!h-8 flex-1"
          
          onClick={() => setNewOpen(true)}
        >
          New Buddy
        </Button>
        {}
        {

}
        <IconButton
          label="隐藏助手栏"
          onClick={toggleCollapsed}
          className="mt-0.5 shrink-0 text-ink-faint"
        >
          <PanelLeftClose size={15} />
        </IconButton>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-2">
        {assistants.length === 0 ? (
          <p className="px-2 py-3 text-[11.5px] leading-relaxed text-ink-faint">
            还没有搭子。点上面的「New Buddy」创建一个。
          </p>
        ) : null}

        {assistants.map((profile, index) => {
          const selected = profile.id === activeId
          





          const divider = Boolean(assistants[index - 1]?.builtin) && !profile.builtin
          return (
            <Fragment key={profile.id}>
            {divider ? <div className="my-1.5 border-t border-line-soft" /> : null}
            <button
              type="button"
              onClick={() => switchTo(profile.id)}
              
              onContextMenu={(event) => {
                event.preventDefault()
                setMenu({ profile, x: event.clientX, y: event.clientY })
              }}
              className={clsx(
                'mb-0.5 flex w-full items-center gap-2 rounded-[8px] px-2 py-1.5 text-left transition-colors',
                selected
                  ? 'bg-brand-soft font-medium text-brand'
                  : 'text-ink-soft hover:bg-hover hover:text-ink',
              )}
            >
              {

}
              <AssistantAvatar profile={profile} size={24} />
              <span className="min-w-0 flex-1 truncate text-[12.5px]">{profile.name}</span>
              {






}
            </button>
            </Fragment>
          )
        })}
      </div>

      {menu ? (
        <AssistantContextMenu
          profile={menu.profile}
          x={menu.x}
          y={menu.y}
          isActive={menu.profile.id === activeId}
          onClose={() => setMenu(null)}
          onEdit={() => {
            setEditing({ profile: menu.profile, isNew: false })
            setMenu(null)
          }}
          onSetActive={() => {
            switchTo(menu.profile.id)
            setMenu(null)
          }}
          onDelete={() => {
            setPendingDelete(menu.profile)
            setMenu(null)
          }}
        />
      ) : null}

      <AssistantFormModal
        open={editing !== null}
        initial={editing?.profile ?? null}
        isNew={editing?.isNew ?? true}
        onClose={() => setEditing(null)}
      />

      {}
      <NewBuddyFlow
        open={newOpen}
        onClose={() => setNewOpen(false)}
        onManual={() => {
          setNewOpen(false)
          setEditing({ profile: blankProfile(), isNew: true })
        }}
      />

      <Modal
        open={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        title="删除搭子"
        width="max-w-md"
        description="这个搭子会被删除，但它名下的对话不会丢，之后仍能在其他搭子下打开。"
        footer={
          <>
            <Button onClick={() => setPendingDelete(null)}>取消</Button>
            <Button variant="danger" onClick={() => void confirmDelete()}>
              删除
            </Button>
          </>
        }
      >
        <p className="text-[12.5px] leading-relaxed text-ink-soft">
          确定要删除「{pendingDelete?.name}」吗？
          {pendingDelete?.builtin
            ? 







              ' 它是内置搭子（出厂自带、名称与简介由产品固定），删掉之后无法找回。'
            : ''}
        </p>
      </Modal>
    </aside>
  )
}
