










import { Settings2 } from 'lucide-react'

import { Modal } from '@/components/ui'
import { useAssistantStore } from '@/stores/assistantStore'
import { useAvatarPreviewStore } from '@/stores/avatarPreviewStore'
import { useGroupStore } from '@/stores/groupStore'

export function AvatarPreview() {
  const src = useAvatarPreviewStore((state) => state.src)
  const name = useAvatarPreviewStore((state) => state.name)
  const assistantId = useAvatarPreviewStore((state) => state.assistantId)
  const groupId = useAvatarPreviewStore((state) => state.groupId)
  const close = useAvatarPreviewStore((state) => state.close)

  
  
  
  
  
  const assistants = useAssistantStore((state) => state.assistants)
  const profile = assistantId ? assistants.find((item) => item.id === assistantId) : undefined

  if (!src) return null

  return (
    
    <Modal
      open
      onClose={close}
      title={name}
      width="max-w-[640px]"
      
      
      
      centerTitleExtra
      







      titleExtra={
        profile ? (
          <button
            type="button"
            onClick={() => {
              close()
              
              
              useAssistantStore.getState().openEditor(profile.id)
            }}
            className="flex shrink-0 items-center gap-1.5 rounded-[8px] border border-line px-3 py-1 text-[12.5px] text-ink-soft transition-colors hover:bg-hover hover:text-ink"
          >
            <Settings2 size={13} />
            配置搭子
          </button>
        ) : groupId ? (
          <button
            type="button"
            onClick={() => {
              close()
              





              useGroupStore.getState().requestGroupSettings(groupId)
            }}
            className="flex shrink-0 items-center gap-1.5 rounded-[8px] border border-line px-3 py-1 text-[12.5px] text-ink-soft transition-colors hover:bg-hover hover:text-ink"
          >
            <Settings2 size={13} />
            群设置
          </button>
        ) : null
      }
    >
      {









}
      <div className="flex justify-center">
        <img
          src={src}
          alt={name}
          className="aspect-square w-full max-w-[560px] rounded-[12px] border border-line object-cover select-none"
          draggable={false}
        />
      </div>
    </Modal>
  )
}
