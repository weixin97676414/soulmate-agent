import clsx from 'clsx'
import { Check, ChevronUp, ShieldAlert, ShieldCheck, ShieldQuestion } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { useAppStore } from '@/stores/appStore'
import { useActiveAssistant, useAssistantStore } from '@/stores/assistantStore'
import { useNotificationStore } from '@/stores/notificationStore'
import type { ConfirmMode, ConfirmModeState } from '@/types'

/**
 * 权限确认模式的快捷开关（放在输入栏旁边）。
 *
 * ## 为什么要放在这个位置
 *
 * 「自动批准」意味着**所有需要确认的操作都不再询问**（写文件、删文件、覆盖 Excel…）。
 * 它原本埋在 设置中心 → 安全与通用 里，用户既看不见当前状态，也很容易忘了自己开过。
 * 放在输入栏旁边，用户每打一句话都能看见「现在处于什么模式」、「刚才那个操作为什么没问我」，
 * 并且随手就能改回来。
 *
 * ## 一个容易被忽略的点
 *
 * 助手预设可以给单个会话指定专属权限策略，**优先级高于全局**。
 * 如果只显示全局值，用户在助手会话里看到的会是一个不生效的开关，
 * 然后陷入「我明明设成交互确认了，为什么还是不问我」的困惑。
 * 所以这里显示的是 effective（实际生效值），并明确标出「来自助手」，
 * 同时提供一键让助手跟随全局。
 */

/**
 * 三个模式，按产品要求定**顺序与颜色**：
 *
 * - 顺序：每次确认 → **自动批准** → 拒绝高危（原先"拒绝高危"排在中间，与自动批准互换）；
 * - 配色：每次确认 **绿**（最稳）、自动批准 **红**（最危险，会绕过一切询问）、
 *   拒绝高危 **黄**（安全，但会让搭子"什么都干不了"，也是一种需要留意的状态）。
 *
 * ⚠️ 颜色不是装饰：这一行在输入栏上**一直可见**，用户每打一句话都会扫到它。
 * 红黄绿是"当前处在什么风险档位"最快的答案 —— 所以红必须留给真正危险的那一档。
 */
const OPTIONS: Array<{
  value: ConfirmMode
  label: string
  hint: string
  icon: typeof ShieldQuestion
  /**
   * 色调。**它表示的是"这一档会带来什么后果"，不是"这一档安不安全"**
   * （产品定下的：自动批准 = 黄，全部拒绝 = 红）：
   *
   * - `success` 每次确认 —— 正常态，既不放开也不拦死；
   * - `warning` 自动批准 —— 会**放开**所有需要确认的操作，相当于少了一层看护；
   * - `danger` 全部拒绝 —— 会**拦掉**所有需要确认的操作，搭子几乎寸步难行。
   *
   * ⚠️ 为什么"最安全"的那一档反而是红色：红色在这里的作用是**让用户注意到
   * 自己动过这个开关**。选中它之后搭子会频频罢工（"它怎么什么都不肯干"），
   * 而用户很可能已经忘了是自己设的 —— 那是这个按钮上最容易让人困惑的一档，
   * 不是最危险的一档。真正危险的是打开后一声不吭的「自动批准」。
   */
  tone: 'success' | 'warning' | 'danger'
}> = [
  {
    value: 'interactive',
    label: '每次确认',
    hint: '执行写文件、删除等操作前弹窗询问',
    icon: ShieldQuestion,
    tone: 'success',
  },
  {
    value: 'auto_approve',
    label: '自动批准',
    hint: '不询问，直接执行需要确认的操作',
    icon: ShieldAlert,
    tone: 'warning',
  },
  {
    value: 'deny',
    label: '全部拒绝',
    hint: '不询问，直接拒绝所有需要确认的操作',
    icon: ShieldCheck,
    tone: 'danger',
  },
]

/**
 * 通知标题里用的名字。
 *
 * ⚠️ 必须与 `OPTIONS` 的 `label` 一致 —— 两处文案不一致时，用户会在通知里
 * 看到一个他没在菜单里见过的名字（原先这里写「拒绝高危」，菜单里也是，
 * 所以看不出问题；现在菜单改成了「全部拒绝」，这里不跟着改就会错位）。
 */
const LABELS: Record<ConfirmMode, string> = {
  interactive: '每次确认',
  deny: '全部拒绝',
  auto_approve: '自动批准',
}

interface ConfirmModeButtonProps {
  /**
   * 受控值。**传了就走受控模式**（群聊用）—— 不读单聊那个"当前助手生效模式"，
   * 也**不按助手去问后端**（群聊没有"当前助手"这个概念）。
   */
  value?: ConfirmMode
  /** 受控改动。受控模式下由调用方负责保存与报错。 */
  onChange?: (next: ConfirmMode) => void
  /** 菜单顶部的说明。默认是单聊那句。 */
  note?: string
  disabled?: boolean
}

/**
 * 权限确认模式（每次确认 / 自动批准 / 拒绝高危）。
 *
 * ## 为什么群聊复用这一个组件
 *
 * 三档的**颜色**（红黄绿）不是装饰：它在输入栏上一直可见，用户每打一句话都会
 * 扫到，是"当前处在什么风险档位"最快的答案。这份配色如果有第二份，
 * 改了一处另一处就慢半拍 —— 用户看到的就是"群里和单聊的权限按钮颜色不一样"，
 * 而那种不一致会直接被读成"其中一个坏了"。
 */
export function ConfirmModeButton({
  value,
  onChange,
  note,
  disabled = false,
}: ConfirmModeButtonProps = {}) {
  const controlled = value !== undefined
  const api = useAppStore((state) => state.api)
  // 兜底值跟出厂默认一致：设置还没加载出来时，显示的就该是新装的默认值
  const globalMode = useAppStore((state) => state.settings?.security.confirm_mode ?? 'interactive')
  const reloadSettings = useAppStore((state) => state.reloadSettings)
  const push = useNotificationStore((state) => state.push)

  const activeAssistant = useActiveAssistant()
  const saveAssistant = useAssistantStore((state) => state.save)

  const [open, setOpen] = useState(false)
  const [state, setState] = useState<ConfirmModeState | null>(null)
  const [pending, setPending] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  // 助手一换，生效模式可能就变了，必须重新问后端
  const assistantId = activeAssistant?.id ?? null
  useEffect(() => {
    // 受控模式（群聊）不问后端：它的值由调用方直接给，问出来也没地方用
    if (controlled || !api) return
    let cancelled = false
    void (async () => {
      try {
        const payload = await api.getConfirmMode(assistantId)
        if (!cancelled) setState(payload)
      } catch {
        // 拿不到就用全局值兜底，不要因此把开关藏起来
        if (!cancelled) setState(null)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [api, assistantId, globalMode, controlled])

  // 点击外部 / Esc 关闭
  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const effective = controlled ? value : (state?.effective ?? globalMode)
  const override = state?.assistant_override ?? null
  // 助手压过了全局——这时改全局开关是没用的，必须让用户知道。
  // 受控模式（群聊）下不适用：那边没有"助手覆盖"这一说。
  const fromAssistant = !controlled && override !== null && override !== globalMode

  const apply = async (mode: ConfirmMode) => {
    if (controlled) {
      // 受控模式下保存是调用方的事（群聊写进群设置）：这里只上报，不弹通知 ——
      // 那条通知说的是"全局权限已切换"，对群设置来说是错的。
      onChange?.(mode)
      setOpen(false)
      return
    }
    if (!api) {
      push({ level: 'error', title: '后端未就绪', message: '请稍候重试。' })
      return
    }
    setPending(true)
    try {
      await api.setConfirmMode(mode)
      await reloadSettings()
      setState((prev) => (prev ? { ...prev, mode, effective: prev.assistant_override ?? mode } : prev))
      setOpen(false)
      push({
        level: mode === 'auto_approve' ? 'warning' : 'success',
        title: `权限模式已切换为「${LABELS[mode]}」`,
        message:
          mode === 'auto_approve'
            ? '所有需要确认的操作将不再询问，直接执行。'
            : undefined,
      })
    } catch (error) {
      // 不静默失败：用户点了开关却什么都没发生，比报错更让人困惑
      push({
        level: 'error',
        title: '切换权限模式失败',
        message: error instanceof Error ? error.message : String(error),
      })
    } finally {
      setPending(false)
    }
  }

  // 让当前助手放弃自己的权限策略，回落到全局设置
  const clearOverride = async () => {
    if (!activeAssistant) return
    setPending(true)
    try {
      await saveAssistant({ ...activeAssistant, confirm_mode: null })
      setState((prev) => (prev ? { ...prev, assistant_override: null, effective: prev.mode } : prev))
      push({ level: 'success', title: '该助手已改为跟随全局权限设置' })
    } catch (error) {
      push({
        level: 'error',
        title: '操作失败',
        message: error instanceof Error ? error.message : String(error),
      })
    } finally {
      setPending(false)
    }
  }

  const current = OPTIONS.find((item) => item.value === effective) ?? OPTIONS[0]
  const Icon = current.icon

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((wasOpen) => !wasOpen)}
        disabled={pending || disabled}
        title={
          fromAssistant
            ? `当前由助手「${activeAssistant?.name}」指定，点击查看`
            : '权限确认模式（有副作用的操作执行前如何处理）'
        }
        aria-label={`权限确认模式：${current.label}`}
        aria-expanded={open}
        className={clsx(
          'no-drag flex items-center gap-1 rounded-[6px] px-1.5 py-0.5 text-[11px] transition-colors',
          current.tone === 'danger'
            ? 'text-danger hover:bg-danger-soft'
            : current.tone === 'warning'
              ? 'text-warning hover:bg-warning-soft'
              : 'text-success hover:bg-success-soft',
        )}
      >
        <Icon size={11} className="shrink-0" />
        <span>{current.label}</span>
        {fromAssistant ? <span className="text-[10px]">· 助手</span> : null}
        <ChevronUp
          size={10}
          className={clsx('shrink-0 transition-transform', open && 'rotate-180')}
        />
      </button>

      {open ? (
        <div className="absolute right-0 bottom-full z-30 mb-1.5 w-[300px] overflow-hidden rounded-[10px] border border-line bg-panel shadow-lg">
          <div className="border-b border-line px-3 py-2">
            <div className="text-[12px] font-medium text-ink">权限确认</div>
            <div className="mt-0.5 text-[11px] leading-relaxed text-ink-faint">
              {note ?? '有副作用的操作（写文件、删除、发邮件等）执行前如何处理。'}
            </div>
          </div>

          {fromAssistant ? (
            <div className="border-b border-line bg-warning-soft px-3 py-2 text-[11px] text-warning">
              当前模式由助手「{activeAssistant?.name}」指定，会覆盖下面的全局设置。
              <button
                type="button"
                onClick={() => void clearOverride()}
                disabled={pending}
                className="ml-1 underline underline-offset-2 hover:no-underline disabled:opacity-50"
              >
                改为跟随全局
              </button>
            </div>
          ) : null}

          <div className="p-1">
            {OPTIONS.map((option) => {
              const OptionIcon = option.icon
              const selected = option.value === effective
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => void apply(option.value)}
                  disabled={pending}
                  className={clsx(
                    'flex w-full items-start gap-2 rounded-[8px] px-2 py-1.5 text-left transition-colors',
                    selected ? 'bg-brand-soft/50' : 'hover:bg-hover',
                    pending && 'opacity-60',
                  )}
                >
                  <OptionIcon
                    size={13}
                    className={clsx(
                      'mt-0.5 shrink-0',
                      option.tone === 'danger'
                        ? 'text-danger'
                        : option.tone === 'warning'
                          ? 'text-warning'
                          : 'text-success',
                    )}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1 text-[12px] text-ink">
                      {option.label}
                      {selected ? <Check size={11} className="text-brand" /> : null}
                    </span>
                    <span className="mt-0.5 block text-[10.5px] leading-relaxed text-ink-faint">
                      {option.hint}
                    </span>
                  </span>
                </button>
              )
            })}
          </div>

          {/*
            ⚠️ 这段警告是**黄**色，不是红的（"选择自动批准时，
            下方的红字说明也改为黄字"）。

            它必须与上面那一档的色调**一致**：把配色定成了
            "自动批准 = 黄、全部拒绝 = 红"（见 `OPTIONS` 的 `tone` 注释），
            而这条警告如果还是红的，菜单里就会出现"选中的那档是黄的、讲它的话
            是红的"——看起来像在描述另一档。
          */}
          {effective === 'auto_approve' ? (
            <div className="border-t border-line bg-warning-soft px-3 py-1.5 text-[10.5px] text-warning">
              自动批准：需要确认的操作不再询问、直接执行。高危（admin）级仍会被拒绝。
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
