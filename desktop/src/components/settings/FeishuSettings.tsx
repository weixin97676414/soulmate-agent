import clsx from 'clsx'
import {
  AlertTriangle,
  ChevronDown,
  MessageSquarePlus,
  Pencil,
  RotateCw,
  Plus,
  RefreshCw,
  Send,
  Trash2,
} from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import { Button, EmptyState, Modal, Switch } from '@/components/ui'
import { useAppStore } from '@/stores/appStore'
import { useAssistantStore } from '@/stores/assistantStore'
import { useNotificationStore } from '@/stores/notificationStore'
import { subscribeAppEvents } from '@/stores/notificationStore'
import type { FeishuBot, FeishuStatus } from '@/types'

import { FeishuBotDialog } from './FeishuBotDialog'


const STATE_META: Record<string, { label: string; dot: string }> = {
  connected: { label: '已连接', dot: 'bg-success' },
  connecting: { label: '连接中', dot: 'bg-brand animate-pulse' },
  not_started: { label: '待接入', dot: 'bg-ink-faint' },
  error: { label: '出错', dot: 'bg-danger' },
  disabled: { label: '未启用', dot: 'bg-ink-faint' },
}












const GUIDE_STEPS: Array<{ title: string; items: string[] }> = [
  {
    title: '① 创建应用',
    items: [
      '打开飞书开放平台（open.feishu.cn）→「开发者后台」→「创建企业自建应用」',
      '⚠️ 需要有**企业管理员权限**。飞书个人版账号创建不了自建应用，这一步绕不过去',
    ],
  },
  {
    title: '② 开启机器人能力',
    items: [
      '进入应用 →「添加应用能力」→ 添加「**机器人**」',
      '没开这一步，凭据能通过校验，但一条消息都收不到',
    ],
  },
  {
    title: '③ 开通权限（共五项，缺一不可）',
    items: [
      '`im:message` —— 读取用户发给机器人的消息',
      '`im:message.p2p_msg:readonly` —— **单聊**消息。界面上写「开通任一即可」，但只在单聊里说话就必须开这一条（最常见的坑）',
      '`im:message.group_msg` —— **群聊**消息。要在群里用时需要',
      '`im:message:send_as_bot` —— 以机器人身份回复',
      '`im:resource` —— 下载图片/文件；`im:chat:readonly` —— 读群名（用作会话标题，可不开，不开则标题叫「飞书会话」）',
    ],
  },
  {
    title: '④ 配置事件订阅',
    items: [
      '「事件与回调」→「事件配置」→ 订阅方式选「**使用长连接接收事件**」并保存',
      '⚠️ 不要选「将事件发送至开发者服务器」——本机没有公网地址，填了也永远收不到',
      '同一页「添加事件」→ 搜索并添加 `im.message.receive_v1`（接收消息）',
    ],
  },
  {
    title: '⑤ 发布版本',
    items: [
      '「版本管理与发布」→ 创建版本 → 申请发布（开发版可自助通过）',
      '⚠️ **权限和事件订阅的改动，不发版不生效**。界面上显示「已开通」只代表申请过',
    ],
  },
  {
    title: '⑥ 回到这里',
    items: [
      '填写 App ID 与 App Secret → 点「测试连接」',
      '通过后保存，然后在飞书里给机器人发一条消息试试',
    ],
  },
]







export function FeishuSettings() {
  const api = useAppStore((state) => state.api)
  const assistants = useAssistantStore((state) => state.assistants)
  const notify = useNotificationStore((state) => state.push)

  const [bots, setBots] = useState<FeishuBot[]>([])
  const [status, setStatus] = useState<FeishuStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [guideOpen, setGuideOpen] = useState(true)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<FeishuBot | null>(null)
  const [pendingDelete, setPendingDelete] = useState<FeishuBot | null>(null)

  const reload = useCallback(() => {
    if (!api) return
    void api
      .listFeishuBots()
      .then((result) => setBots(result.bots))
      .catch((err: unknown) => {
        notify({
          level: 'error',
          title: '读取飞书机器人失败',
          message: err instanceof Error ? err.message : String(err),
        })
      })
      .finally(() => setLoading(false))
  }, [api, notify])

  useEffect(() => {
    reload()
  }, [reload])

  
  useEffect(() => {
    return subscribeAppEvents((type) => {
      if (type === 'feishu_changed') reload()
    })
  }, [reload])

  




  useEffect(() => {
    if (!api) return
    let timer: ReturnType<typeof setInterval> | null = null

    const tick = () => {
      void api
        .feishuStatus()
        .then(setStatus)
        .catch(() => {
          
        })
    }
    const start = () => {
      if (timer) return
      tick()
      timer = setInterval(tick, 5000)
    }
    const stop = () => {
      if (!timer) return
      clearInterval(timer)
      timer = null
    }
    const onVisibility = () => (document.hidden ? stop() : start())

    if (!document.hidden) start()
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      stop()
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [api])

  const stateOf = (bot: FeishuBot): string => {
    if (!bot.enabled) return 'disabled'
    const hit = status?.bots.find((item) => item.id === bot.id)
    return hit?.state ?? status?.bridge ?? 'not_started'
  }

  const errorOf = (bot: FeishuBot): string =>
    status?.bots.find((item) => item.id === bot.id)?.error ?? ''

  const assistantName = (id: string): string =>
    assistants.find((item) => item.id === id)?.name ?? id

  const toggle = (bot: FeishuBot, enabled: boolean) => {
    if (!api) return
    
    setBots((prev) => prev.map((item) => (item.id === bot.id ? { ...item, enabled } : item)))
    void api.updateFeishuBot(bot.id, { enabled }).catch((err: unknown) => {
      setBots((prev) =>
        prev.map((item) => (item.id === bot.id ? { ...item, enabled: !enabled } : item)),
      )
      notify({
        level: 'error',
        title: '切换失败',
        message: err instanceof Error ? err.message : String(err),
      })
    })
  }

  const confirmDelete = () => {
    if (!api || !pendingDelete) return
    const target = pendingDelete
    setPendingDelete(null)
    void api
      .deleteFeishuBot(target.id)
      .then(() => {
        notify({ level: 'success', title: '已删除', message: `「${target.name}」已断开接入` })
        reload()
      })
      .catch((err: unknown) => {
        notify({
          level: 'error',
          title: '删除失败',
          message: err instanceof Error ? err.message : String(err),
        })
      })
  }

  return (
    <div className="flex flex-col gap-3">
      {}
      <div className="rounded-[10px] border border-line bg-panel">
        <button
          type="button"
          onClick={() => setGuideOpen((value) => !value)}
          className="flex w-full items-center gap-2 px-3.5 py-2.5 text-left"
        >
          <Send size={14} className="shrink-0 text-brand" />
          <span className="text-[13px] font-semibold text-ink">怎么接一个飞书机器人</span>
          <span className="min-w-0 flex-1" />
          <ChevronDown
            size={14}
            className={clsx(
              'shrink-0 text-ink-faint transition-transform',
              guideOpen && 'rotate-180',
            )}
          />
        </button>
        {guideOpen ? (
          <div className="space-y-3 border-t border-line-soft px-3.5 py-3">
            {GUIDE_STEPS.map((group) => (
              <div key={group.title}>
                <div className="text-[11.5px] font-semibold text-ink">{group.title}</div>
                <ul className="mt-1 ml-4 list-disc space-y-1 text-[11.5px] leading-relaxed text-ink-soft">
                  {group.items.map((item) => (
                    
                    <li key={item}>{item.replace(/\*\*/g, '').replace(/`/g, '')}</li>
                  ))}
                </ul>
              </div>
            ))}

            <div className="flex items-start gap-1.5 rounded-[8px] border border-warning/30 bg-warning-soft px-2.5 py-2 text-[11.5px] leading-relaxed text-warning">
              <AlertTriangle size={13} className="mt-0.5 shrink-0" />
              <span>
                创建自建应用需要企业管理员权限；飞书个人版账号建不了。
                客户端没有公网地址，所以事件只能用「长连接」接收，不能填 Webhook 地址。
              </span>
            </div>

            <div className="flex items-start gap-1.5 rounded-[8px] border border-brand/30 bg-brand/5 px-2.5 py-2 text-[11.5px] leading-relaxed text-ink-soft">
              <RotateCw size={13} className="mt-0.5 shrink-0 text-brand" />
              <span>
                <b className="text-ink">改了绑定的搭子，需要重启客户端才生效。</b>
                {' '}长连接本身会自动重连，但「这个机器人归哪个搭子管」在会话建立时就定了 ——
                重启后飞书那边再发消息，才会进新搭子的对话。
              </span>
            </div>
          </div>
        ) : null}
      </div>

      {}
      <div className="flex items-center justify-between">
        <div className="text-[13px] font-semibold text-ink">
          机器人（{bots.length}）
          {status?.bridge === 'not_started' ? (
            <span className="ml-2 text-[11.5px] font-normal text-ink-faint">
              长连接待接入
            </span>
          ) : null}
        </div>
        <div className="flex items-center gap-1.5">
          <Button size="sm" variant="ghost" onClick={reload} icon={<RefreshCw size={12} />}>
            刷新
          </Button>
          <Button
            size="sm"
            variant="primary"
            icon={<Plus size={12} />}
            onClick={() => {
              setEditing(null)
              setDialogOpen(true)
            }}
          >
            新增机器人
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="rounded-[10px] border border-line bg-panel px-3.5 py-6 text-center text-[12px] text-ink-faint">
          正在读取…
        </div>
      ) : bots.length === 0 ? (
        <EmptyState
          icon={<MessageSquarePlus size={22} />}
          title="还没有接入飞书机器人"
          description="接入后，飞书里发给机器人的消息会自动出现在「对话」页，回复也会同步回去。"
          action={
            <Button
              size="sm"
              variant="primary"
              icon={<Plus size={12} />}
              onClick={() => {
                setEditing(null)
                setDialogOpen(true)
              }}
            >
              新增机器人
            </Button>
          }
        />
      ) : (
        <div className="flex flex-col gap-2">
          {bots.map((bot) => {
            const state = stateOf(bot)
            const meta = STATE_META[state] ?? STATE_META.not_started
            const reason = errorOf(bot)
            return (
              <div
                key={bot.id}
                className="flex items-center gap-3 rounded-[10px] border border-line bg-panel px-3.5 py-2.5 transition-colors hover:border-brand/40"
              >
                <span
                  className={clsx('h-2 w-2 shrink-0 rounded-full', meta.dot)}
                  title={reason || meta.label}
                />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] font-medium text-ink">{bot.name}</div>
                  <div className="truncate text-[11.5px] text-ink-faint">
                    绑定：{assistantName(bot.assistant_id)} · 群聊
                    {bot.group_policy === 'mention' ? '仅 @ 时回复' : '全部回复'}
                    {bot.has_secret ? '' : ' · ⚠️ 未配置密钥'}
                  </div>
                  {reason ? (
                    <div className="mt-0.5 truncate text-[11px] text-danger">{reason}</div>
                  ) : null}
                </div>
                <span className="shrink-0 text-[11.5px] text-ink-faint">{meta.label}</span>
                {}
                <Switch
                  checked={bot.enabled}
                  onChange={(value) => toggle(bot, value)}
                  label={`启用「${bot.name}」`}
                />
                <button
                  type="button"
                  aria-label={`编辑「${bot.name}」`}
                  onClick={() => {
                    setEditing(bot)
                    setDialogOpen(true)
                  }}
                  className="shrink-0 rounded-[6px] p-1.5 text-ink-faint transition-colors hover:bg-hover hover:text-ink focus-visible:ring-2 focus-visible:ring-brand/50 focus-visible:outline-none"
                >
                  <Pencil size={13} aria-hidden="true" />
                </button>
                <button
                  type="button"
                  aria-label={`删除「${bot.name}」`}
                  onClick={() => setPendingDelete(bot)}
                  className="shrink-0 rounded-[6px] p-1.5 text-ink-faint transition-colors hover:bg-danger-soft hover:text-danger focus-visible:ring-2 focus-visible:ring-danger/50 focus-visible:outline-none"
                >
                  <Trash2 size={13} aria-hidden="true" />
                </button>
              </div>
            )
          })}
        </div>
      )}

      <FeishuBotDialog
        open={dialogOpen}
        bot={editing}
        onClose={() => setDialogOpen(false)}
        onSaved={reload}
      />

      <Modal
        open={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        title="断开这个机器人？"
        description={`「${pendingDelete?.name ?? ''}」将不再接收消息。已有的飞书会话和聊天记录会保留。`}
        footer={
          <div className="flex items-center justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => setPendingDelete(null)}>
              取消
            </Button>
            <Button size="sm" variant="danger" onClick={confirmDelete}>
              删除
            </Button>
          </div>
        }
      >
        <p className="text-[12.5px] leading-relaxed text-ink-soft">
          这里的删除只是**断开接入**。你之前在飞书里和它聊过的内容，在「对话」页仍然看得到。
        </p>
      </Modal>
    </div>
  )
}
