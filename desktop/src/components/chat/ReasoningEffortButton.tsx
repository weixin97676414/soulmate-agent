import clsx from 'clsx'
import { Brain, ChevronUp } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

import { useAppStore } from '@/stores/appStore'
import { useChatStore } from '@/stores/chatStore'

/**
 * 档位表。
 *
 * `null` 排在最前面，因为它是**默认值**也是"关掉"：不发送思考强度参数，
 * 完全按模型自己的默认行为走 —— 这是绝大多数用户该待的位置。
 */
const LEVELS: Array<{ value: string | null; label: string; detail: string }> = [
  { value: null, label: '关闭', detail: '不发送该参数，按模型自己的默认行为' },
  { value: 'low', label: '低', detail: '略作思考，回答更快' },
  { value: 'medium', label: '中', detail: '兼顾速度与推理深度' },
  { value: 'high', label: '高', detail: '推理更充分，但更慢、也更费 token' },
]

interface ReasoningEffortButtonProps {
  /**
   * 受控值。**传了就走受控模式**（群聊用），读写它而不是单聊会话上的值。
   *
   * 注意判据是 `!== undefined` 而不是 `??`：`null` 是一个**合法取值**
   * （= "关闭，不发送该参数"），用 `??` 兜底会让"用户明确选了关闭"被当成
   * "没传"，从而显示成单聊的设置。
   */
  value?: string | null
  /** 受控改动 */
  onChange?: (next: string | null) => void
  /**
   * 受控模式下是否显示。
   *
   * 单聊那套门控（"当前模型不支持思考就不显示"）在群里**没有意义** ——
   * 群成员各有各的模型，没有一个"当前模型"可判。所以由调用方决定。
   * 不传则走单聊那套门控。
   */
  visible?: boolean
  /** 菜单底部的说明。默认是单聊那句"只对这个对话生效"。 */
  note?: string
  /**
   * `null` 那一档（列表第一项）的文案。不传就用单聊的「关闭」。
   *
   * ⚠️ **两边的 `null` 是两种不同的意思**（强调群/单聊的设置
   * 不能混）：
   * · 单聊 → "不发这个参数，按模型自己的默认走"，所以叫**关闭**；
   * · 群聊 → "这个群不管，用每个搭子档案里的档位"，所以叫**跟随每个搭子**。
   *
   * 复用同一个组件就必须让这两个字能改 —— 群里写「关闭」会被读成"群里关掉了
   * 思考强度"，而实际是"交给各成员自己定"，那是两回事。
   */
  nullLabel?: string
  nullDetail?: string
  disabled?: boolean
}

/**
 * 思考强度选择。
 *
 * ## 为什么当前模型不支持时整个控件都不显示
 *
 * 摆一个点了没用的旋钮比没有更糟：用户会以为"这个功能坏了"，而不是
 * "这个模型不支持"。所以走 `supports_reasoning` 门控 —— 开关在
 * 「设置 → 模型」里，默认就是打开的，只有用户明确关掉才不显示。
 *
 * ## 每个对话单独记
 *
 * 值存在会话上（见后端 `sessions.reasoning_effort`）：用户对"这轮值不值得多想
 * 一会儿"的判断是按对话来的，而且切走再回来应该还是上次的选择。
 *
 * ## 群聊怎么用它
 *
 * 传 `value` / `onChange` 走受控模式（值来自群设置 `group.reasoning_effort`）。
 * 复用同一个组件而不是给群聊再写一个，是因为**颜色、档位文案、弹出位置**这些
 * 一旦有第二份，改了一处另一处就会慢半拍 —— 而用户看到的就是"两个地方不一样"。
 */
export function ReasoningEffortButton({
  value,
  onChange,
  visible,
  note,
  nullLabel,
  nullDetail,
  disabled = false,
}: ReasoningEffortButtonProps = {}) {
  const models = useAppStore((state) => state.models)
  const modelId = useChatStore((state) => state.modelId)
  const effectiveDefault = useAppStore((state) => state.modelDefaults.effectiveDefault)
  const storeEffort = useChatStore((state) => state.reasoningEffort)
  const storeSetEffort = useChatStore((state) => state.setReasoningEffort)

  // 受控与否只由"调用方有没有传 value"决定：同一个组件在这两种模式下
  // 视觉必须完全一致，否则就不该叫"样式和单聊一样"。
  const controlled = value !== undefined
  const effort = controlled ? (value ?? null) : storeEffort
  const setEffort = controlled ? (onChange ?? (() => undefined)) : storeSetEffort
  const footerNote = note ?? '只对这个对话生效；切走再回来仍然是这个设置。'

  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const currentModel = models.find((model) => model.id === (modelId ?? effectiveDefault))
  if (visible === undefined) {
    // 单聊那套门控：拿不到模型信息时**不显示** —— 宁可不给，也不要给一个
    // 可能不生效的旋钮
    if (!currentModel?.supports_reasoning) return null
  } else if (!visible) {
    return null
  }

  // `null` 那一档的文案按调用方覆盖（群聊叫「跟随每个搭子」，单聊叫「关闭」——
  // 理由见 props 里 `nullLabel` 的说明）。其余档位两边完全一样，不参与覆盖。
  const levels = useMemo(
    () =>
      nullLabel === undefined && nullDetail === undefined
        ? LEVELS
        : LEVELS.map((item) =>
            item.value === null
              ? { ...item, label: nullLabel ?? item.label, detail: nullDetail ?? item.detail }
              : item,
          ),
    [nullLabel, nullDetail],
  )

  const active = levels.find((level) => level.value === effort) ?? levels[0]

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen(!open)}
        title="思考强度：让模型多想一会儿，还是尽快作答"
        className={clsx(
          'no-drag flex items-center gap-1 rounded-[6px] px-1.5 py-0.5 text-[11px] hover:bg-hover',
          effort ? 'text-brand' : 'text-ink-faint',
          disabled && 'cursor-not-allowed opacity-50 hover:bg-transparent',
        )}
      >
        <Brain size={11} />
        {effort ? `思考强度 ${active.label}` : '思考强度'}
        <ChevronUp size={10} className={clsx('transition-transform', open ? '' : 'rotate-180')} />
      </button>

      {open ? (
        <div className="absolute right-0 bottom-full z-30 mb-2 w-[280px] overflow-hidden rounded-[10px] border border-line bg-canvas shadow-[0_10px_30px_rgba(0,0,0,0.16)]">
          <div className="border-b border-line px-3 py-2 text-[12.5px] font-medium text-ink">
            思考强度
          </div>
          <div className="py-1">
            {levels.map((level) => (
              <button
                key={level.label}
                type="button"
                onClick={() => {
                  setEffort(level.value)
                  setOpen(false)
                }}
                className={clsx(
                  'no-drag flex w-full items-start gap-2 px-3 py-1.5 text-left',
                  level.value === active.value ? 'bg-brand-soft' : 'hover:bg-hover',
                )}
              >
                <span
                  className={clsx(
                    'mt-[3px] h-3 w-3 shrink-0 rounded-full border',
                    level.value === active.value ? 'border-brand bg-brand' : 'border-line',
                  )}
                />
                <span className="min-w-0 flex-1">
                  <span
                    className={clsx(
                      'block text-[12.5px]',
                      level.value === active.value ? 'text-brand' : 'text-ink',
                    )}
                  >
                    {level.label}
                  </span>
                  <span className="mt-0.5 block text-[11px] leading-relaxed text-ink-faint">
                    {level.detail}
                  </span>
                </span>
              </button>
            ))}
          </div>
          <div className="border-t border-line px-3 py-2 text-[11px] leading-relaxed text-ink-faint">
            {footerNote}
          </div>
        </div>
      ) : null}
    </div>
  )
}
