import { useEffect, useState } from 'react'

import { Modal } from '@/components/ui'
import { useClosableDialog } from '@/stores/transientDialogs'
import { useChatStore } from '@/stores/chatStore'
import type { InteractionAnswer, InteractionEvent } from '@/types'
import { Check, Eye, EyeOff, HelpCircle, KeyRound, Loader2 } from 'lucide-react'






















export function InteractionDialog() {
  const interaction = useChatStore((state) => state.interaction)
  const respond = useChatStore((state) => state.respondInteraction)

  
  
  
  
  useClosableDialog(
    'InteractionDialog',
    interaction?.kind === 'choice',
    () => void respond({ cancelled: true }),
  )

  if (!interaction) return null
  return interaction.kind === 'secret' ? (
    <SecretForm key={interaction.requestId} data={interaction} respond={respond} />
  ) : (
    <ChoiceList key={interaction.requestId} data={interaction} respond={respond} />
  )
}

interface Props {
  data: InteractionEvent
  respond: (answer: InteractionAnswer) => Promise<void>
}


function SourceLine({ data }: { data: InteractionEvent }): React.JSX.Element | null {
  if (!data.sessionTitle && !data.assistantName) return null
  const who = data.assistantName || ''
  const where = data.groupName ? `群聊「${data.groupName}」` : data.sessionTitle
  const text = [who, where].filter(Boolean).join(' · ')
  if (!text) return null
  return <p className="mt-1 text-[11.5px] text-ink-faint">来自 {text}</p>
}




function ChoiceList({ data, respond }: Props): React.JSX.Element {
  const [custom, setCustom] = useState('')
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)

  const submit = async (answer: InteractionAnswer): Promise<void> => {
    setBusy(true)
    await respond(answer)
  }

  return (
    <Modal
      open
      onClose={() => void submit({ cancelled: true })}
      title="想跟你确认一下"
      width="max-w-xl"
    >
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] bg-brand/10 text-brand">
          <HelpCircle size={17} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[13.5px] leading-relaxed font-medium text-ink">{data.question}</p>
          <SourceLine data={data} />
        </div>
      </div>

      <div className="mt-3 space-y-1.5">
        {data.options.map((option) => (
          <button
            key={option.label}
            type="button"
            disabled={busy}
            onClick={() => void submit({ value: option.label })}
            className="flex w-full items-start gap-2 rounded-[8px] border border-line-soft px-3 py-2 text-left transition-colors hover:border-brand hover:bg-brand/5 disabled:opacity-50"
          >
            <span className="min-w-0 flex-1">
              <span className="block text-[13px] font-medium text-ink">{option.label}</span>
              {option.description ? (
                <span className="mt-0.5 block text-[11.5px] leading-relaxed text-ink-faint">
                  {option.description}
                </span>
              ) : null}
            </span>
          </button>
        ))}
      </div>

      {}
      {data.allowCustom ? (
        open ? (
          <div className="mt-2 flex items-start gap-2">
            <input
              autoFocus
              value={custom}
              onChange={(event) => setCustom(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && custom.trim()) {
                  void submit({ custom: custom.trim() })
                }
              }}
              placeholder="说说你真正想要的是什么"
              className="min-w-0 flex-1 rounded-[8px] border border-line-soft bg-canvas px-3 py-2 text-[13px] text-ink outline-none focus:border-brand"
            />
            <button
              type="button"
              disabled={busy || !custom.trim()}
              onClick={() => void submit({ custom: custom.trim() })}
              className="shrink-0 rounded-[8px] bg-brand px-3.5 py-2 text-[12.5px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              就用这个
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="mt-2 w-full rounded-[8px] border border-dashed border-line-soft px-3 py-2 text-left text-[12.5px] text-ink-soft transition-colors hover:border-brand hover:text-ink"
          >
            以上都不是，我自己说…
          </button>
        )
      ) : null}

      <div className="mt-4 flex items-center justify-end gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => void submit({ cancelled: true })}
          className="rounded-[8px] px-3 py-2 text-[12.5px] text-ink-soft transition-colors hover:bg-hover hover:text-ink disabled:opacity-50"
        >
          都不对，重新理解
        </button>
      </div>
    </Modal>
  )
}




function SecretForm({ data, respond }: Props): React.JSX.Element {
  const [values, setValues] = useState<Record<string, string>>({})
  const [shown, setShown] = useState<Record<string, boolean>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  
  useEffect(() => {
    const timers = Object.keys(shown)
      .filter((name) => shown[name])
      .map((name) =>
        window.setTimeout(() => setShown((prev) => ({ ...prev, [name]: false })), 5000),
      )
    return () => timers.forEach((timer) => window.clearTimeout(timer))
  }, [shown])

  const filled = data.fields.filter((field) => (values[field.name] ?? '').trim())

  const submit = async (): Promise<void> => {
    if (!filled.length) {
      setError('至少填一项再提交')
      return
    }
    setBusy(true)
    setError('')
    const keys: Record<string, string> = {}
    for (const field of filled) keys[field.name] = values[field.name].trim()
    try {
      
      
      
      const bridge = window.agentBridge
      if (!bridge?.saveSkillSecrets) {
        setError('当前版本不支持安全保存，请更新客户端')
        setBusy(false)
        return
      }
      await bridge.saveSkillSecrets({ keys })
      
      await respond({ names: filled.map((field) => field.name) })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '保存失败，请重试')
      setBusy(false)
    }
  }

  return (
    <Modal open onClose={() => void respond({ cancelled: true })} title="需要你提供一项信息" width="max-w-lg">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] bg-warning/10 text-warning">
          <KeyRound size={16} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[13px] leading-relaxed text-ink-soft">{data.reason}</p>
          <SourceLine data={data} />
        </div>
      </div>

      <div className="mt-3 space-y-3">
        {data.fields.map((field) => (
          <div key={field.name}>
            <label className="mb-1 block text-[12.5px] font-medium text-ink">{field.label}</label>
            <div className="relative">
              {field.multiline ? (
                <textarea
                  rows={4}
                  value={values[field.name] ?? ''}
                  onChange={(event) =>
                    setValues((prev) => ({ ...prev, [field.name]: event.target.value }))
                  }
                  className="w-full rounded-[8px] border border-line-soft bg-canvas px-3 py-2 font-mono text-[12px] text-ink outline-none focus:border-brand"
                />
              ) : (
                <input
                  type={shown[field.name] ? 'text' : 'password'}
                  autoComplete="off"
                  spellCheck={false}
                  value={values[field.name] ?? ''}
                  onChange={(event) =>
                    setValues((prev) => ({ ...prev, [field.name]: event.target.value }))
                  }
                  className="w-full rounded-[8px] border border-line-soft bg-canvas px-3 py-2 pr-9 font-mono text-[12px] text-ink outline-none focus:border-brand"
                />
              )}
              {field.multiline ? null : (
                <button
                  type="button"
                  aria-label={shown[field.name] ? '隐藏内容' : '临时显示 5 秒'}
                  title={shown[field.name] ? '隐藏内容' : '临时显示 5 秒'}
                  onClick={() =>
                    setShown((prev) => ({ ...prev, [field.name]: !prev[field.name] }))
                  }
                  className="absolute top-1/2 right-2 -translate-y-1/2 rounded-[6px] p-1 text-ink-faint transition-colors hover:bg-hover hover:text-ink"
                >
                  {shown[field.name] ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              )}
            </div>
            {field.hint ? (
              <p className="mt-1 text-[11.5px] leading-relaxed text-ink-faint">{field.hint}</p>
            ) : null}
          </div>
        ))}
      </div>

      {}
      <p className="mt-3 rounded-[8px] bg-success/8 px-3 py-2 text-[11.5px] leading-relaxed text-ink-soft">
        内容<strong className="font-semibold text-ink">只保存在这台电脑上</strong>
        （本地加密），不会发送给模型，AI 也看不到它。之后它会被用来代替你向对方服务发起请求。
      </p>

      {error ? <p className="mt-2 text-[11.5px] text-danger">{error}</p> : null}

      <div className="mt-4 flex items-center justify-end gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => void respond({ cancelled: true })}
          className="rounded-[8px] px-3 py-2 text-[12.5px] text-ink-soft transition-colors hover:bg-hover hover:text-ink disabled:opacity-50"
        >
          取消
        </button>
        <button
          type="button"
          disabled={busy || !filled.length}
          onClick={() => void submit()}
          className="flex items-center gap-1.5 rounded-[8px] bg-brand px-3.5 py-2 text-[12.5px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
        >
          {busy ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
          保存并使用
        </button>
      </div>
    </Modal>
  )
}
