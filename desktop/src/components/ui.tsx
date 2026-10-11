import clsx from 'clsx'
import { X } from 'lucide-react'
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from 'react'
import { useEffect } from 'react'

// --------------------------------------------------------------------------- //
// 按钮
// --------------------------------------------------------------------------- //
type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
type ButtonSize = 'sm' | 'md'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  icon?: ReactNode
}

/**
 * 夜间（`.dark`）按钮整体压暗一档。
 *
 * 反馈："夜间 UI 当中按钮亮度偏高，都稍微暗一点。"
 *
 * ## 为什么用 `filter: brightness` 而不是逐套皮肤改色值
 *
 * 深色皮肤有 **7 套**（dark / forest / ocean / plum / pine / charcoal / deepnight），
 * 每套都有一组自己的 `--app-*` 令牌。逐个调它们等于把同一件事做七遍，而且以后
 * 加新皮肤时必然漏掉一套 —— 那正是"别的都暗了、就这一套刺眼"的由来。
 *
 * `brightness` 作用在**按钮整个元素**上，一次就把主色 / 危险 / 次要三种底色
 * 统一压暗，且 `dark:` 变体绑的是 `.dark` class（由 `applyTheme` 按
 * `isDarkTheme` 挂上）——**只影响深色，浅色皮肤一个像素都不动**。
 *
 * 代价是白字也跟着暗一点（#fff → #e0e0e0 上下），仍然清晰。
 *
 * ⚠️ 数值刻意克制（0.88 / hover 回到 1）：这是"稍微暗一点"的调节，不是重做配色。
 * 调狠了会让主按钮在深色下变成"像被禁用"，比偏亮更糟。
 */
const DARK_BUTTON_DIM = 'dark:brightness-[0.88] dark:hover:brightness-100'

/**
 * 夜间次要按钮改用**主色调底**。
 *
 * 产品要求："夜间所有黑色底色按钮的底色都做相同处理 —— 用夜间主色调
 * 作为底色"。原先它们是 `bg-canvas`（夜间几乎纯黑），在一整片深色面板里像"凹陷的洞"，
 * 而按钮本该是**可点的**东西 —— 一块黑底看起来更像禁用态。
 *
 * 改在一处而不是逐个组件加 `className`：`secondary` 是 `<Button>` 的**默认变体**，
 * 「保存并测试连通性」「添加服务商」「New Buddy」「选择图片」这些用户点名的按钮
 * 全都在内。逐个改必然漏掉下一个新按钮。
 *
 * ⚠️ 用 `bg-brand-soft`（主色的淡化版）而不是 `bg-brand`：`secondary` 大量用在
 * "取消 / 次要"这类按钮上，实心主色会把它们全部升格成主按钮 —— 一屏里出现五个
 * 同等醒目度的按钮，等于没有重点。
 */
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
        // **按钮文字一律单行**（产品明确要求"所有按钮和控件标签强制单行"）：
        // 宽度不够时按钮被压成两行字比溢出更难看；配合外层的横向滚动使用
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

// --------------------------------------------------------------------------- //
// 表单
// --------------------------------------------------------------------------- //
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

/**
 * 表单控件的公共外观（Input / Textarea / Select 共用）。
 *
 * ⚠️ `focus-visible:ring-*` 是第 90 批（M-35）加的，**只对键盘生效**：
 * 原来只有 `focus:border-brand`（边框由灰变品牌色）—— 对鼠标用户够用，
 * 但键盘 Tab 到第几个控件了不够明显，尤其是一排 select 挨在一起时。
 * 刻意**保留** `focus:outline-none` + `focus:border-brand`：那是对鼠标用户的既有外观，
 * 这一批只增加键盘线索，不动鼠标下看到的样子。
 */
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

// --------------------------------------------------------------------------- //
// 展示
// --------------------------------------------------------------------------- //
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

// --------------------------------------------------------------------------- //
// 弹窗
// --------------------------------------------------------------------------- //
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
  /** 标题区下方的附加内容（跟着标题固定，不随内容滚动） */
  headerExtra?: ReactNode
  /**
   * 与标题**同一行**的附加内容（排在标题右边）。
   *
   * 与 `headerExtra` 的区别就是这一行的位置：那个在标题下面另起一块，
   * 适合"整块的东西"；这个是"标题旁边的一个小动作"。
   */
  titleExtra?: ReactNode
  /**
   * 把 `titleExtra` 单独**居中**（相对整个标题栏），而 `title` 仍**靠左**。
   *
   * 要的就是这个：头像大图里标题与按钮同一行、**按钮居中**、
   * **标题不变（还是靠左）**。
   *
   * ⚠️ 用绝对定位把按钮抽出行外，而不是 `justify-center`：flex 里的居中
   * 居的是"**剩下的空间**"，左侧标题与右侧关闭按钮宽度不等，那个"中间"
   * 会被推偏 —— 看起来就是"差一点没居中"。
   *
   * ⚠️ 标题限宽（`max-w-[36%]`）是配合它的：按钮已经被抽出行外、不占流，
   * 不限制的话长标题会**直接压到它下面**。
   *
   * 默认 `false`：其它弹窗的标题与附加内容都在左边。
   */
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
      <div
        className="absolute inset-0 bg-black/35 backdrop-blur-[1px]"
        onClick={() => closeOnBackdrop && onClose()}
      />
      <div
        role="dialog"
        aria-modal="true"
        className={clsx(
          'animate-enter relative flex max-h-[86vh] w-full flex-col overflow-hidden rounded-[12px]',
          'border border-line bg-canvas shadow-[0_18px_48px_rgba(0,0,0,0.18)]',
          width,
        )}
      >
        {centerTitleExtra ? (
          /*
            `titleExtra` 单独居中、`title` 仍靠左、关闭按钮靠右。

            三条位置各自独立：
            · 标题 —— 正常流里的第一个元素，天然靠左；
            · 按钮 —— 绝对定位 + `left-1/2 -translate-x-1/2`，相对**整个标题栏**居中；
            · 关闭 —— `ml-auto` 顶到最右。
          */
          <header className="relative flex shrink-0 items-center gap-4 border-b border-line px-5 py-4">
            {/* 限宽是配合那个绝对定位的按钮：它不占流，不限制的话长标题会压到它下面 */}
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
              {/* `truncate` 给标题：它旁边可能挂着附加内容，而超长的名字
                  会把那个挤出可视区（群名是可以起很长的） */}
              <div className="flex items-center gap-3">
                <h2 className="min-w-0 truncate text-[15px] font-semibold text-ink">{title}</h2>
                {titleExtra ?? null}
              </div>
              {description ? (
                <p className="mt-0.5 text-[12.5px] text-ink-soft">{description}</p>
              ) : null}
              {/*
                标题区下方的一块附加内容。放在 header 内而不是 children 里：
                它属于"这个弹窗是什么"的一部分，应该跟着标题一起固定、不随内容滚动。
              */}
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
