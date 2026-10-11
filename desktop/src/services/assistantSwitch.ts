/**
 * 切到另一个搭子 —— **鼠标点击与语音喊名字走同一条路**。
 *
 * ## 为什么要单独一个文件
 *
 * 这两条路以前是**各写各的**，而且行为不一样：
 *
 * - 鼠标点击（`AssistantRail.switchTo`）：切过去之后**加载那个搭子最近一次会话**，
 *   没有会话才开新的。这正是用户期望的"与另一个搭子开始对话"。
 * - 语音喊名字（`voiceSessionStore.switchToAssistant`）：只改了当前搭子、
 *   把页面拉回对话页，**没有动会话**。
 *
 * 后果是"用嘴切搭子"和"用鼠标切搭子"看起来是两件事 —— 实测反馈就是这个：
 * 喊了一句名字，当前这条对话**还是上一个搭子的**，内容对不上人。
 *
 * 所以抽到一处、两边都调它。以后再加第三条入口（快捷键、托盘）也不会走歪。
 *
 * ## 为什么不放进某个 store
 *
 * 它要同时读改 `assistantStore` 与 `chatStore`。放进任一个 store 都会引入
 * store 之间的相互 import —— 那类循环依赖在打包后表现为"某个 store 是 undefined"，
 * 而且只在特定引入顺序下出现，很难查。放这里两个都只单向依赖。
 */

import { useAppStore } from '@/stores/appStore'
import { useAssistantStore } from '@/stores/assistantStore'
import { useChatStore } from '@/stores/chatStore'

/**
 * 切到 `assistantId` 这个搭子，并落到它的会话上。
 *
 * 落点规则（产品要求，**与鼠标点击完全一致**）：
 * 切过去之后默认打开该搭子**最近一次对话**；它还没有任何对话则开一个新对话。
 *
 * ⚠️ `setActive` 而不是直接改 `activeId`：它会把 `picked` 置位（"这是用户主动选的"），
 * 而点击与喊名字**都是**主动选择 —— 直接改 state 会让后续的自动落位逻辑
 * 把用户刚选中的搭子又换掉。
 */
export function switchAssistant(assistantId: string): void {
  // 切搭子必须**一起回到对话页**（在群聊页喊搭子唤醒词，
  // 主体确实换了，但页面还停在群聊页 —— 看起来像"没反应"）。
  //
  // 群那一侧一直有这一步（见 `groupSwitch` 的 `setView('groups')`），这里漏了；
  // 而本文件开头的注释其实**早就写着**"把页面拉回对话页" —— 只是没实现。
  useAppStore.getState().setView('chat')

  const { activeId, setActive } = useAssistantStore.getState()
  if (activeId !== assistantId) setActive(assistantId)

  const { sessions, selectSession, startNewSession } = useChatStore.getState()
  const latest = sessions
    .filter((session) => session.assistant_id === assistantId)
    .sort((a, b) => b.updated_at - a.updated_at)[0]

  if (latest) void selectSession(latest.id)
  else startNewSession()
}
