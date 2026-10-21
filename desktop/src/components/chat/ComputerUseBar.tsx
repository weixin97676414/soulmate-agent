































import { Square } from 'lucide-react'

import { useChatStore } from '@/stores/chatStore'
import type { ChatMessage, ToolCallState } from '@/types'








const COMPUTER_PREFIX = 'computer_'


function runningComputerTool(messages: ChatMessage[]): ToolCallState | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const tools = messages[i]?.toolCalls
    if (!tools?.length) continue
    for (let j = tools.length - 1; j >= 0; j -= 1) {
      const tool = tools[j]
      if (tool?.status === 'running' && tool.name.startsWith(COMPUTER_PREFIX)) {
        return tool
      }
    }
  }
  return null
}

export function ComputerUseBar({ messages }: { messages: ChatMessage[] }) {
  const stop = useChatStore((state) => state.stop)
  const tool = runningComputerTool(messages)

  
  if (!tool) return null

  return (
    <div className="flex shrink-0 items-center gap-2 rounded-[12px] border border-line bg-panel px-3 py-2">
      {}
      <span className="relative flex h-2 w-2 shrink-0">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand opacity-60" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-brand" />
      </span>
      <span className="shrink-0 text-[12px] font-medium text-ink">搭子正在操作你的电脑</span>
      <span className="min-w-0 flex-1 truncate text-[11.5px] text-ink-faint">
        {tool.displayName}
      </span>
      <button
        type="button"
        onClick={() => {
          void stop()
        }}
        title="立刻停止，把控制权拿回来"
        className="flex shrink-0 items-center gap-1 rounded-[8px] border border-danger/30 px-2 py-0.5 text-[11.5px] text-danger transition-colors hover:bg-danger-soft"
      >
        <Square size={11} />
        急停
      </button>
    </div>
  )
}
