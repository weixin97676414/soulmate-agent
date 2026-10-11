import { useEffect, useRef, useState } from 'react'

/**
 * 会话区的"跟随最新"行为。单聊与群聊共用这一份实现。
 *
 * ## 规则
 *
 * - **只有当前已经贴着底**时，新内容到达才把视图带到最新；
 * - 用户一往上翻（离底超过 `STICK_THRESHOLD`）就**立刻停止跟随** —— 他停在哪儿就是哪儿；
 * - 离底超过 `SHOW_JUMP_THRESHOLD` 时露出「回到最新」按钮，点它才跳回去并恢复跟随；
 * - 换会话 / 换群（`resetKey` 变化）时重新贴底：进去就该看见最新的一条。
 *
 * ## 为什么要有这套规则（群聊那次的教训）
 *
 * 群聊原本是"内容一变就无条件 `scrollTo(底部)`"。buddy 们讨论时每个字都在触发它，于是
 * 用户**根本翻不上去**：手一滑就被拽回底部，想回看前面某个搭子说了什么完全做不到。
 * 区别在于"内容在动"与"用户想看哪里"是两件事，前者无权替后者做决定。
 *
 * ## 为什么用"签名"而不是直接依赖数组
 *
 * 内容变化由调用方给的 `signature` 表达（字符串即可）：它变了就说明"有新东西"。
 * 直接依赖消息数组会在每帧流式更新时都触发一次遍历比较，而这里只需要知道"变了没有"。
 *
 * ## 阈值
 *
 * 80px 是"贴底"的容差：滚动条在触控板/滚轮下很难精确停在最底部，差几像素仍应算贴底。
 * 200px 才露出按钮：差十几像素就弹按钮会让它在正常阅读时反复闪烁。
 */
const STICK_THRESHOLD = 80
const SHOW_JUMP_THRESHOLD = 200

export function useStickToBottom(signature: unknown, resetKey?: unknown) {
  const ref = useRef<HTMLDivElement>(null)
  const stick = useRef(true)
  const [showJump, setShowJump] = useState(false)

  // 换会话/换群：重新贴底。必须在下面那个 effect 之前声明 —— 同一次提交里
  // React 按声明顺序执行 effect，先复位再滚，顺序反了就会白滚一次。
  useEffect(() => {
    if (resetKey === undefined) return
    stick.current = true
    setShowJump(false)
  }, [resetKey])

  useEffect(() => {
    if (!stick.current) return
    const element = ref.current
    if (element) element.scrollTop = element.scrollHeight
  }, [signature])

  const onScroll = () => {
    const element = ref.current
    if (!element) return
    const distance = element.scrollHeight - element.scrollTop - element.clientHeight
    stick.current = distance < STICK_THRESHOLD
    setShowJump(distance >= SHOW_JUMP_THRESHOLD)
  }

  const jumpToBottom = () => {
    const element = ref.current
    if (!element) return
    element.scrollTop = element.scrollHeight
    stick.current = true
    setShowJump(false)
  }

  return { ref, showJump, onScroll, jumpToBottom }
}
