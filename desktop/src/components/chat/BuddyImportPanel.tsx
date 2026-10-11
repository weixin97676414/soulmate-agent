import clsx from 'clsx'
import { AlertTriangle, Check, FileArchive, Loader2, Upload, X } from 'lucide-react'
import { useRef, useState } from 'react'

import { Button, Modal } from '@/components/ui'
import { useAppStore } from '@/stores/appStore'
import { useAssistantStore } from '@/stores/assistantStore'
import { useGroupStore } from '@/stores/groupStore'
import { useNotificationStore } from '@/stores/notificationStore'
import type { ImportOutcome } from '@/types'

type Kind = 'buddy' | 'group'

const COPY: Record<Kind, { title: string; description: string; accept: string; hint: string }> = {
  buddy: {
    title: '导入搭子',
    description: '一个压缩包：搭子配置（json）与该搭子的技能包。也接受单独的 .json。',
    accept: '.zip,.json',
    hint: '接受 .zip（内含搭子 json 与 skills/）或单独的 .json',
  },
  group: {
    title: '导入搭子群',
    description: '一个压缩包：group.json + 多个搭子包（每个搭子包含自己的 json 与技能包）。',
    accept: '.zip',
    hint: '接受 .zip（内含 group.json 与 buddies/）',
  },
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/**
 * 搭子 / 搭子群的导入面板（两种导入共用）。
 *
 * 三件事写死在这里：
 * 1. **拖进来就能用** —— 用户拿到的是别人发来的压缩包，拖进来比"点选择文件、
 *    再翻目录"少两步；
 * 2. **逐条回报** —— 一个包里可能装了好几个技能，只说"导入失败"等于没说，
 *    所以成功/失败/已存在都逐行列出（后端也是这么返回的）；
 * 3. **导入中不许关窗** —— 中途关掉会留下一半的搭子与一半的技能。
 */
export function BuddyImportPanel({
  open,
  kind,
  onClose,
}: {
  open: boolean
  kind: Kind
  onClose: () => void
}) {
  const api = useAppStore((state) => state.api)
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)
  const [outcome, setOutcome] = useState<ImportOutcome | null>(null)
  const [error, setError] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const copy = COPY[kind]
  const close = () => {
    if (busy) return
    setFile(null)
    setOutcome(null)
    setError('')
    onClose()
  }

  const run = async () => {
    if (!api || !file) return
    setBusy(true)
    setError('')
    setOutcome(null)
    try {
      const result =
        kind === 'buddy' ? await api.importBuddyPackage(file) : await api.importBuddyGroup(file)
      setOutcome(result)
      // 清单要立刻跟上：后端也推了 assistants_changed/groups_changed，
      // 但这里显式再拉一次，"导入完就能在左边看到它"这件事不该取决于事件时序
      await useAssistantStore.getState().load()
      if (kind === 'group') await useGroupStore.getState().loadGroups()
      useNotificationStore.getState().push({
        level: result.ok ? 'info' : 'warning',
        title: result.ok ? `已导入「${result.assistant?.name ?? result.group?.name ?? ''}」` : '导入没有完成',
        message: result.skills_missing?.length
          ? `有 ${result.skills_missing.length} 个技能在本机找不到：${result.skills_missing.join('、')}`
          : '详情见导入面板里的逐条结果。',
      })
    } catch (exc) {
      // 后端给的是 4xx + 人话（"这个包里没找到搭子文件"这类），原样显示
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
    }
  }

  const missing = outcome?.skills_missing ?? []

  return (
    <Modal
      open={open}
      onClose={close}
      width="max-w-lg"
      closeOnBackdrop={!busy}
      title={copy.title}
      description={copy.description}
    >
      <input
        ref={inputRef}
        type="file"
        accept={copy.accept}
        className="hidden"
        onChange={(event) => {
          const picked = event.target.files?.[0] ?? null
          event.target.value = ''
          if (picked) {
            setFile(picked)
            setOutcome(null)
            setError('')
          }
        }}
      />

      {file ? (
        <div className="flex items-center gap-2.5 rounded-[10px] border border-line bg-panel px-3 py-2.5">
          <FileArchive size={15} className="shrink-0 text-ink-faint" />
          <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink" title={file.name}>
            {file.name}
          </span>
          <span className="shrink-0 text-[11px] text-ink-faint">{formatSize(file.size)}</span>
          <button
            type="button"
            aria-label="移除这个文件"
            disabled={busy}
            onClick={() => {
              setFile(null)
              setOutcome(null)
              setError('')
            }}
            className="no-drag shrink-0 rounded-[6px] p-1 text-ink-faint transition-colors hover:bg-hover hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
          >
            <X size={13} />
          </button>
        </div>
      ) : (
        <button
          type="button"
          disabled={busy}
          onClick={() => inputRef.current?.click()}
          onDragOver={(event) => {
            // 不 preventDefault 的话浏览器会直接打开拖进来的那个文件
            event.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault()
            setDragging(false)
            const dropped = event.dataTransfer.files?.[0]
            if (dropped) {
              setFile(dropped)
              setOutcome(null)
              setError('')
            }
          }}
          className={clsx(
            'flex h-[160px] w-full flex-col items-center justify-center gap-2 rounded-[12px] border border-dashed transition-colors',
            dragging
              ? 'border-brand bg-brand-soft/40'
              : 'border-line hover:border-brand/40 hover:bg-hover',
          )}
        >
          <Upload size={20} className={dragging ? 'text-brand' : 'text-ink-faint'} />
          <span className="text-[12.5px] text-ink">把压缩包拖到这里，或点击选择文件</span>
          <span className="text-[11px] text-ink-faint">{copy.hint}</span>
        </button>
      )}

      {busy ? (
        <div className="mt-3 h-[3px] w-full overflow-hidden rounded-full bg-line">
          <div className="boot-progress h-full w-1/3 rounded-full bg-brand" />
        </div>
      ) : null}

      {error ? (
        <div className="mt-3 flex items-start gap-2 rounded-[8px] border border-danger/30 bg-danger-soft px-3 py-2">
          <AlertTriangle size={13} className="mt-[2px] shrink-0 text-danger" />
          <span className="selectable text-[12px] leading-relaxed text-ink-soft">{error}</span>
        </div>
      ) : null}

      {missing.length ? (
        <div className="mt-3 flex items-start gap-2 rounded-[8px] border border-warning/30 bg-warning-soft px-3 py-2">
          <AlertTriangle size={13} className="mt-[2px] shrink-0 text-warning" />
          <span className="text-[12px] leading-relaxed text-ink-soft">
            这些技能在本机找不到，已跳过：{missing.join('、')}。
            <br />
            它们可能在包里没带、或名字与你的技能不一致。
          </span>
        </div>
      ) : null}

      {outcome ? (
        <div className="mt-3 max-h-[240px] overflow-y-auto rounded-[10px] border border-line">
          {outcome.results.map((row, index) => (
            <div
              key={`${row.name}-${index}`}
              className="animate-enter flex items-start gap-2 border-b border-line-soft px-3 py-2 last:border-b-0"
            >
              {row.ok ? (
                <Check size={13} className="mt-[3px] shrink-0 text-success" />
              ) : (
                <X size={13} className="mt-[3px] shrink-0 text-danger" />
              )}
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="truncate text-[12.5px] text-ink">{row.name}</span>
                  {row.skipped ? (
                    <span className="rounded-[5px] border border-line bg-panel px-1.5 text-[10.5px] text-ink-faint">
                      已存在，未重复导入
                    </span>
                  ) : null}
                </div>
                {row.message && !row.skipped ? (
                  <p
                    className={clsx(
                      'mt-0.5 text-[11.5px] leading-relaxed',
                      row.ok ? 'text-ink-faint' : 'text-danger',
                    )}
                  >
                    {row.message}
                  </p>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      ) : null}

      <div className="mt-4 flex items-center gap-2">
        <Button
          variant="primary"
          disabled={!file || busy}
          onClick={() => void run()}
          icon={busy ? <Loader2 size={13} className="animate-spin" /> : undefined}
        >
          {busy ? '导入中…' : '开始导入'}
        </Button>
        <Button disabled={busy} onClick={close}>
          {outcome ? '完成' : '取消'}
        </Button>
      </div>
    </Modal>
  )
}
