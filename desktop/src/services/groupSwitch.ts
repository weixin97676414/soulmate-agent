/**
 * 切到某个群 —— **鼠标点击与语音喊名字走同一条路**。
 *
 * 这是 `assistantSwitch.ts` 的群版本，产品要求"语音也要能唤醒群"，
 * 而且明确"**切换规则和切换搭子时是相同的**"。所以在群里照抄那边的一条铁律：
 * 两条入口（点击 / 喊名字）调同一个函数，行为不可能分叉。
 *
 * ## 为什么单独一个文件，不与 `assistantSwitch` 合并
 *
 * 它们要读改的 store 完全不同（那边是 `assistantStore` + `chatStore`，
 * 这边是 `groupStore` + `appStore` 的 `view`）。合在一起就得在一个文件里
 * 同时 import 四个 store，而"群"和"搭子"除了"都是唤醒目标"之外没有任何
 * 共同操作 —— 那种合并只会让两边都变慢才读懂。
 *
 * 但**语义**是刻意对齐的，改一边时记得看另一边。
 */

import { useAppStore } from '@/stores/appStore'
import { useGroupStore } from '@/stores/groupStore'

/**
 * 切到 `groupId` 这个群，并落到它的对话上。
 *
 * 落点规则与鼠标点击**完全一致**（`GroupChatPage` 的群列表项也调它）：
 * 进群后打开该群"最近有动静"的那条对话；一条都没有时后端会先建一条，
 * 所以界面不需要处理空态。
 *
 * ⚠️ `setView('groups')` 必须在前面：用户喊完要**立刻**看到群聊页。只调
 * `selectGroup` 的话它只写 store、不换页 —— 用户当时如果停在设置页，
 * 屏幕上什么都不会变，他只会觉得"喊了没反应"。
 *
 * ⚠️ `selectGroup` 内部会先拉群清单/对话列表再进第一条对话，是异步的。
 * 这里**刻意不等它**（返回 `void`）：等待没有任何用处 —— 调用方（语音状态机）
 * 接下来要做的是"进入录音态"，而那件事与群数据是否加载完无关；
 * 而把 `await` 传下去，采集回调就会被拖在这里、后续音频分块堆在队列里。
 */
export function switchGroup(groupId: string): void {
  useAppStore.getState().setView('groups')
  void useGroupStore.getState().selectGroup(groupId)
}
