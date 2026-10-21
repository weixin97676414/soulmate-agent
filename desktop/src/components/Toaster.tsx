import clsx from 'clsx'
import { AlertTriangle, Bell, CheckCircle2, Info, X, XCircle } from 'lucide-react'

import { IconButton } from '@/components/ui'
import { useNotificationStore, type ToastLevel } from '@/stores/notificationStore'

const LEVEL_META: Record<
  ToastLevel,
  { icon: typeof Info; className: string; iconClassName: string }
> = {
  info: { icon: Bell, className: 'border-line', iconClassName: 'text-brand' },
  success: {
    icon: CheckCircle2,
    className: 'border-success/30',
    iconClassName: 'text-success',
  },
  warning: {
    icon: AlertTriangle,
    className: 'border-warning/30',
    iconClassName: 'text-warning',
  },
  error: { icon: XCircle, className: 'border-danger/30', iconClassName: 'text-danger' },
}






export function Toaster() {
  const toasts = useNotificationStore((state) => state.toasts)
  const dismiss = useNotificationStore((state) => state.dismiss)

  
  
  
  
  
  
  
  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="false"
      className="pointer-events-none fixed right-4 bottom-4 z-40 flex w-[336px] flex-col gap-2"
    >
      {toasts.map((toast) => {
        const meta = LEVEL_META[toast.level] ?? LEVEL_META.info
        const Icon = meta.icon
        return (
          <div
            key={toast.id}
            className={clsx(
              'animate-enter pointer-events-auto flex items-start gap-2.5 rounded-[10px] border bg-canvas px-3.5 py-3',
              'shadow-[0_8px_28px_rgba(0,0,0,0.14)]',
              meta.className,
            )}
          >
            <Icon size={16} className={clsx('mt-0.5 shrink-0', meta.iconClassName)} />
            <div className="min-w-0 flex-1">
              <div className="text-[13px] font-medium text-ink">{toast.title}</div>
              {toast.message ? (
                <div className="selectable mt-0.5 text-[12.5px] leading-relaxed whitespace-pre-wrap text-ink-soft">
                  {toast.message}
                </div>
              ) : null}
              {toast.action ? (
                <button
                  type="button"
                  onClick={() => {
                    
                    
                    dismiss(toast.id)
                    void toast.action?.run()
                  }}
                  className="no-drag mt-1.5 text-[12.5px] font-medium text-brand hover:underline"
                >
                  {toast.action.label}
                </button>
              ) : null}
            </div>
            <IconButton label="关闭" onClick={() => dismiss(toast.id)} className="-mt-0.5 -mr-1">
              <X size={14} />
            </IconButton>
          </div>
        )
      })}
    </div>
  )
}
