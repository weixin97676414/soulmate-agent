import clsx from 'clsx'
import { X } from 'lucide-react'
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from 'react'
import { useEffect } from 'react'




type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
type ButtonSize = 'sm' | 'md'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  icon?: ReactNode
}





















const DARK_BUTTON_DIM = 'dark:brightness-[0.88] dark:hover:brightness-100'
















const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary: `bg-brand text-white hover:brightness-110 active:brightness-95 ${DARK_BUTTON_DIM} disabled:bg-brand/45 disabled:text-white/80`,
  secondary: `bg-canvas text-ink border border-line hover:bg-hover dark:border-brand/25 dark:bg-brand-soft dark:text-brand dark:hover:bg-brand/20 ${DARK_BUTTON_DIM} disabled:text-ink-faint disabled:hover:bg-canvas`,
  ghost: `text-ink-soft hover:bg-hover hover:text-ink ${DARK_BUTTON_DIM} disabled:text-ink-faint disabled:hover:bg-transparent`,
  danger: `bg-danger text-white hover:brightness-110 ${DARK_BUTTON_DIM} disabled:opacity-50`,
}

export function Button({
  variant = 'secondary',
  size = 'md',
  icon,
  className,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type="button"
      {...rest}
      className={clsx(
        'no-drag inline-flex items-center justify-center gap-1.5 rounded-[8px] font-medium transition-colors',
        
        
        'shrink-0 whitespace-nowrap',
        'disabled:cursor-not-allowed disabled:opacity-70',
        size === 'sm' ? 'h-7 px-2.5 text-[12.5px]' : 'h-9 px-3.5 text-[13.5px]',
        BUTTON_VARIANTS[variant],
        className,
      )}
    >
      {icon}
      {children}
    </button>
  )
}

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string
  active?: boolean
}

export function IconButton({ label, active, className, children, ...rest }: IconButtonProps) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      {...rest}
      className={clsx(
        'no-drag inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] transition-colors',
        active ? 'bg-brand-soft text-brand' : 'text-ink-soft hover:bg-hover hover:text-ink',
        'disabled:cursor-not-allowed disabled:text-ink-faint disabled:hover:bg-transparent',
        className,
      )}
    >
      {children}
    </button>
  )
}




interface FieldProps {
  label: string
  hint?: string
  children: ReactNode
  className?: string
}

export function Field({ label, hint, children, className }: FieldProps) {
  return (
    <label className={clsx('block', className)}>
      <span className="mb-1.5 block text-[12.5px] font-medium text-ink-soft">{label}</span>
      {children}
      {hint ? <span className="mt-1 block text-[11.5px] text-ink-faint">{hint}</span> : null}
    </label>
  )
}










const CONTROL_CLASS =
  'w-full rounded-[8px] border border-line bg-canvas px-2.5 py-1.5 text-[13px] text-ink ' +
  'placeholder:text-ink-faint transition-colors hover:border-ink-faint/60 ' +
  'focus:border-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 ' +
  'disabled:bg-panel disabled:text-ink-faint'

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...rest} className={clsx(CONTROL_CLASS, 'h-9', className)} />
}

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...rest} className={clsx(CONTROL_CLASS, 'resize-y', className)} />
}

export function Select({
  className,
  children,
  ...rest
}: InputHTMLAttributes<HTMLSelectElement> & { children: ReactNode }) {
  return (
    <select {...rest} className={clsx(CONTROL_CLASS, 'h-9 cursor-pointer', className)}>
      {children}
    </select>
  )
}

export function Switch({
  checked,
  onChange,
  disabled,
  label,
}: {
  checked: boolean
  onChange: (value: boolean) => void
  disabled?: boolean
  label?: string
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={clsx(
        'no-drag relative inline-flex h-[20px] w-[36px] shrink-0 items-center rounded-full transition-colors',
        checked ? 'bg-brand' : 'bg-ink-faint/40',
        disabled && 'cursor-not-allowed opacity-50',
      )}
    >
      <span
        className={clsx(
          'inline-block h-[16px] w-[16px] transform rounded-full bg-white shadow transition-transform',
          checked ? 'translate-x-[18px]' : 'translate-x-[2px]',
        )}
      />
    </button>
  )
}




type BadgeTone = 'neutral' | 'brand' | 'success' | 'warning' | 'danger'

const BADGE_TONES: Record<BadgeTone, string> = {
  neutral: 'bg-panel text-ink-soft border-line',
  brand: 'bg-brand-soft text-brand border-brand/25',
  success: 'bg-success-soft text-success border-success/25',
  warning: 'bg-warning-soft text-warning border-warning/25',
  danger: 'bg-danger-soft text-danger border-danger/25',
}

export function Badge({
  tone = 'neutral',
  children,
  className,
}: {
  tone?: BadgeTone
  children: ReactNode
  className?: string
}) {
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-[5px] border px-1.5 py-[1px] text-[11px] leading-[16px] font-medium',
        BADGE_TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={clsx(
        'inline-block animate-spin rounded-full border-2 border-current border-t-transparent',
        className ?? 'h-3.5 w-3.5',
      )}
    />
  )
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 text-center">
      {icon ? <div className="mb-1 text-ink-faint">{icon}</div> : null}
      <div className="text-[14px] font-medium text-ink">{title}</div>
      {description ? (
        <div className="max-w-[420px] text-[12.5px] leading-relaxed text-ink-soft">{description}</div>
      ) : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  )
}




export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  headerExtra,
  titleExtra,
  centerTitleExtra = false,
  width = 'max-w-2xl',
  closeOnBackdrop = true,
}: {
  open: boolean
  onClose: () => void
  title: string
  description?: string
  children: ReactNode
  footer?: ReactNode
  
  headerExtra?: ReactNode
  





  titleExtra?: ReactNode
  














  centerTitleExtra?: boolean
  width?: string
  closeOnBackdrop?: boolean
}) {
  useEffect(() => {
    if (!open) return
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
      {








}
      <div
        className="absolute inset-0 bg-black/55"
        onClick={() => closeOnBackdrop && onClose()}
      />
      <div
        role="dialog"
        aria-modal="true"
        className={clsx(
          'animate-enter relative flex max-h-[86vh] w-full flex-col overflow-hidden rounded-[12px]',
          












          'border border-line bg-elevated shadow-[0_18px_48px_rgba(0,0,0,0.18)]',
          width,
        )}
      >
        {centerTitleExtra ? (
          







          <header className="relative flex shrink-0 items-center gap-4 border-b border-line px-5 py-4">
            {}
            <h2 className="min-w-0 max-w-[36%] truncate text-[15px] font-semibold text-ink">
              {title}
            </h2>
            {titleExtra ? (
              <div className="absolute left-1/2 -translate-x-1/2">{titleExtra}</div>
            ) : null}
            <IconButton label="关闭" onClick={onClose} className="ml-auto">
              <X size={16} />
            </IconButton>
          </header>
        ) : (
          <header className="flex shrink-0 items-start justify-between gap-4 border-b border-line px-5 py-4">
            <div className="min-w-0 flex-1">
              {
}
              <div className="flex items-center gap-3">
                <h2 className="min-w-0 truncate text-[15px] font-semibold text-ink">{title}</h2>
                {titleExtra ?? null}
              </div>
              {description ? (
                <p className="mt-0.5 text-[12.5px] text-ink-soft">{description}</p>
              ) : null}
              {


}
              {headerExtra ?? null}
            </div>
            <IconButton label="关闭" onClick={onClose}>
              <X size={16} />
            </IconButton>
          </header>
        )}

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>

        {footer ? (
          <footer className="flex shrink-0 items-center justify-end gap-2 border-t border-line bg-panel px-5 py-3">
            {footer}
          </footer>
        ) : null}
      </div>
    </div>
  )
}
