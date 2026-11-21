import { CheckCircle2, Loader2, XCircle } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Button, Field, Input, Modal, Select, Switch } from '@/components/ui'
import { useAppStore } from '@/stores/appStore'
import { useAssistantStore } from '@/stores/assistantStore'
import type { FeishuBot } from '@/types'









export function FeishuBotDialog({
  open,
  bot,
  onClose,
  onSaved,
}: {
  open: boolean
  
  bot: FeishuBot | null
  onClose: () => void
  onSaved: () => void
}) {
  const api = useAppStore((state) => state.api)
  const assistants = useAssistantStore((state) => state.assistants)

  const [name, setName] = useState('')
  const [appId, setAppId] = useState('')
  const [appSecret, setAppSecret] = useState('')
  const [assistantId, setAssistantId] = useState('')
  const [groupPolicy, setGroupPolicy] = useState<'mention' | 'all'>('mention')
  const [syncReply, setSyncReply] = useState(true)

  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [probe, setProbe] = useState<{ ok: boolean; text: string } | null>(null)
  const [error, setError] = useState('')

  
  useEffect(() => {
    if (!open) return
    setName(bot?.name ?? '')
    setAppId(bot?.app_id ?? '')
    setAppSecret('')
    setAssistantId(bot?.assistant_id ?? assistants[0]?.id ?? '')
    setGroupPolicy(bot?.group_policy ?? 'mention')
    setSyncReply(bot?.sync_reply_to_feishu ?? true)
    setProbe(null)
    setError('')
  }, [open, bot, assistants])

  const canSave = name.trim().length > 0 && appId.trim().length > 0 && assistantId.length > 0

  const runTest = () => {
    if (!api) return
    setTesting(true)
    setProbe(null)
    setError('')
    void api
      .testFeishuBot({
        bot_id: bot?.id ?? '',
        app_id: appId.trim(),
        
        app_secret: appSecret.trim(),
      })
      .then((result) => {
        setProbe({ ok: true, text: `已连通：${result.app_name || '（飞书未返回名称）'}` })
      })
      .catch((err: unknown) => {
        
        setProbe({ ok: false, text: err instanceof Error ? err.message : String(err) })
      })
      .finally(() => setTesting(false))
  }

  const submit = () => {
    if (!api || !canSave) return
    setSaving(true)
    setError('')

    const payload = {
      name: name.trim(),
      app_id: appId.trim(),
      assistant_id: assistantId,
      group_policy: groupPolicy,
      sync_reply_to_feishu: syncReply,
    }

    const request = bot
      ? api.updateFeishuBot(bot.id, {
          ...payload,
          
          ...(appSecret.trim() ? { app_secret: appSecret.trim() } : {}),
        })
      : api.createFeishuBot({ ...payload, app_secret: appSecret.trim() })

    void request
      .then(() => {
        onSaved()
        onClose()
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : String(err))
      })
      .finally(() => setSaving(false))
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={bot ? '编辑飞书机器人' : '新增飞书机器人'}
      description="一个机器人绑定一个搭子；飞书里发给它的消息会进入那个搭子的对话。"
      footer={
        <div className="flex w-full items-center justify-between gap-2">
          <Button
            size="sm"
            variant="secondary"
            disabled={testing || !appId.trim()}
            onClick={runTest}
            icon={testing ? <Loader2 size={12} className="animate-spin" /> : undefined}
          >
            {testing ? '测试中…' : '测试连接'}
          </Button>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="ghost" onClick={onClose}>
              取消
            </Button>
            <Button size="sm" variant="primary" disabled={!canSave || saving} onClick={submit}>
              {saving ? '保存中…' : '保存'}
            </Button>
          </div>
        </div>
      }
    >
      <div className="flex flex-col gap-3">
        <Field label="名称" hint="给你自己看的，比如「客服小助手」">
          <Input
            name="feishu-bot-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="例如：客服小助手"
          />
        </Field>

        <Field label="App ID" hint="飞书开放平台 → 应用详情 → 凭证与基础信息">
          <Input
            name="feishu-app-id"
            value={appId}
            onChange={(event) => setAppId(event.target.value)}
            placeholder="例如：cli_a1b2c3d4e5f6g7h8"
            spellCheck={false}
            autoComplete="off"
          />
        </Field>

        <Field
          label="App Secret"
          hint={
            bot?.has_secret
              ? '已保存过密钥；留空表示不修改，填新的会覆盖'
              : '与 App ID 在同一个页面，复制过来即可'
          }
        >
          <Input
            name="feishu-app-secret"
            type="password"
            value={appSecret}
            onChange={(event) => setAppSecret(event.target.value)}
            placeholder={
              bot?.has_secret ? '••••••（留空不修改）' : '例如：粘贴 App Secret'
            }
            spellCheck={false}
            autoComplete="new-password"
          />
        </Field>

        <Field label="绑定搭子" hint="飞书来的消息由这个搭子回；一个机器人只能绑一个">
          <Select
            value={assistantId}
            onChange={(event) => setAssistantId(event.target.value)}
          >
            {assistants.length === 0 ? <option value="">（还没有搭子）</option> : null}
            {assistants.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </Select>
        </Field>

        <Field
          label="群聊里怎么回"
          hint="单聊永远每条都回；这一项只管群聊"
        >
          <Select
            value={groupPolicy}
            onChange={(event) => setGroupPolicy(event.target.value as 'mention' | 'all')}
          >
            <option value="mention">只有 @ 它才回（推荐）</option>
            <option value="all">每条消息都回</option>
          </Select>
        </Field>

        <div className="flex items-center justify-between rounded-[8px] border border-line-soft px-3 py-2">
          <div className="pr-3">
            <div className="text-[12.5px] font-medium text-ink">客户端里的回复同步到飞书</div>
            <div className="mt-0.5 text-[11px] text-ink-faint">
              打开后，你在客户端里接着这个会话聊，对方在飞书也能收到
            </div>
          </div>
          <Switch checked={syncReply} onChange={setSyncReply} />
        </div>

        {probe ? (
          <div
            



            role="alert"
            className={
              probe.ok
                ? 'flex items-start gap-1.5 rounded-[8px] border border-success/30 bg-success/5 px-2.5 py-2 text-[11.5px] text-success'
                : 'flex items-start gap-1.5 rounded-[8px] border border-danger/30 bg-danger-soft px-2.5 py-2 text-[11.5px] text-danger'
            }
          >
            {probe.ok ? (
              <CheckCircle2 size={13} className="mt-0.5 shrink-0" />
            ) : (
              <XCircle size={13} className="mt-0.5 shrink-0" />
            )}
            <span className="break-all">{probe.text}</span>
          </div>
        ) : null}

        {error ? (
          <div
            role="alert"
            className="rounded-[8px] border border-danger/30 bg-danger-soft px-2.5 py-2 text-[11.5px] text-danger"
          >
            {error}
          </div>
        ) : null}
      </div>
    </Modal>
  )
}
