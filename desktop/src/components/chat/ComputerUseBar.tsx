/**
 * 「搭子正在操作你的电脑」提示条 + 一键急停。
 *
 * ## 为什么需要它
 *
 * 「操作用户的键盘鼠标」是唯一一类**会直接改动用户正在用的东西**的能力：
 * 点错一下可能关掉他没保存的文档、点错一个按钮可能把钱转出去。所以除了
 * "每一步都先弹确认"（那是后端的 `permission_level="confirm"`，见
 * core/src/my_agent/skill/builtin/computer.py），界面上还必须有一块
 * **常驻的"正在被操作"提示** —— 否则用户只是走开接杯水，回来发现屏幕上
 * 有一串自己没做过的动作，却不知道是谁在动、也不知道怎么让它停。
 *
 * ## 数据从哪来（刻意不新建状态机）
 *
 * 直接用当前会话消息里的**工具调用状态**：`tool_call` 事件进来时状态是
 * `running`、`tool_result` 进来时变 `done/failed`（见 chatStore 的
 * `onToolCall` / `onToolResult`）。所以"有没有电脑操作正在进行"只是对
 * messages 的一次派生，不需要在 store 里再维护一份并行状态 —— 两份状态
 * 迟早会不一致（关掉一轮时只清了一份，提示条就永远挂在屏幕上）。
 *
 * ⚠️ 传的是整个 `messages`（与 `PlanBar` 同理）：正在进行的那次调用可能落在
 * 被折叠掉的历史里，用 `visibleMessages` 会让提示条时有时无。
 *
 * ## 急停
 *
 * 直接复用现有停止链路（`chatStore.stop` → `POST /v1/stop` → 核心
 * `cancel_task` + `reject_pending`）：它会把"正在等用户确认"的那个请求一并
 * 按拒绝处理，所以点了急停之后搭子**不会再自己往下做**。
 * 这里刻意不另开一条"急停专用"的后端通道 —— 两条路做同一件事，迟早会有一条
 * 忘了清理，而它们本来就该完全一致。
 */

import { Square } from 'lucide-react'

import { useChatStore } from '@/stores/chatStore'
import type { ChatMessage, ToolCallState } from '@/types'

/**
 * 电脑操作技能的名字前缀（与 core 的 `skill/builtin/computer.py` 一一对应）。
 *
 * ⚠️ 前端**只能靠名字前缀**识别这类技能：技能的 `tags` 没有随 `tool_call`
 * 事件传到前端。所以 core 侧以后新增电脑操作技能时**必须**沿用
 * `computer_` 前缀，否则提示条会漏掉它（而漏掉的表现是"用户以为搭子没在动"）。
 */
const COMPUTER_PREFIX = 'computer_'

/** 从后往前找最近一次**正在跑**的电脑操作。 */
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

  // 没有正在进行的电脑操作时**整个不渲染**：它平时不该占任何地方
  if (!tool) return null

  return (
    <div className="flex shrink-0 items-center gap-2 rounded-[12px] border border-line bg-panel px-3 py-2">
      {/* 呼吸点：让"它正在动"这件事看得出来（静态圆点会被当成装饰） */}
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
