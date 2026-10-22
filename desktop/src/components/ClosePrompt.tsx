import type { ClosePromptResult } from '@shared/bridge'
import { AlertTriangle } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Button, Modal, Switch } from '@/components/ui'
import { useAssistantStore } from '@/stores/assistantStore'
import { useChatStore } from '@/stores/chatStore'
















export function ClosePrompt() {
  const [open, setOpen] = useState(false)
  const [remember, setRemember] = useState(false)
  
  
  
  
  
  
  const runningCount = useChatStore((state) => Object.keys(state.runs).length)
  const runningAssistantId = useChatStore((state) => state.runningAssistantId)
  const runningName = useAssistantStore((state) => {
    const running = state.assistants.find((item) => item.id === runningAssistantId)
    return running?.name ?? '搭子'
  })

  useEffect(() => {
    
    
    return window.agentBridge?.onClosePrompt(() => {
      
      
      setRemember(false)
      setOpen(true)
    })
  }, [])

  const answer = (action: ClosePromptResult) => {
    
    
    setOpen(false)
    window.agentBridge?.answerClosePrompt({ action, remember })
  }

  return (
    <Modal
      open={open}
      
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
      {

}
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
              {
}
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
