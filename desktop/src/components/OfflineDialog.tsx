import { CloudOff } from 'lucide-react'

import { Button } from '@/components/ui'
import { useAccountStore } from '@/stores/accountStore'

/**
 * 断网提示（文档 §6.1 S2）。
 *
 * 这是**全应用唯一一处**会拦一下用户的账号相关提示 —— 因为断网时账号/充值
 * 确实不可用，必须让人知道。但它不是模态死锁：两个按钮都能进主界面，区别只在于
 * 「跳过检测」会让本次运行不再每 60 秒静默重试（否则会反复弹）。
 *
 * 一个会话只弹一次：引擎侧用 `offlinePrompt` 控制，弹完回答一次就收起。
 */
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
