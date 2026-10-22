import clsx from 'clsx'
import { Brain, ChevronUp } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

import { useAppStore } from '@/stores/appStore'
import { useChatStore } from '@/stores/chatStore'







const LEVELS: Array<{ value: string | null; label: string; detail: string }> = [
  { value: null, label: '关闭', detail: '不发送该参数，按模型自己的默认行为' },
  { value: 'low', label: '低', detail: '略作思考，回答更快' },
  { value: 'medium', label: '中', detail: '兼顾速度与推理深度' },
  { value: 'high', label: '高', detail: '推理更充分，但更慢、也更费 token' },
]

interface ReasoningEffortButtonProps {
  






  value?: string | null
  
  onChange?: (next: string | null) => void
  






  visible?: boolean
  
  note?: string
  










  nullLabel?: string
  nullDetail?: string
  disabled?: boolean
}





















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
    
    
    if (!currentModel?.supports_reasoning) return null
  } else if (!visible) {
    return null
  }

  
  
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
