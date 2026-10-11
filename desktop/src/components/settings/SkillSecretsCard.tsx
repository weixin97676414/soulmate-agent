import { useCallback, useEffect, useState } from 'react'

import { Card } from '@/components/account/Card'
import { useNotificationStore } from '@/stores/notificationStore'
import type { SkillSecretsView } from '@shared/bridge'
import { KeyRound, Loader2, ShieldAlert, ShieldCheck, Trash2 } from 'lucide-react'

/**
 * 「给技能的密钥」管理面板。
 *
 * ## 为什么必须有它
 *
 * 没有删除入口 = 用户**无法撤销**自己交出去的东西。这在别的设置里只是不便，
 * 在这里是安全问题：他可能把一把**用错地方**的私钥粘了进来，
 * 而唯一的补救办法是去翻应用数据目录手删文件 —— 那不该是给普通用户的答案。
 *
 * ## ⚠️ 这里**看不到明文**，而且是刻意的
 *
 * `getSkillSecrets` 只返回名字与脱敏预览。要换一把就重新提供（覆盖同名即可）：
 * "能看"和"能被偷看"是同一件事，而这些是用户主动粘进来的私钥。
 * 这一条与已有的模型密钥库**故意不一致**（那边有"小眼睛"）——
 * 那边是用户自己申请的 API Key、需要核对有没有粘全；这边通常是复制来的长串。
 */
export function SkillSecretsCard() {
  const [view, setView] = useState<SkillSecretsView | null>(null)
  const [busy, setBusy] = useState(false)
  const push = useNotificationStore((state) => state.push)

  const refresh = useCallback(async (): Promise<void> => {
    const bridge = window.agentBridge
    if (!bridge?.getSkillSecrets) return
    try {
      setView(await bridge.getSkillSecrets())
    } catch {
      // 读不到就当"没有"：这只是个展示面板，不该因为它把设置页搞崩
      setView(null)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const remove = async (names: string[]): Promise<void> => {
    const bridge = window.agentBridge
    if (!bridge?.removeSkillSecrets) return
    setBusy(true)
    try {
      setView(await bridge.removeSkillSecrets(names))
      push({
        level: 'success',
        title: '已删除',
        message: names.length ? `已删除 ${names.length} 项` : '已清空全部',
      })
    } catch (error) {
      push({
        level: 'error',
        title: '删除失败',
        message: error instanceof Error ? error.message : String(error),
      })
    } finally {
      setBusy(false)
    }
  }

  const names = view?.names ?? []

  return (
    <Card
      title="给技能的密钥"
      actions={
        names.length > 0 ? (
          <button
            type="button"
            disabled={busy}
            onClick={() => void remove([])}
            className="flex items-center gap-1 rounded-[7px] px-2 py-1 text-[11.5px] text-danger transition-colors hover:bg-danger/10 disabled:opacity-50"
          >
            <Trash2 size={12} /> 全部清空
          </button>
        ) : null
      }
    >
      <p className="text-[11.5px] leading-relaxed text-ink-faint">
        搭子请求你提供、并且<strong className="font-semibold text-ink-soft">只保存在这台电脑上</strong>
        的凭据（私钥、API Secret 之类）。它们不会发送给模型，AI 也看不到。
      </p>

      <div className="mt-2 flex items-center gap-2">
        {view?.protection === 'encrypted' ? (
          <span className="flex items-center gap-1.5 text-[11.5px] text-success">
            <ShieldCheck size={13} /> 本地加密已启用
          </span>
        ) : (
          // ⚠️ 明文降级必须**显眼**：那一刻这些私钥就是磁盘上的明文文件，
          // 而用户完全没有别的途径知道这件事。
          <span className="flex items-center gap-1.5 text-[11.5px] font-medium text-warning">
            <ShieldAlert size={13} /> 系统未提供加密，这些内容以明文保存在本机
          </span>
        )}
        {names.length > 0 ? (
          <span className="text-[11.5px] text-ink-faint">共 {names.length} 项</span>
        ) : null}
      </div>

      {names.length === 0 ? (
        <p className="mt-2 flex items-center gap-1.5 text-[12px] text-ink-faint">
          <KeyRound size={13} /> 还没有保存任何密钥。搭子需要时会弹窗请你提供。
        </p>
      ) : (
        <ul className="mt-2 divide-y divide-line-soft overflow-hidden rounded-[10px] border border-line">
          {names.map((name) => (
            <li key={name} className="flex items-center gap-3 px-3.5 py-2.5">
              <div className="min-w-0 flex-1">
                <code className="text-[12px] text-ink">{name}</code>
                <p className="mt-0.5 font-mono text-[11.5px] text-ink-faint">
                  {view?.masked?.[name] ?? ''}
                </p>
              </div>
              <button
                type="button"
                disabled={busy}
                aria-label={`删除 ${name}`}
                title={`删除 ${name}`}
                onClick={() => void remove([name])}
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[6px] text-ink-faint transition-colors hover:bg-danger/10 hover:text-danger disabled:opacity-50"
              >
                {busy ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
