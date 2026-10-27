import { useState } from 'react'
import { ShieldAlert } from 'lucide-react'

import { ParamTable } from '@/components/chat/ParamTable'
import { Badge, Button, Modal } from '@/components/ui'
import { useChatStore } from '@/stores/chatStore'
import { useVoiceCommand } from '@/stores/voiceCommandStore'

const LEVEL_TEXT: Record<string, string> = {
  confirm: '需要确认',
  admin: '高危操作',
}







export function ConfirmDialog() {
  const permission = useChatStore((state) => state.permission)
  const activeSessionId = useChatStore((state) => state.activeSessionId)
  const respond = useChatStore((state) => state.respondPermission)
  
  const [remember, setRemember] = useState(false)

  
  
  
  
  
  
  
  
  
  
  
  
  const askable = permission !== null
  useVoiceCommand('confirm.allow', askable ? () => void respond(true) : null)
  useVoiceCommand('confirm.reject', askable ? () => void respond(false) : null)

  if (!permission) return null

  const dangerous = permission.permissionLevel === 'admin'
  
  
  
  const foreignSession =
    permission.sessionId && permission.sessionId !== activeSessionId
      ? permission.sessionTitle
        ? `来自对话「${permission.sessionTitle}」`
        : '来自另一个对话'
      : ''

  return (
    <Modal
      open
      onClose={() => void respond(false)}
      closeOnBackdrop={false}
      width="max-w-xl"
      title="操作确认"
      description="智能体请求执行一个可能产生副作用的操作，请确认后再继续。"
      footer={
        <>
          <Button onClick={() => void respond(false)}>拒绝</Button>
          <Button
            variant={dangerous ? 'danger' : 'primary'}
            onClick={() => void respond(true, remember)}
          >
            允许
          </Button>
        </>
      }
    >
      <div className="flex items-start gap-3">
        <div
          className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-[9px] ${
            dangerous ? 'bg-danger-soft text-danger' : 'bg-warning-soft text-warning'
          }`}
        >
          <ShieldAlert size={16} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[14px] font-medium text-ink">{permission.displayName}</span>
            <Badge tone={dangerous ? 'danger' : 'warning'}>
              {LEVEL_TEXT[permission.permissionLevel] ?? permission.permissionLevel}
            </Badge>
            <code className="rounded-[4px] bg-panel px-1.5 py-[1px] text-[11px] text-ink-faint">
              {permission.skillName}
            </code>
            {permission.source ? (
              
              
              <span className="text-[11.5px] text-ink-faint">来自 {permission.source}</span>
            ) : foreignSession ? (
              <span className="text-[11.5px] text-ink-faint">{foreignSession}</span>
            ) : null}
          </div>
          {permission.description ? (
            <p className="mt-1.5 text-[12.5px] leading-relaxed text-ink-soft">
              {permission.description}
            </p>
          ) : null}
        </div>
      </div>

      <div className="mt-4">
        <div className="mb-1.5 text-[11.5px] font-medium text-ink-faint">将要使用的参数</div>
        <ParamTable skillName={permission.skillName} params={permission.params ?? {}} />
      </div>

      {}
      {dangerous ? (
        <p className="mt-3 text-[11.5px] leading-relaxed text-danger">
          这是高危操作（删除 / 执行命令 / 系统控制 / 密钥），每次都必须你亲自确认，不能记住。
        </p>
      ) : (
        <label className="mt-3 flex cursor-pointer items-center gap-2 text-[12px] text-ink-soft">
          <input
            type="checkbox"
            checked={remember}
            onChange={(event) => setRemember(event.target.checked)}
            className="h-3.5 w-3.5 accent-[var(--brand)]"
          />
          记住这个技能，以后同类操作不再询问（可在设置里一键撤销）
        </label>
      )}

      <p className="mt-3 text-[11.5px] leading-relaxed text-ink-faint">
        超过等待时间未响应将自动视为拒绝，且本次操作不会被执行。
      </p>
    </Modal>
  )
}
