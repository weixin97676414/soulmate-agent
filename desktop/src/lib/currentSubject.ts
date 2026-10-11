import { useAppStore } from '@/stores/appStore'
import { useGroupStore } from '@/stores/groupStore'
import type { GroupProfile } from '@/types'

/**
 * 「当前主体」—— 用户此刻在看的那个东西：一个**群**，还是一个**搭子**。
 *
 * 这个判定从 （群聊也能语音唤醒）起变得有用了：界面与语音都开始需要
 * 知道"眼前是群还是搭子"，而且**判得不一样会出很微妙的问题**——
 *
 * · 左上角标题栏显示群名，语音设置面板却在配那个搭子的唤醒词；
 * · 语音面板说"只对这个群生效"，实际写进了搭子的档案。
 *
 * 所以判据只能有一份。放进 `lib/` 而不是某个 store：它同时要读 `appStore`
 * 的 `view` 与 `groupStore` 的数据，塞进任一个 store 都会引入互相 import。
 */

/**
 * 当前处在"群上下文"里吗？
 *
 * 两个来源，**缺一不可**：
 *
 * 1. 主窗口停在群聊页（`view === 'groups'`）；
 * 2. **群聊独立窗口**（`mode === 'group'`）—— 只读观察窗与可操作窗口共用这一种
 *    窗口类型。那种窗口里根本没有"页面"这个概念（`view` 还是它启动时的旧值），
 *    它天生就是那个群，所以不能拿 `view` 去判。
 *
 * ⚠️ 不看页面、只看"有没有选中群"是不行的：`groupStore.selectedId` 是**粘性**的
 * —— 用户去过群聊页之后它就一直是那个群，哪怕他现在停在设置页。
 */
export function inGroupContext(view: string): boolean {
  return view === 'groups' || window.agentBridge?.getWindowArgs?.()?.mode === 'group'
}

/**
 * 当前主体所在的群；不在群上下文里时是 `undefined`（调用方据此回落到搭子）。
 *
 * ⚠️ 独立窗口那边靠的是 `GroupChatPage` 启动时调的 `selectGroup(groupId)`
 * 把 `selectedId` 固定下来 —— 所以这里直接取即可，不必自己解析启动参数。
 */
export function useCurrentGroup(): GroupProfile | undefined {
  const view = useAppStore((state) => state.view)
  const group = useGroupStore((state) =>
    state.groups.find((item) => item.id === state.selectedId),
  )
  return inGroupContext(view) ? group : undefined
}
