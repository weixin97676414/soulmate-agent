import clsx from 'clsx'
import { Check, ChevronUp, ShieldAlert, ShieldCheck, ShieldQuestion } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { useAppStore } from '@/stores/appStore'
import { useActiveAssistant, useAssistantStore } from '@/stores/assistantStore'
import { useNotificationStore } from '@/stores/notificationStore'
import type { ConfirmMode, ConfirmModeState } from '@/types'






























const OPTIONS: Array<{
  value: ConfirmMode
  label: string
  hint: string
  icon: typeof ShieldQuestion
  












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








const LABELS: Record<ConfirmMode, string> = {
  interactive: '每次确认',
  deny: '全部拒绝',
  auto_approve: '自动批准',
}

interface ConfirmModeButtonProps {
  



  value?: ConfirmMode
  
  onChange?: (next: ConfirmMode) => void
  
  note?: string
  disabled?: boolean
}











export function ConfirmModeButton({
  value,
  onChange,
  note,
  disabled = false,
}: ConfirmModeButtonProps = {}) {
  const controlled = value !== undefined
  const api = useAppStore((state) => state.api)
  
  const globalMode = useAppStore((state) => state.settings?.security.confirm_mode ?? 'interactive')
  const reloadSettings = useAppStore((state) => state.reloadSettings)
  const push = useNotificationStore((state) => state.push)

  const activeAssistant = useActiveAssistant()
  const saveAssistant = useAssistantStore((state) => state.save)

  const [open, setOpen] = useState(false)
  const [state, setState] = useState<ConfirmModeState | null>(null)
  const [pending, setPending] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  
  const assistantId = activeAssistant?.id ?? null
  useEffect(() => {
    
    if (controlled || !api) return
    let cancelled = false
    void (async () => {
      try {
        const payload = await api.getConfirmMode(assistantId)
        if (!cancelled) setState(payload)
      } catch {
        
        if (!cancelled) setState(null)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [api, assistantId, globalMode, controlled])

  
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
  
  
  const fromAssistant = !controlled && override !== null && override !== globalMode

  const apply = async (mode: ConfirmMode) => {
    if (controlled) {
      
      
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
      
      push({
        level: 'error',
        title: '切换权限模式失败',
        message: error instanceof Error ? error.message : String(error),
      })
    } finally {
      setPending(false)
    }
  }

  
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

          {







}
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
