/**
 * 「可以被一句话关掉」的弹窗登记处。
 *
 * ## 为什么需要它
 *
 * 语音有一条「关闭弹窗」。但**不是所有弹窗都该被它关**：
 *
 * - **该关的**：反馈、添加技能这类 —— 它们是"看一眼就完事的浮层"，
 *   关掉没有任何后果，用嘴关掉正是语音最合适的场景；
 * - **绝不该关的**：搭子发起的权限确认弹窗（`ConfirmDialog`）与任务计划卡片
 *   （`PlanCard`）—— 那两个是在问"允不允许执行"。随口一句"关闭弹窗"就把它们
 *   打发掉，等于用一个含糊的词驳回了一次高危操作；而要驳回，命令表里本来就有
 *   「拒绝执行」这条精确得多的命令。
 *
 * 所以不搞"遍历 DOM 关掉所有遮罩"那种做法（那样迟早会把确认框一起关掉），
 * 而是**让该关的弹窗自己来登记**。没登记的，语音就关不掉 —— 这个默认值是安全的。
 *
 * ## 与 store 的关系
 *
 * 登记表本身是个普通 `Map`（不需要响应式）；store 里只放一个 `openCount`，
 * 给语音命令表判断"现在到底有没有弹窗可关"用 —— 没有的时候那条命令就不出现
 * （按项目口径：**说了没反应**比"不出现"更糟）。
 */

import { useEffect, useRef } from 'react'
import { create } from 'zustand'

/** 登记表：id → 关闭函数。id 用组件名即可，同一个弹窗同时只会有一份。 */
const closers = new Map<string, () => void>()

interface TransientDialogsState {
  /** 当前登记在册（= 正开着）的弹窗数量 */
  openCount: number
  sync: () => void
}

export const useTransientDialogsStore = create<TransientDialogsState>((set) => ({
  openCount: 0,
  sync: () => set({ openCount: closers.size }),
}))

/**
 * 把一个弹窗登记进来（`open` 为 false 时自动摘掉）。
 *
 * 用法：在弹窗组件里 `useClosableDialog('FeedbackDialog', open, () => setOpen(false))`。
 *
 * ⚠️ `close` 用 ref 存：它多半是每次渲染都新建的箭头函数，直接进依赖数组会让
 * effect 每帧重跑，登记表跟着抖动，语音命令的可用性就会一闪一闪。
 */
export function useClosableDialog(id: string, open: boolean, close: () => void): void {
  const sync = useTransientDialogsStore((state) => state.sync)
  const closeRef = useRef(close)
  closeRef.current = close

  useEffect(() => {
    if (open) {
      closers.set(id, () => closeRef.current())
    } else {
      closers.delete(id)
    }
    sync()
    return () => {
      closers.delete(id)
      sync()
    }
  }, [id, open, sync])
}

/**
 * 关掉所有登记在册的弹窗，返回关了几个。
 *
 * 返回数量是为了让调用方（语音那条命令）能在**一个都没关掉**时如实说出来 ——
 * 而不是让用户以为"说了，但它没反应"。
 */
export function closeAllTransientDialogs(): number {
  const pending = [...closers.values()]
  for (const close of pending) {
    try {
      close()
    } catch {
      // 某个弹窗关闭时抛异常不该连累其他弹窗；它自己的错误自己管
    }
  }
  return pending.length
}
