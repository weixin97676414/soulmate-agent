/**
 * 语音命令注册表：把"用户说了一句话"接到"界面上某个**真在屏幕上**的按钮"。
 *
 * ## 为什么是"注册"而不是一张全局映射表
 *
 * 命令要触发的是**界面动作**，而界面动作只在**那个组件挂载着**的时候才有意义：
 * 「开始执行」这张计划卡片没显示，说它就不该有任何反应；对话已经停了，
 * 说「停下来」也不该报错。
 *
 * 所以组件在自己挂载时**登记**能干什么（`useVoiceCommand`），卸载时自动注销。
 * 派发时只找当前真正在屏幕上的动作 —— 这一条顺手解决了两件难事：
 *   1. 相似命令不会误伤看不见的界面（没挂载就根本收不到）；
 *   2. 危险操作只在它真的可见时才可能被一句话触发。
 *
 * ## 匹配：先本地字面，不中再问核心拼音
 *
 * 识别会把「确认」写成同音字（「全认」），严格说要按拼音比 —— 而拼音能力在核心
 * （Python 的 pypinyin）。所以本地先做一次**字面**整句相等（零成本，绝大多数
 * 时候直接就中），不中再请核心按拼音判一次。常见路径没有额外往返。
 *
 * ## 为什么要求"整句相等"
 *
 * 命令词很短（"确认"、"不用了"）。用"包含"的话，「帮我确认一下这个文件」会被
 * 判成批准一个高危操作 —— 那是会出事的。宁可让用户重说一遍。
 */

import { useEffect, useRef } from 'react'
import { create } from 'zustand'

import { getApi } from '@/stores/appStore'
import { VOICE_COMMANDS, commandWord } from '@/services/voiceCommands'

type Handler = () => void | Promise<void>

/** 去掉标点与空白，只留能比对的字。 */
function normalize(text: string): string {
  return (text ?? '').replace(/[\s，。！？、；：""''《》…—·.,!?;:"'()[\]{}]/g, '')
}

interface VoiceCommandState {
  /** 当前在屏幕上的动作：id → 触发函数 */
  handlers: Map<string, Handler>
  /**
   * 登记一个动作，返回**注销函数**（放进 `useEffect` 的清理里）。
   * 同一个 id 重复登记时后者生效。
   */
  register: (id: string, handler: Handler) => () => void
  /** 尝试把一句话当作命令执行；返回是否命中了某个当前可用的命令 */
  dispatch: (
    text: string,
    overrides: Record<string, string>,
    disabled: string[],
  ) => Promise<boolean>
  /** 当前真的能用的命令 id（设置面板可以据此标出"现在可用"） */
  activeIds: () => string[]
}

export const useVoiceCommandStore = create<VoiceCommandState>((set, get) => ({
  handlers: new Map(),

  register: (id, handler) => {
    const next = new Map(get().handlers)
    next.set(id, handler)
    set({ handlers: next })

    return () => {
      const current = get().handlers
      // 只有当里面还是**我登记的那个函数**时才删：热点组件可能在一个 tick 里
      // 先注销旧的、再登记新的，顺序反了就会把刚登记的那份误删（那个命令随之
      // 静默失效，且非常难查）。
      if (current.get(id) === handler) {
        const cleaned = new Map(current)
        cleaned.delete(id)
        set({ handlers: cleaned })
      }
    }
  },

  dispatch: async (text, overrides, disabled) => {
    const { handlers } = get()
    if (handlers.size === 0) return false

    const pool = VOICE_COMMANDS.filter(
      (spec) => handlers.has(spec.id) && !disabled.includes(spec.id),
    ).map((spec) => ({ id: spec.id, word: commandWord(spec, overrides) }))
    if (pool.length === 0) return false

    const said = normalize(text)
    if (!said) return false

    let hit = pool.find((item) => normalize(item.word) === said)

    if (!hit) {
      // 字面没中：请核心按拼音再判一次（同音字是识别的常态）
      try {
        const api = getApi()
        const result = await api.matchVoiceCommand(said, pool)
        if (result.id) hit = pool.find((item) => item.id === result.id)
      } catch {
        // 核心不在（或这个接口还没就绪）就当作没命中 —— 语音主链路不该因此卡住
        return false
      }
    }
    if (!hit) return false

    const handler = handlers.get(hit.id)
    if (!handler) return false
    await handler()
    return true
  },

  activeIds: () => Array.from(get().handlers.keys()),
}))

/**
 * 把一个界面动作登记为"可以被语音触发"。
 *
 * ⚠️ 传 `null` 表示**这一刻不提供**这个动作（比如"接着说"只在真有没跑完的回答时
 * 才该被说中）。这比传一个"点了没反应"的空函数诚实得多：命令表里就不会出现它，
 * 用户说了也不会以为界面坏了。
 */
export function useVoiceCommand(id: string, handler: Handler | null): void {
  // handler 通常是内联箭头函数，每次渲染都是新引用 —— 用 ref 拿最新的那份，
  // 否则每渲染一次就要"注销再登记"，而两次之间那个瞬间恰好收不到命令。
  const latest = useRef(handler)
  latest.current = handler

  // 依赖里放 `handler === null`（布尔）而不是 handler 本身：
  // 只在"从有到无 / 从无到有"时才真的重新登记。
  const absent = handler === null

  useEffect(() => {
    if (absent) return
    return useVoiceCommandStore.getState().register(id, () => latest.current?.())
  }, [id, absent])
}
