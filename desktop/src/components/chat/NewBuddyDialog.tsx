import { ChevronRight, FileJson, Package, Settings2, type LucideIcon } from 'lucide-react'
import { useEffect, useState } from 'react'

import { BuddyImportPanel } from '@/components/chat/BuddyImportPanel'
import { Modal } from '@/components/ui'














export type NewBuddyChoice = 'manual' | 'buddy' | 'group'

const OPTIONS: Array<{
  key: NewBuddyChoice
  label: string
  hint: string
  icon: LucideIcon
}> = [
  {
    key: 'manual',
    label: '手动配置',
    hint: '自己写名称、人格与技能，逐项填',
    icon: Settings2,
  },
  {
    key: 'buddy',
    label: '导入搭子',
    hint: '一个压缩包：搭子配置 + 它的技能包',
    icon: FileJson,
  },
  {
    key: 'group',
    label: '导入搭子群',
    hint: '一个压缩包：群配置 + 多个搭子包',
    icon: Package,
  },
]

export function NewBuddyDialog({
  open,
  onClose,
  onPick,
}: {
  open: boolean
  onClose: () => void
  onPick: (choice: NewBuddyChoice) => void
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      width="max-w-md"
      title="新建搭子"
      description="挑一种方式。导入的搭子可以直接用，技能会一起装好。"
    >
      <div className="flex flex-col gap-2">
        {OPTIONS.map((option) => {
          const Icon = option.icon
          return (
            <button
              key={option.key}
              type="button"
              onClick={() => onPick(option.key)}
              className="flex w-full items-center gap-3 rounded-[10px] border border-line bg-canvas px-3 py-2.5 text-left transition-colors hover:border-brand/40 hover:bg-hover active:scale-[0.995]"
            >
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[9px] bg-brand-soft text-brand">
                <Icon size={15} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-[13px] font-medium text-ink">{option.label}</span>
                <span className="mt-0.5 block text-[11.5px] leading-relaxed text-ink-faint">
                  {option.hint}
                </span>
              </span>
              <ChevronRight size={14} className="shrink-0 text-ink-faint" />
            </button>
          )
        })}
      </div>

      <p className="mt-3 text-[11.5px] leading-relaxed text-ink-faint">
        说明：导入**不带导出**功能。搭子群包里不包含优化顾问与审核员 ——
        这两个角色仍由你在群里按既有流程指定。
      </p>
    </Modal>
  )
}







export function NewBuddyFlow({
  open,
  onClose,
  onManual,
}: {
  open: boolean
  onClose: () => void
  
  onManual: () => void
}) {
  const [kind, setKind] = useState<'buddy' | 'group' | null>(null)

  
  useEffect(() => {
    if (!open) setKind(null)
  }, [open])

  return (
    <>
      <NewBuddyDialog
        open={open && kind === null}
        onClose={onClose}
        onPick={(choice) => {
          if (choice === 'manual') {
            onManual()
            return
          }
          setKind(choice)
        }}
      />
      <BuddyImportPanel
        open={open && kind !== null}
        kind={kind ?? 'buddy'}
        onClose={() => setKind(null)}
      />
    </>
  )
}
