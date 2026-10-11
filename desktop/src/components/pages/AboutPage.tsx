import { useAppStore } from '@/stores/appStore'

/** 「关于」页 —— 从设置栏挪出，作为左侧导航的独立入口（产品要求）。 */
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
          自研智能体框架的 Windows 桌面客户端。所有数据保存在本机，不上传云端；
          模型服务商密钥仅存于本地配置文件。
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
      </div>
    </div>
  )
}
