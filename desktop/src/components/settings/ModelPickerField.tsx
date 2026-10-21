import clsx from 'clsx'
import { Loader2, RefreshCw } from 'lucide-react'
import { useState } from 'react'

import { Button, Input } from '@/components/ui'


import { filterDiscoveredModels } from '@/components/settings/modelFilter'
import { useAppStore } from '@/stores/appStore'











export function ModelPickerField({
  baseUrl,
  apiKey,
  value,
  onChange,
  suggested = [],
  id = 'model-name',
}: {
  baseUrl: string
  apiKey: string
  value: string
  onChange: (name: string) => void
  
  suggested?: string[]
  
  id?: string
}) {
  const api = useAppStore((state) => state.api)
  const [fetched, setFetched] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null)

  
  
  
  const options =
    fetched.length > 0
      ? [...new Set(fetched)]
      : [...new Set(suggested)]

  const fetchModels = async () => {
    if (!api) return
    if (!baseUrl.trim()) {
      setNote({ tone: 'error', text: '请先填写接口地址。' })
      return
    }
    setBusy(true)
    setNote(null)
    try {
      const result = await api.discoverModels({
        base_url: baseUrl.trim(),
        api_key: apiKey.trim(),
      })
      
      
      const models = filterDiscoveredModels(baseUrl.trim(), result.models ?? [])
      setFetched(models)
      if (models.length === 0) {
        
        setNote({ tone: 'error', text: '该地址没有返回模型列表，请在下方手动填写模型名。' })
        return
      }
      setNote({ tone: 'ok', text: `获取到 ${models.length} 个模型，请在列表中选择。` })
      
      
      if (!value || !models.includes(value)) onChange(models[0])
    } catch (error) {
      setNote({
        tone: 'error',
        text: `${error instanceof Error ? error.message : String(error)}（可以手动填写模型名）`,
      })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div className="flex gap-2">
        <Input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="例如 deepseek-chat"
          list={options.length ? `${id}-options` : undefined}
          autoComplete="off"
          spellCheck={false}
        />
        <Button
          onClick={() => void fetchModels()}
          disabled={busy}
          icon={busy ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
        >
          {busy ? '获取中…' : '获取模型'}
        </Button>
      </div>

      {options.length ? (
        <datalist id={`${id}-options`}>
          {options.map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
      ) : null}

      {options.length ? (
        
        
        <div className="mt-1.5 flex max-h-[150px] flex-wrap gap-1 overflow-y-auto">
          {options.map((name) => (
            <button
              key={name}
              type="button"
              onClick={() => onChange(name)}
              className={clsx(
                'no-drag rounded-[6px] border px-2 py-0.5 text-[11.5px] whitespace-nowrap transition-colors',
                value === name
                  ? 'border-brand/40 bg-brand-soft text-brand'
                  : 'border-line text-ink-soft hover:border-brand/40 hover:text-ink',
              )}
            >
              {name}
            </button>
          ))}
        </div>
      ) : null}

      {note ? (
        <p
          className={clsx(
            'mt-1.5 text-[11.5px] leading-relaxed',
            note.tone === 'ok' ? 'text-success' : 'text-danger',
          )}
        >
          {note.text}
        </p>
      ) : null}
    </div>
  )
}
