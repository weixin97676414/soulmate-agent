import { AlertTriangle, RefreshCw } from 'lucide-react'
import { useState } from 'react'

import { BrandMark } from '@/components/BrandMark'
import { Button, Spinner } from '@/components/ui'
import { useAppStore } from '@/stores/appStore'

/**
 * 启动等待页。
 *
 * Python 核心首次启动需要 1~3 秒（导入 pandas 之类的库会更久），
 * 这里给出明确的进度反馈；失败时把后端日志折叠展示，便于自助排查。
 */
export function BootScreen() {
  const error = useAppStore((state) => state.bootstrapError)
  const status = useAppStore((state) => state.backendStatus)
  const restartBackend = useAppStore((state) => state.restartBackend)
  const appInfo = useAppStore((state) => state.appInfo)

  const [logs, setLogs] = useState<string[]>([])
  const [showLogs, setShowLogs] = useState(false)

  // 通信桥不存在时，「查看后端日志」这个按钮本身也会崩（它走的正是这座桥），
  // 所以直接不渲染它，而不是让用户点了再看一个看不懂的错。
  const bridgeMissing = !window.agentBridge

  const loadLogs = async () => {
    if (!window.agentBridge) return
    setLogs(await window.agentBridge.getBackendLogs())
    setShowLogs(true)
  }

  return (
    <div className="flex min-h-0 flex-1 items-center justify-center bg-canvas">
      <div className="w-full max-w-[620px] px-8">
        {error ? (
          <>
            <div className="flex items-start gap-3 rounded-[10px] border border-danger/30 bg-danger-soft p-4">
              <AlertTriangle size={18} className="mt-0.5 shrink-0 text-danger" />
              <div className="min-w-0">
                <div className="text-[14px] font-medium text-ink">智能体核心启动失败</div>
                <pre className="selectable mt-1.5 max-h-[180px] overflow-auto text-[12px] whitespace-pre-wrap text-ink-soft">
                  {error}
                </pre>
              </div>
            </div>

            <div className="mt-4 flex items-center gap-2">
              <Button
                variant="primary"
                icon={<RefreshCw size={14} />}
                onClick={() => void restartBackend()}
              >
                重新启动
              </Button>
              {bridgeMissing ? null : (
                <Button onClick={() => void loadLogs()}>查看后端日志</Button>
              )}
            </div>

            {showLogs ? (
              <pre className="selectable mt-3 max-h-[240px] overflow-auto rounded-[8px] border border-line bg-panel p-3 text-[11.5px] leading-relaxed whitespace-pre-wrap text-ink-soft">
                {logs.length ? logs.join('\n') : '（暂无日志）'}
              </pre>
            ) : null}

            <div className="mt-4 text-[12px] leading-relaxed text-ink-faint">
              {bridgeMissing ? (
                <>
                  界面与主程序的通信桥没有建立起来。这是客户端安装本身的问题，
                  与 Python 环境无关，重新安装即可。
                </>
              ) : (
                <>
                  常见原因：Python 依赖未安装（在 core 目录执行
                  <code className="mx-1 rounded bg-panel px-1 py-0.5">
                    .venv\Scripts\pip install -e .
                  </code>
                  ）、虚拟环境路径被移动、或配置文件损坏。 数据目录：
                  {appInfo?.dataDir ?? '—'}
                </>
              )}
            </div>
          </>
        ) : (
          <div className="flex flex-col items-center gap-4 text-center">
            {/* 品牌加载动画（产品要求）：等待期给一个明确的"正在启动"观感，
                而不是一块静止的空白。logo 做呼吸脉冲、底部一条循环进度条。 */}
            <BrandMark size={56} radius={14} className="animate-pulse" />
            <div className="text-[14px] font-medium text-ink">正在启动 Soulmate Agent…</div>
            <div className="flex items-center gap-2 text-[12.5px] text-ink-soft">
              <Spinner className="h-3.5 w-3.5 text-brand" />
              {status.message}
            </div>
            <div className="mt-1 h-[3px] w-[220px] overflow-hidden rounded-full bg-line">
              <div className="boot-progress h-full w-1/3 rounded-full bg-brand" />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
