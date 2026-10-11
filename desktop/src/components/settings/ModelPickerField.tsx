import clsx from 'clsx'
import { Loader2, RefreshCw } from 'lucide-react'
import { useState } from 'react'

import { Button, Input } from '@/components/ui'
import { useAppStore } from '@/stores/appStore'

/**
 * 「获取模型」拿回来的清单可能要先裁剪一道。
 *
 * ## 硅基流动只留 deepseek（产品要求）
 *
 * 这家的模型广场是**几十家厂商的合集**（Qwen / GLM / Kimi / MiniMax…），
 * 用户在"配置一家服务商"时看到的是一整片目录，真正要用的那几个被淹在几百行里。
 * 他在这家要的就是 deepseek，所以只列出来。
 *
 * ⚠️ **收窄列表 ≠ 禁止别的模型**：输入框始终可以手打任意模型名。过滤只影响
 * "点按钮之后看到什么"，不影响"能不能用"。所以这里刻意不报错、不警告。
 *
 * ⚠️ 一个 deepseek 都没过滤出来时（接口换了、账号权限特殊），**退回原列表**：
 * 给空列表等于告诉用户"获取失败了"，比给多了糟得多 —— 他会退回手填，
 * 而本来自动获取是能用的。
 */
export function filterDiscoveredModels(baseUrl: string, models: string[]): string[] {
  if (!/siliconflow/i.test(baseUrl)) return models
  // ⚠️ 要求**同时**含 `deepseek` 与 `flash`（都不区分大小写）。
  //
  // 只匹配 `deepseek` 是不够的：这家在同一族下还挂着 V3 / R1 / Pro / 各种量化版，
  // 而用户要的是那一档 flash。加上 `flash` 之后清单通常只剩一两条，选都不用选。
  const only = models.filter((name) => /deepseek/i.test(name) && /flash/i.test(name))
  return only.length > 0 ? only : models
}

/**
 * 「模型名」输入 + 「获取模型」按钮。
 *
 * **为什么抽出来共用**：首启动引导与「添加服务商」向导都要问同一个问题
 * （"你要用哪个模型？"）。两个入口各写一套的话，"能不能自动获取""获取失败后
 * 能不能手填"这类行为迟早不一致，而用户只会觉得"有时候行有时候不行"。
 *
 * **手动输入是必须保留的**：不少网关不提供 `/models` 接口，或需要额外权限。
 * 自动获取只是把默认路径变省事，不是唯一路径 —— 少了手填，用户会在这一步卡死。
 */
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
  /** 预设里自带的候选；获取失败时至少还有这些可选 */
  suggested?: string[]
  /** datalist 的 id，同页有多个实例时必须区分 */
  id?: string
}) {
  const api = useAppStore((state) => state.api)
  const [fetched, setFetched] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null)

  // **拉到真实清单后，预设候选退场**：预设只是"没 Key 时的出厂快照"，
  // 真实清单才是权威 —— 把已停售的预设名混在里面，用户选中就 404。
  // 拉取失败/为空时才回退到预设（这正是预设存在的意义）。
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
      // 过滤后再展示（见 filterDiscoveredModels）：硅基流动只留 deepseek。
      // 注意 `models[0]` 因此变成过滤后的第一个 —— 正是我们想替他默认选中的那个。
      const models = filterDiscoveredModels(baseUrl.trim(), result.models ?? [])
      setFetched(models)
      if (models.length === 0) {
        // 能连通但没返回列表：如实说，并指回手填这条路
        setNote({ tone: 'error', text: '该地址没有返回模型列表，请在下方手动填写模型名。' })
        return
      }
      setNote({ tone: 'ok', text: `获取到 ${models.length} 个模型，请在列表中选择。` })
      // 原先填的（预设默认值）不在返回列表里时，直接替用户选第一个 ——
      // 对零基础用户来说，多一步选择就是多一道坎
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
        // 光靠 datalist 不够：它要点过输入框才展开，等于把"有哪些可选"藏起来了。
        // 列表直接摊开，点一下就选中。
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
