import { useState } from 'react'

/**
 * 侧栏折叠状态。
 *
 * 记在 **localStorage** 而不是应用配置里：这纯属界面偏好，跟后端毫无关系，
 * 走后端反而会让"每次换设备/重装都带着别人的折叠习惯"。
 * localStorage 写满时静默放弃 —— 折叠状态丢了顶多下次打开是展开的，不值得报错。
 */
/**
 * 侧栏收起/展开时，**窗口**要跟着变化的宽度（px）。
 *
 * ⚠️ 产品要求：收起侧栏**不要让对话栏变宽**，而是整体收窄窗口。
 * 直觉上"把腾出的宽度分给内容"像是好事，实际很别扭：用户眼前的排版会整体重排
 * 一次（消息换行位置全变），而他的本意只是"先把这一栏挪开"。收窄窗口则符合
 * 直觉 —— 那一块是被移走了，不是被摊给了别人。
 *
 * 数值 = 展开宽 264 − 折叠宽 44。三个列表都是这个宽度，所以一份常量够用。
 */
const RAIL_WIDTH_DELTA = 264 - 44

/**
 * 落盘 + 让窗口跟着收/放。
 *
 * 失败一律静默：折叠状态丢了顶多下次打开是展开的；窗口大小不跟着变也不影响
 * 折叠本身生效 —— 这两件事都不值得报错。
 */
function apply(next: boolean, key: string): void {
  try {
    localStorage.setItem(key, next ? '1' : '0')
  } catch {
    // 存不下就算了：这只是个界面偏好
  }
  // 窗口宽度跟着一起收/放。失败（或本来就是最大化）时静默忽略 ——
  // 折叠本身照常生效，只是窗口大小不变，不该为此报错。
  try {
    window.agentBridge?.resizeWindowBy?.(next ? -RAIL_WIDTH_DELTA : RAIL_WIDTH_DELTA)
  } catch {
    /* 老版本主进程没有这个通道时忽略 */
  }
}

export function useCollapsed(
  key: string,
): [boolean, () => void, (next: boolean) => void] {
  const [collapsed, setCollapsedState] = useState(() => {
    try {
      return localStorage.getItem(key) === '1'
    } catch {
      return false
    }
  })

  const toggle = () => {
    setCollapsedState((prev) => {
      const next = !prev
      apply(next, key)
      return next
    })
  }

  /**
   * 设成**指定状态**（而不是取反）。
   *
   * ⚠️ 为什么需要它：语音里"收起"和"展开"是两条命令，却作用在同一个开关上。
   * 只用 toggle 的话，说「收起搭子栏」时如果它本来就是收起的，会把栏**弹出来** ——
   * 用户说了收起却看着它展开，只会认为识别错了。实测反馈
   * "只有收起没有展开"，根子就在这里。
   */
  const setCollapsed = (next: boolean) => {
    setCollapsedState((prev) => {
      if (prev === next) return prev
      apply(next, key)
      return next
    })
  }

  return [collapsed, toggle, setCollapsed]
}
