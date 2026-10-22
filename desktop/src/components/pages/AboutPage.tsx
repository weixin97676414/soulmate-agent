import { useEffect, useState } from 'react'

import type { UpdateState } from '../../../shared/bridge'
import { useAppStore } from '@/stores/appStore'


export function AboutPage() {
  const appInfo = useAppStore((state) => state.appInfo)
  const health = useAppStore((state) => state.health)
  const paths = useAppStore((state) => state.paths)

  const rows: Array<[string, string]> = [
    ['应用版本', appInfo?.version ?? '—'],
    ['Electron', appInfo?.electronVersion ?? '—'],
    ['Chromium', appInfo?.chromeVersion ?? '—'],
    ['核心版本', health?.version ?? '—'],
    ['运行模式', appInfo?.isDev ? '开发模式' : '生产模式'],
    ['数据存储', health?.persistent ? 'SQLite 持久化' : '内存模式（不保留）'],
    ['数据目录', appInfo?.dataDir ?? '—'],
    ['工作区', paths?.workspace ?? '—'],
    ['产物目录', paths?.artifacts ?? '—'],
    ['日志目录', paths?.logs ?? '—'],
  ]

  return (
    <div className="flex min-w-0 flex-1 flex-col overflow-y-auto px-10 py-6">
      <div className="max-w-[720px]">
        <h2 className="text-[15px] font-semibold text-ink">关于</h2>
        <p className="mt-1 text-[12.5px] leading-relaxed text-ink-soft">
          Soulmate Agent 开源自研智能体框架的 Windows 桌面客户端。
          <br />
          所有数据保存在本机，不上传云端；模型服务商密钥仅存于本地配置文件。
        </p>

        <dl className="mt-5 divide-y divide-line-soft rounded-[10px] border border-line">
          {rows.map(([label, value]) => (
            <div key={label} className="flex items-center gap-4 px-3.5 py-2.5">
              <dt className="w-[92px] shrink-0 text-[12.5px] text-ink-soft">{label}</dt>
              <dd
                className="selectable min-w-0 flex-1 truncate text-[12.5px] text-ink"
                title={value}
              >
                {value}
              </dd>
            </div>
          ))}
        </dl>

        <div className="mt-4 flex gap-2">
          <button
            type="button"
            onClick={() => paths && void window.agentBridge.openPath(paths.root)}
            className="no-drag text-[12.5px] text-brand hover:underline"
          >
            打开数据目录
          </button>
          <span className="text-ink-faint">·</span>
          <button
            type="button"
            onClick={() => paths && void window.agentBridge.openPath(paths.logs)}
            className="no-drag text-[12.5px] text-brand hover:underline"
          >
            打开日志目录
          </button>
        </div>

        <UpdateSection />
      </div>
    </div>
  )
}













function UpdateSection() {
  const [state, setState] = useState<UpdateState | null>(null)
  const [autoUpdate, setAutoUpdate] = useState(true)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const bridge = window.agentBridge
    if (!bridge?.getUpdateState) return
    void bridge.getUpdateState().then(setState)
    void bridge.getDesktopPrefs?.().then((prefs) => setAutoUpdate(prefs.autoUpdate !== false))
    
    return bridge.onUpdateState?.((next) => setState(next))
  }, [])

  if (!state) return null

  const downloading = state.phase === 'downloading'
  const percent =
    state.bytesTotal > 0 ? Math.min(100, Math.round((state.bytesDone / state.bytesTotal) * 100)) : 0

  const check = async () => {
    setBusy(true)
    try {
      setState(await window.agentBridge.checkForUpdate())
    } finally {
      setBusy(false)
    }
  }

  const toggleAuto = async (next: boolean) => {
    setAutoUpdate(next)
    await window.agentBridge.setDesktopPrefs({ autoUpdate: next })
  }

  return (
    <div className="mt-6">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-[13px] font-medium text-ink">更新</h3>
        <label className="flex cursor-pointer items-center gap-1.5 text-[12.5px] text-ink-soft">
          <input
            type="checkbox"
            className="no-drag size-3.5 accent-[var(--brand)]"
            checked={autoUpdate}
            onChange={(event) => void toggleAuto(event.target.checked)}
          />
          自动检查更新
        </label>
      </div>

      <div className="mt-2 rounded-[10px] border border-line px-3.5 py-3">
        <p className="text-[12.5px] leading-relaxed text-ink">{state.message}</p>

        {downloading ? (
          <div className="mt-2.5">
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-line-soft">
              <div
                className="h-full rounded-full bg-brand transition-[width] duration-300"
                style={{ width: `${percent}%` }}
              />
            </div>
            <p className="mt-1 text-[11.5px] text-ink-faint">
              {state.downloaded} / {state.total} 个文件（{percent}%）
            </p>
          </div>
        ) : null}

        <div className="mt-3 flex flex-wrap gap-2">
          {state.pendingApply ? (
            <button
              type="button"
              onClick={() => void window.agentBridge.applyUpdateNow()}
              className="no-drag rounded-md bg-brand px-2.5 py-1 text-[12.5px] text-white"
            >
              重启并更新
            </button>
          ) : null}

          {state.phase === 'need-full' ? (
            <button
              type="button"
              onClick={() => void window.agentBridge.openFullPackage()}
              className="no-drag rounded-md bg-brand px-2.5 py-1 text-[12.5px] text-white"
            >
              下载完整安装包
            </button>
          ) : null}

          <button
            type="button"
            disabled={busy || !state.supported || state.phase === 'checking'}
            onClick={() => void check()}
            className="no-drag rounded-md border border-line px-2.5 py-1 text-[12.5px] text-ink transition-colors hover:border-brand hover:text-brand disabled:opacity-50"
          >
            {state.phase === 'checking' ? '检查中…' : '检查更新'}
          </button>
        </div>

        {state.lastCheckedAt ? (
          <p className="mt-2 text-[11.5px] text-ink-faint">
            上次检查：{new Date(state.lastCheckedAt).toLocaleString()}
          </p>
        ) : null}
      </div>
    </div>
  )
}
