import clsx from 'clsx'
import { CornerDownLeft } from 'lucide-react'


export interface PaletteItem {
  key: string
  
  title: string
  
  detail: string
  
  tone?: 'danger'
}

export interface SlashCommand {
  name: string
  label: string
  hint?: string
}







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
  
  return SLASH_COMMANDS.filter((command) =>
    `${command.name} ${command.label}`.toLowerCase().includes(lower),
  )
}








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
