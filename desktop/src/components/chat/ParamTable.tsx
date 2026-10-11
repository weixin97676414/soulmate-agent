import clsx from 'clsx'
import { FileText, List } from 'lucide-react'

import { useAppStore } from '@/stores/appStore'

interface JsonSchemaProperty {
  type?: string
  description?: string
  items?: { type?: string }
  enum?: unknown[]
}

interface JsonSchema {
  properties?: Record<string, JsonSchemaProperty>
  required?: string[]
}

/**
 * 把 description 压成一句短标签。
 *
 * 技能作者写的是给模型看的完整说明（往往很长），直接铺在确认弹窗里
 * 会把界面撑爆，所以只取第一句并截断。
 */
function shortLabel(description: string | undefined, fallback: string): string {
  if (!description) return fallback.replace(/_/g, ' ')
  const firstClause = description.split(/[，。；;,.（(]/)[0]?.trim() ?? ''
  if (!firstClause) return fallback.replace(/_/g, ' ')
  return firstClause.length > 16 ? `${firstClause.slice(0, 16)}…` : firstClause
}

function looksLikePath(value: string): boolean {
  return /^[A-Za-z]:[\\/]/.test(value) || value.startsWith('/') || value.startsWith('\\\\')
}

function ValueView({ value }: { value: unknown }) {
  if (value === null || value === undefined) {
    return <span className="text-ink-faint">—</span>
  }
  if (typeof value === 'boolean') {
    return <span className="text-ink">{value ? '是' : '否'}</span>
  }
  if (typeof value === 'number') {
    return <span className="tabular-nums text-ink">{value}</span>
  }
  if (typeof value === 'string') {
    if (!value) return <span className="text-ink-faint">（空）</span>
    if (looksLikePath(value)) {
      return (
        <span className="selectable flex items-start gap-1.5 break-all text-ink">
          <FileText size={12} className="mt-[3px] shrink-0 text-ink-faint" />
          {value}
        </span>
      )
    }
    // 长文本（比如报告正文）折叠展示，避免弹窗被撑到屏幕外
    if (value.length > 200) {
      return (
        <pre className="selectable max-h-[160px] overflow-auto rounded-[6px] border border-line bg-panel p-2 text-[11.5px] leading-relaxed whitespace-pre-wrap text-ink-soft">
          {value}
        </pre>
      )
    }
    return <span className="selectable break-words whitespace-pre-wrap text-ink">{value}</span>
  }
  if (Array.isArray(value)) {
    const allPrimitive = value.every(
      (item) => item === null || ['string', 'number', 'boolean'].includes(typeof item),
    )
    if (allPrimitive && value.length > 0) {
      return (
        <ul className="selectable list-disc space-y-0.5 pl-4 text-ink">
          {value.slice(0, 20).map((item, index) => (
            <li key={index} className="break-words">
              {String(item)}
            </li>
          ))}
          {value.length > 20 ? (
            <li className="text-ink-faint">… 共 {value.length} 项</li>
          ) : null}
        </ul>
      )
    }
    return (
      <div className="flex items-center gap-1.5">
        <List size={12} className="shrink-0 text-ink-faint" />
        <span className="text-ink-soft">{value.length} 项</span>
      </div>
    )
  }
  // 对象：折叠成一段 JSON，需要时用户展开看
  return (
    <pre className="selectable max-h-[160px] overflow-auto rounded-[6px] border border-line bg-panel p-2 text-[11.5px] leading-relaxed whitespace-pre-wrap text-ink-soft">
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

/**
 * 确认弹窗里的参数展示。
 *
 * 直接用 ``JSON.stringify`` 铺给用户看有两个问题：键名是英文的
 * ``file_path``、``max_rows``，而值可能是一大坨。这里借助技能自己的
 * JSON Schema 把字段说明取出来当标签，并按值类型分别渲染。
 */
export function ParamTable({
  skillName,
  params,
}: {
  skillName: string
  params: Record<string, unknown>
}) {
  const skills = useAppStore((state) => state.skills)
  const schema = skills.find((skill) => skill.name === skillName)?.parameters as
    | JsonSchema
    | undefined
  const properties = schema?.properties ?? {}
  const required = new Set(schema?.required ?? [])

  const entries = Object.entries(params ?? {})
  if (entries.length === 0) {
    return (
      <div className="rounded-[8px] border border-line bg-panel px-3 py-2 text-[12.5px] text-ink-faint">
        该操作没有额外参数。
      </div>
    )
  }

  return (
    <div className="divide-y divide-line-soft overflow-hidden rounded-[8px] border border-line">
      {entries.map(([key, value]) => (
        <div key={key} className="flex gap-3 px-3 py-2.5">
          <div className="w-[112px] shrink-0">
            <div className="flex items-center gap-1">
              <span className="text-[12.5px] text-ink-soft">{shortLabel(properties[key]?.description, key)}</span>
              {required.has(key) ? <span className="text-[11px] text-danger">*</span> : null}
            </div>
            <code className="mt-0.5 block truncate text-[10.5px] text-ink-faint" title={key}>
              {key}
            </code>
          </div>
          <div className={clsx('min-w-0 flex-1 text-[12.5px] leading-relaxed')}>
            <ValueView value={value} />
          </div>
        </div>
      ))}
    </div>
  )
}
