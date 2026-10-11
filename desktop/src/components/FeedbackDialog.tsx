import { Check, Copy, Mail } from 'lucide-react'
import { useState } from 'react'
import { create } from 'zustand'

import { Modal } from '@/components/ui'
import { useClosableDialog } from '@/stores/transientDialogs'

/**
 * 联系方式：改这里就够（界面上的行由它渲染）。
 *
 * ⚠️ 微信与 QQ 已于 **剔除**（产品要求"只留邮箱"）：三个渠道看起来
 * 是"哪儿都能找到我们"，实际是把用户分散到三条他不确定有没有人看的地方 ——
 * 留一个邮箱，他不用挑。删的时候记得连带清 `lucide-react` 的 import：
 * 那两个图标只在这两行用过，留着会直接触发 tsc 的未使用报错。
 */
const CONTACTS = [{ key: 'email', label: '邮箱', value: '97676414@qq.com', icon: Mail }] as const

/**
 * 反馈弹窗的开关。
 *
 * 用一个小 store 而不是逐层传 prop：这个弹窗是从**左侧导航底部**打开的，
 * 而弹窗本体挂在应用顶层 —— 为了一个布尔值把 props 从上串到下不值当。
 *
 * ⚠️ 这里曾写着"两个入口"（另一个是赞助卡里的「获取兑换码」）。
 * 兑换码功能 整体剔除后，那个入口随之消失，现在只剩一个 ——
 * 但**仍然保留这个小 store**：`openFeedback()` 是个不依赖 React 树的函数，
 * 将来任何地方（托盘、命令、别的卡片）要唤起反馈都能直接调。
 */
const useFeedbackStore = create<{ open: boolean; setOpen: (value: boolean) => void }>((set) => ({
  open: false,
  setOpen: (value) => set({ open: value }),
}))

/** 打开反馈弹窗（任何地方都能调） */
export function openFeedback(): void {
  useFeedbackStore.getState().setOpen(true)
}

/**
 * 反馈与联系。
 *
 * 内容很少，所以做成**弹窗**而不是一个页面：为三行联系方式占一个导航位、
 * 再配一个空荡荡的页面，用户点进去只会觉得"这里没什么"。
 */
export function FeedbackDialog() {
  const open = useFeedbackStore((state) => state.open)
  const setOpen = useFeedbackStore((state) => state.setOpen)
  const [copied, setCopied] = useState('')

  // 登记给语音那条「关闭弹窗」。见 stores/transientDialogs.ts：
  // 只有**主动登记**的弹窗才关得掉 —— 搭子发起的权限确认框不登记，所以那句
  // "关闭弹窗"永远碰不到它。
  useClosableDialog('FeedbackDialog', open, () => setOpen(false))

  const copy = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(value)
      window.setTimeout(() => setCopied((current) => (current === value ? '' : current)), 1600)
    } catch {
      // 剪贴板拿不到（权限/环境）时不提示"已复制"——那会撒谎；
      // 文本本身是可选中的，用户手动复制即可
    }
  }

  return (
    <Modal
      open={open}
      onClose={() => setOpen(false)}
      width="max-w-md"
      title="反馈与联系"
      description="用下面的方式直接联系我们，你的意见我们都会看。"
    >
      <div className="overflow-hidden rounded-[10px] border border-line">
        {CONTACTS.map((item) => {
          const Icon = item.icon
          return (
            <div
              key={item.key}
              className="flex items-center gap-2.5 border-b border-line-soft px-3 py-2.5 last:border-b-0"
            >
              <Icon size={14} className="shrink-0 text-ink-faint" />
              <span className="w-8 shrink-0 text-[12px] text-ink-faint">{item.label}</span>
              <span className="min-w-0 flex-1 truncate font-mono text-[12.5px] text-ink">
                {item.value}
              </span>
              <button
                type="button"
                onClick={() => void copy(item.value)}
                className="no-drag flex shrink-0 items-center gap-1 rounded-[6px] px-1.5 py-0.5 text-[11.5px] text-ink-faint transition-colors hover:bg-hover hover:text-ink"
              >
                {copied === item.value ? <Check size={11} /> : <Copy size={11} />}
                {copied === item.value ? '已复制' : '复制'}
              </button>
            </div>
          )
        })}
      </div>

      {/*
        ⚠️ 这里原本承诺"反馈被采纳后赠送 1000–10000 Token 的兑换码，
        在权益页输入即可到账"。按产品要求**剔除** —— 兑换码功能
        整体下线了，留着这句会变成"说好的奖励没地方领"。

        只留下面这句"说明账号名"：那是**客服能对上人**的必要条件，
        与奖励无关，删了会让反馈变成一堆没有主语的留言。
      */}
      <div className="mt-3 rounded-[10px] border border-brand/25 bg-brand-soft px-3 py-2.5 text-[12px] leading-relaxed text-ink">
        <span className="text-ink-soft">
          反馈时请顺带说明你用的账号名，方便我们发放贡献度（Token）奖励。
        </span>
      </div>
    </Modal>
  )
}
