import { Check, Copy, MessageCircle } from 'lucide-react'
import { useState } from 'react'
import { create } from 'zustand'

import { Modal } from '@/components/ui'
import { useAccountStore } from '@/stores/accountStore'
import { useClosableDialog } from '@/stores/transientDialogs'



























const useFeedbackStore = create<{ open: boolean; setOpen: (value: boolean) => void }>((set) => ({
  open: false,
  setOpen: (value) => set({ open: value }),
}))


export function openFeedback(): void {
  useFeedbackStore.getState().setOpen(true)
}







export function FeedbackDialog() {
  const open = useFeedbackStore((state) => state.open)
  const setOpen = useFeedbackStore((state) => state.setOpen)
  const [copied, setCopied] = useState('')
  
  
  const snapshot = useAccountStore((state) => state.snapshot)
  const forumUrl =
    (snapshot?.line?.preferred ?? 'cn') === 'cn'
      ? 'https://china.xinjianxue.com/forum.html'
      : 'https://www.xinjianxue.com/forum.html'

  
  
  
  useClosableDialog('FeedbackDialog', open, () => setOpen(false))

  const copy = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(value)
      window.setTimeout(() => setCopied((current) => (current === value ? '' : current)), 1600)
    } catch {
      
      
    }
  }

  return (
    <Modal
      open={open}
      onClose={() => setOpen(false)}
      width="max-w-md"
      title="反馈与联系"
      description="到开源社区反馈，你的意见我们都会看。"
    >
      <div className="overflow-hidden rounded-[10px] border border-line">
        <div className="flex items-center gap-2.5 border-b border-line-soft px-3 py-2.5 last:border-b-0">
          {}
          <MessageCircle size={14} className="shrink-0 text-ink-faint" aria-hidden="true" />
          <span className="w-8 shrink-0 text-[12px] text-ink-faint">社区</span>
          {


}
          <button
            type="button"
            onClick={() => void window.agentBridge?.openExternal(forumUrl)}
            title={`用默认浏览器打开：${forumUrl}`}
            className="min-w-0 flex-1 truncate text-left font-mono text-[12.5px] text-brand hover:underline focus-visible:ring-2 focus-visible:ring-brand/60 focus-visible:outline-none"
          >
            {forumUrl}
          </button>
          <button
            type="button"
            onClick={() => void copy(forumUrl)}
            className="no-drag flex shrink-0 items-center gap-1 rounded-[6px] px-1.5 py-0.5 text-[11.5px] text-ink-faint transition-colors hover:bg-hover hover:text-ink"
          >
            {copied === forumUrl ? <Check size={11} /> : <Copy size={11} />}
            {copied === forumUrl ? '已复制' : '复制'}
          </button>
        </div>
      </div>

      {






}
      <div className="mt-3 rounded-[10px] border border-brand/25 bg-brand-soft px-3 py-2.5 text-[12px] leading-relaxed text-ink">
        <span className="text-ink-soft">
          反馈时请顺带说明你用的账号名，方便我们发放贡献度（Token）奖励。
        </span>
      </div>
    </Modal>
  )
}
