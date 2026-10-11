import type { ClosePromptResult } from '@shared/bridge'
import { AlertTriangle } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Button, Modal, Switch } from '@/components/ui'
import { useAssistantStore } from '@/stores/assistantStore'
import { useChatStore } from '@/stores/chatStore'

/**
 * 点右上角 × 时弹出的关闭询问。
 *
 * **风格刻意与应用一致**：早先这里用的是 Windows 原生对话框，实测反馈
 * "看起来像另一个程序的提示"。原生窗的外观不是应用能控制的，所以改成应用内弹窗。
 *
 * ⚠️ 主进程侧的兜底规则（第 91 批，L-04 更正了这里的过期描述）：
 * **渲染层活着时只发这个应用内弹窗、没有任何超时回退**；只有渲染层没起来/已崩时，
 * 主进程才改用系统对话框（见 `electron/main.ts` 的 `askCloseAction`）。
 * 以前这里写的是"有 1.5s 超时退回原生对话框"——那一版因为**两个弹窗同时出现**
 * 已经被删掉了（历史原因见 `main.ts` 里 `askCloseAction` 的注释）。
 *
 * **所以这个组件仍然必须能立刻渲染**，别在这里做任何异步准备工作：
 * 现在没有回退意味着"慢"不再是弹两个框，而是**用户盯着一个还没出现的框等**。
 */
export function ClosePrompt() {
  const [open, setOpen] = useState(false)
  const [remember, setRemember] = useState(false)
  // 有搭子在后台干活时，这个弹窗要额外说清楚"退出会打断它"（要求 #8）。
  // 任务状态住在 chatStore 里，所以只有渲染层知道这件事 —— 这正是
  // 「提醒」放在这个组件而不是主进程的原因。
  // ⚠️ 判据是"**有没有**任务在跑"，不是"当前可见会话在不在跑"：
  // 用户切到设置页、眼前那条没在跑，但后台可能还有搭子在干活 ——
  // 这时候退出，损失是一模一样的。所以数 `runs` 的个数。
  const runningCount = useChatStore((state) => Object.keys(state.runs).length)
  const runningAssistantId = useChatStore((state) => state.runningAssistantId)
  const runningName = useAssistantStore((state) => {
    const running = state.assistants.find((item) => item.id === runningAssistantId)
    return running?.name ?? '搭子'
  })

  useEffect(() => {
    // 返回退订函数：React 严格模式下 effect 会跑两次，
    // 不退订就会叠出两个弹窗（而且第二个永远关不掉）
    return window.agentBridge?.onClosePrompt(() => {
      // 每次重新询问都把复选框复位：上次的选择已经被"写入偏好"这条路径记住了，
      // 这里再带过来会让用户以为"它自己勾上了"
      setRemember(false)
      setOpen(true)
    })
  }, [])

  const answer = (action: ClosePromptResult) => {
    // 先收起弹窗再回传：主进程收到回应后会立刻隐藏窗口或退出，
    // 弹窗留在屏幕上会闪一下
    setOpen(false)
    window.agentBridge?.answerClosePrompt({ action, remember })
  }

  return (
    <Modal
      open={open}
      // Esc / 点空白处 = 取消这次关闭，窗口保持打开
      onClose={() => answer('cancel')}
      title="关闭窗口"
      description="最小化到托盘后应用仍在后台运行，可以从托盘图标重新打开。"
      width="max-w-md"
      footer={
        <div className="flex flex-wrap items-center justify-between gap-3">
          <label className="flex cursor-pointer items-center gap-2 text-[12px] text-ink-soft">
            <Switch checked={remember} onChange={setRemember} label="记住我的选择" />
            记住我的选择
          </label>
          <div className="flex gap-2">
            <Button onClick={() => answer('quit')}>退出应用</Button>
            <Button variant="primary" onClick={() => answer('tray')}>
              最小化到托盘
            </Button>
          </div>
        </div>
      }
    >
      {/* 有搭子在干活时，把后果明确说出来（要求 #8）。
          用户最可能踩的坑是：以为自己只是"关掉窗口"，实际上把正在做的事一起停了。
          退出 = 后端进程结束 = 任务真的没了；进托盘 = 任务继续跑。 */}
      {runningCount > 0 ? (
        <div className="mb-3 flex items-start gap-2 rounded-[8px] border border-warning/30 bg-warning-soft px-3 py-2">
          <AlertTriangle size={14} className="mt-0.5 shrink-0 text-warning" />
          <div className="text-[12.5px] leading-relaxed text-ink">
            <span className="font-medium">
              {runningCount > 1
                ? `有 ${runningCount} 个搭子正在工作。`
                : `「${runningName}」正在工作。`}
            </span>
            <br />
            <span className="text-ink-soft">
              最小化到托盘：它会在后台继续做完。
              <br />
              {/* 这里原来是 `**被中断**`，而这段是纯文本 JSX —— 用户看到的是
                  带着星号的原文。改成真正的强调，别再让记号直接露出来。 */}
              退出应用：这一次的工作会
              <span className="font-medium text-ink">被中断</span>。
            </span>
          </div>
        </div>
      ) : null}
      <p className="text-[12.5px] leading-relaxed text-ink-soft">
        想彻底退出时，右键点击右下角托盘区的应用图标，选择「退出」即可。
        这个选择之后也可以在左边「安全与通用」页的「点关闭按钮时」里改。
      </p>
      <p className="mt-2 text-[11.5px] text-ink-faint">
        按 Esc 或点击空白处 = 取消，窗口继续开着。
      </p>
    </Modal>
  )
}
