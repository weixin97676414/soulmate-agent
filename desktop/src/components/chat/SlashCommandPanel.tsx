import clsx from 'clsx'
import { CornerDownLeft } from 'lucide-react'

/** 面板里的一行 */
export interface PaletteItem {
  key: string
  /** 左侧主文案：命令名或模型名 */
  title: string
  /** 右侧说明 */
  detail: string
  /** 危险操作用红色强调 */
  tone?: 'danger'
}

export interface SlashCommand {
  name: string
  label: string
  hint?: string
}

/**
 * 可用命令。
 *
 * **只放真能生效的**。摆一个点了没反应的命令，比不放更糟 —— 用户会以为功能坏了，
 * 然后开始怀疑整个应用。所以这里刻意没有"导出""分享"这类还没实现的东西。
 */
export const SLASH_COMMANDS: SlashCommand[] = [
  { name: 'new', label: '开始新对话', hint: 'Ctrl+N' },
  { name: 'compact', label: '压缩上下文（把较早内容折叠成摘要）' },
  { name: 'clear', label: '清空当前对话内容' },
  { name: 'stop', label: '停止正在生成的回答' },
  { name: 'model', label: '切换主对话模型' },
  { name: 'help', label: '查看全部命令' },
]

export function matchCommands(query: string): SlashCommand[] {
  const lower = query.trim().toLowerCase()
  if (!lower) return SLASH_COMMANDS
  // 中文标签与英文命令名都能命中 —— 用户记不住 `/clear` 但可能记得"清空"
  return SLASH_COMMANDS.filter((command) =>
    `${command.name} ${command.label}`.toLowerCase().includes(lower),
  )
}

/**
 * 斜杠命令面板（提示框上方弹出的小面板）。
 *
 * 故意做成**纯展示组件**：键盘上下键、回车、Esc 全部由 Composer 的 textarea
 * 统一处理。让面板自己监听键盘会和输入框抢事件（尤其是回车 —— 输入框也认回车），
 * 那是这类面板最常见的 bug 来源。
 */
export function SlashCommandPanel({
  items,
  activeIndex,
  emptyText = '没有匹配的命令',
  onPick,
  onHover,
}: {
  items: PaletteItem[]
  activeIndex: number
  emptyText?: string
  onPick: (item: PaletteItem) => void
  onHover: (index: number) => void
}) {
  return (
    <div className="absolute bottom-full left-0 z-30 mb-2 w-[340px] overflow-hidden rounded-[10px] border border-line bg-canvas shadow-[0_10px_30px_rgba(0,0,0,0.16)]">
      {items.length === 0 ? (
        <div className="px-3 py-2.5 text-[12px] text-ink-faint">{emptyText}</div>
      ) : (
        <div className="max-h-[240px] overflow-y-auto py-1">
          {items.map((item, index) => (
            <button
              key={item.key}
              type="button"
              onMouseEnter={() => onHover(index)}
              // 用 mousedown 而不是 click：click 之前 textarea 会先失焦，
              // 某些情况下会把这次点击吞掉
              onMouseDown={(event) => {
                event.preventDefault()
                onPick(item)
              }}
              className={clsx(
                'no-drag flex w-full items-center gap-3 px-3 py-1.5 text-left',
                index === activeIndex
                  ? 'bg-brand-soft'
                  : item.tone === 'danger'
                    ? 'hover:bg-danger-soft'
                    : 'hover:bg-hover',
              )}
            >
              <span
                className={clsx(
                  'min-w-0 flex-1 truncate font-mono text-[12px]',
                  item.tone === 'danger' ? 'text-danger' : 'text-ink',
                )}
              >
                {item.title}
              </span>
              <span className="shrink-0 text-[11.5px] text-ink-faint">{item.detail}</span>
              {index === activeIndex ? (
                <CornerDownLeft size={11} className="shrink-0 text-ink-faint" />
              ) : null}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
