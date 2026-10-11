import { ShieldAlert } from 'lucide-react'

import { ParamTable } from '@/components/chat/ParamTable'
import { Badge, Button, Modal } from '@/components/ui'
import { useChatStore } from '@/stores/chatStore'
import { useVoiceCommand } from '@/stores/voiceCommandStore'

const LEVEL_TEXT: Record<string, string> = {
  confirm: '需要确认',
  admin: '高危操作',
}

/**
 * 权限确认弹窗。
 *
 * 对应开发文档第 10 章：有副作用的操作必须人工确认，且**不确认即不执行**。
 * 这里把工具名、参数、风险等级全部摊开给用户看，而不是只给一句"是否继续"。
 */
export function ConfirmDialog() {
  const permission = useChatStore((state) => state.permission)
  const activeSessionId = useChatStore((state) => state.activeSessionId)
  const respond = useChatStore((state) => state.respondPermission)

  // ---- 语音 ----
  //
  // 权限确认是最该能用语音的一类：弹窗是**别的地方**触发出来的（定时任务、群聊里
  // 某个搭子），用户的手和注意力往往都不在这儿，这时还要腾手去点一下"允许执行"
  // 特别烦。说一句就等于点。
  //
  // ⚠️ 这是**危险**命令（会真的放行一个有副作用的操作），所以它的命令词默认为
  // 「允许执行」而不是「好」—— 短词在语音场景太容易误触发，用户也可以随时改词
  // 或干脆停用它（见设置里的语音命令）。
  //
  // 两个 hook 必须在 `if (!permission)` 之前：hook 不能有条件地调用。
  // 弹窗没显示时传 `null`，命令表里就没有它们。
  const askable = permission !== null
  useVoiceCommand('confirm.allow', askable ? () => void respond(true) : null)
  useVoiceCommand('confirm.reject', askable ? () => void respond(false) : null)

  if (!permission) return null

  const dangerous = permission.permissionLevel === 'admin'
  // 单聊里**别的**对话发来的确认请求要标明来源：现在多个会话能同时跑，
  // 用户完全可能在 A 对话看到一条属于 B 对话的确认框，不说清就会以为是误弹。
  // 属于眼前这条对话时不加这句 —— 那是废话，只会占地方。
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
            onClick={() => void respond(true)}
          >
            允许执行
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
              // 说清"这是从哪冒出来的"：群聊里是某个搭子在讨论中要求的，
              // 而用户此刻的注意力可能在别的页面 —— 不写来源只会让人以为是误弹
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

      <p className="mt-3 text-[11.5px] leading-relaxed text-ink-faint">
        超过等待时间未响应将自动视为拒绝，且本次操作不会被执行。
      </p>
    </Modal>
  )
}
