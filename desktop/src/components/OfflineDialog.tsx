import { CloudOff } from 'lucide-react'

import { Button } from '@/components/ui'
import { useAccountStore } from '@/stores/accountStore'










export function OfflineDialog() {
  const snapshot = useAccountStore((state) => state.snapshot)
  const answerOffline = useAccountStore((state) => state.answerOffline)

  if (!snapshot?.offlinePrompt) return null

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-6">
      <div className="absolute inset-0 bg-black/35 backdrop-blur-[1px]" />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="offline-title"
        className="animate-enter relative flex w-full max-w-sm flex-col overflow-hidden rounded-[12px] border border-line bg-canvas shadow-[0_18px_48px_rgba(0,0,0,0.18)]"
      >
        <div className="px-5 pt-5 text-center">
          <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-panel text-ink-soft">
            <CloudOff size={22} />
          </div>
          <h2 id="offline-title" className="mt-3 text-[15px] font-semibold text-ink">
            部分功能需要联网才能使用
          </h2>
          <p className="mt-1.5 text-[12.5px] leading-relaxed text-ink-soft">
            账号、余额与赞助这些功能现在用不了；对话与其它本地功能不受影响。联网后会自动恢复。
          </p>
        </div>
        <footer className="flex items-center justify-center gap-2 px-5 py-4">
          <Button onClick={() => void answerOffline('continue')}>继续使用（离线）</Button>
          <Button variant="primary" onClick={() => void answerOffline('skip')}>
            跳过检测
          </Button>
        </footer>
      </div>
    </div>
  )
}
