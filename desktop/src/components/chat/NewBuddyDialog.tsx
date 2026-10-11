import { ChevronRight, FileJson, Package, Settings2, type LucideIcon } from 'lucide-react'
import { useEffect, useState } from 'react'

import { BuddyImportPanel } from '@/components/chat/BuddyImportPanel'
import { Modal } from '@/components/ui'

/**
 * 「New Buddy」点开后的**新建方式选择**。
 *
 * 三选一（产品约定）：
 * ①手动配置（原来的新建表单）
 * ②导入搭子 —— **一个压缩包**：搭子 json + 这个搭子的多个技能包
 * ③导入搭子群 —— **一个压缩包**：group.json + 多个搭子包
 *
 * ⚠️ 这里**没有**「导入技能组」这一项：技能包随搭子包一起进来，
 * 用户不需要分别导两次（产品明确要求"后端只提供一个包"）。
 *
 * 选项写成数组而不是三段硬编码：将来要加一项（比如"从官网挑搭子"）只加一条。
 */
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

/**
 * 「新建搭子」的完整流程：先选方式，选了导入就切到导入面板。
 *
 * 抽成一个组件是为了让**搭子栏**与**设置 → 搭子**两处共用同一份接线 ——
 * 两处各写一遍的话，"在这里能导入、在那里按钮点了没反应"迟早会出现。
 */
export function NewBuddyFlow({
  open,
  onClose,
  onManual,
}: {
  open: boolean
  onClose: () => void
  /** 选了「手动配置」：调用方去开自己的新建表单 */
  onManual: () => void
}) {
  const [kind, setKind] = useState<'buddy' | 'group' | null>(null)

  // 每次重新打开都从"选方式"开始：否则上次停在导入面板，这次点开就直接是它
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
