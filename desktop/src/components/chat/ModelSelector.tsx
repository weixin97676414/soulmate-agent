
















import { useMemo } from 'react'

import { useAppStore } from '@/stores/appStore'
import { useChatStore } from '@/stores/chatStore'

export function ModelSelector() {
  const models = useAppStore((state) => state.models)
  const effectiveDefault = useAppStore((state) => state.modelDefaults.effectiveDefault)
  const modelId = useChatStore((state) => state.modelId)
  const setModelId = useChatStore((state) => state.setModelId)
  const streaming = useChatStore((state) => state.streaming)

  const enabled = models.filter((model) => model.enabled)
  const current = modelId ?? effectiveDefault

  const grouped = useMemo(() => {
    const map = new Map<string, typeof enabled>()
    for (const model of enabled) {
      const key = model.provider || '其他'
      const list = map.get(key) ?? []
      list.push(model)
      map.set(key, list)
    }
    return [...map.entries()]
  }, [enabled])

  if (enabled.length === 0) {
    return <span className="text-[12.5px] text-danger">未配置可用模型</span>
  }

  return (
    <select
      value={current}
      disabled={streaming}
      onChange={(event) => setModelId(event.target.value)}
      


















      
      
      aria-label="选择模型"
      className="h-7 w-[25cqw] min-w-0 max-w-full cursor-pointer rounded-[8px] border border-line bg-canvas px-2 text-[12.5px] text-ellipsis text-ink hover:border-ink-faint/60 focus:border-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 disabled:cursor-not-allowed disabled:opacity-60"
    >
      {grouped.map(([provider, list]) => (
        <optgroup key={provider} label={provider}>
          {list.map((model) => (
            <option key={model.id} value={model.id}>
              {model.model_name || model.display_name}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  )
}
