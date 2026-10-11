/**
 * 语音命令目录 —— "说哪句话，就能干哪件事"。
 *
 * ## 这里只有"声明"，没有实现
 *
 * 每条命令的**实现**由真正渲染它的组件提供（见 `useVoiceCommand`）。
 * 「开始执行」那张计划卡片没出现在屏幕上，说它就不该有任何反应 ——
 * 所以这里只写"有这么个命令、默认叫什么词、属于哪一类"。
 *
 * ## 加上一条新命令要动的地方（就三处）
 *
 * 1. 这个数组里加一行；
 * 2. 在渲染那个按钮的组件里调一次 `useVoiceCommand(id, () => ...)`；
 * 3. 没了 —— 设置面板会自动列出它，命令词冲突校验也会自动带上它。
 *
 * ## 命令词为什么都这么短
 *
 * 命令词是**独立成句**说的（"确认"、"开始执行"），匹配也要求**整句相等**。
 * 不能用"包含"：那样"帮我确认一下这个文件"会直接批准一个危险操作。
 * 短，但精确。
 */

// ⚠️ 分组名「搭子」→「助手」。这个字符串会**直接渲染**在
// 语音设置面板里（见 VoicePanel 的 GROUP_NOTES 按名字取值），所以改它必须
// 连同 VoicePanel 的映射、buddy.new 的 group、以及下面 VOICE_COMMAND_GROUPS 一起改。
export type VoiceCommandGroup = '对话' | '导航' | '面板' | '助手' | '确认'

export interface VoiceCommandSpec {
  id: string
  /** 设置面板里显示的名字（说人话，不是动作 id） */
  label: string
  /** 出厂默认命令词；用户改过就用他的 */
  defaultWord: string
  group: VoiceCommandGroup
  /** 危险动作（会删东西、会真的开始执行）。设置面板要标出来，免得用户随手配个"好" */
  dangerous?: boolean
  hint?: string
}

export const VOICE_COMMANDS: VoiceCommandSpec[] = [
  // ---- 对话 ----
  {
    id: 'chat.stop',
    label: '停止生成',
    /*
      ⚠️ 默认词从「停下来」改成 **「停止」**（反馈："开始之后说
      停止也没用"）。

      他说的是"停止"，而这里写的是"停下来" —— 匹配又要求**整句相等**
      （见本文件顶部：用"包含"的话"帮我停下来看看"会误触发），于是字面差一个字
      就是不认。而这个词当时**在设置面板里根本找不到**（面板只列了"开启新对话"
      和"改一下"两条），所以他连改都改不了，只能一直以为功能坏了。

      两处都修了：默认词改成口语里更常说的「停止」；面板改成把**全表**列出来，
      以后任何一条命令的词都能自己改。

      （已改过这个词的用户不受影响 —— 用户改过的值优先于默认词。）
    */
    defaultWord: '停止',
    group: '对话',
    hint: '打断搭子正在说的话',
  },
  { id: 'chat.new', label: '开启新对话', defaultWord: '新对话', group: '对话' },
  {
    id: 'chat.continue',
    label: '接着说',
    defaultWord: '接着说',
    group: '对话',
    hint: '回答没跑完时，让它把剩下的做完',
  },

  // ---- 导航 ----
  { id: 'nav.chat', label: '回到对话', defaultWord: '回到对话', group: '导航' },
  { id: 'nav.groups', label: '打开群聊', defaultWord: '打开群聊', group: '导航' },
  { id: 'nav.tasks', label: '打开任务', defaultWord: '打开任务', group: '导航' },
  { id: 'nav.appearance', label: '打开外观', defaultWord: '打开外观', group: '导航' },
  /*
    ⚠️ 「打开设置」**删除**（设置页本身取消，`'settings'` 这个 view 已不存在）。
    下面八条是原设置页里那八栏各自的入口 —— 它们现在在左栏是顶级页面，语音也就各给一条。
    默认说法沿用「打开X」句式（与上面「打开群聊 / 打开外观」一致），用户在面板里可以改。
  */
  { id: 'nav.models', label: '打开模型', defaultWord: '打开模型', group: '导航' },
  { id: 'nav.skills', label: '打开技能', defaultWord: '打开技能', group: '导航' },
  { id: 'nav.mcp', label: '打开 MCP', defaultWord: '打开 MCP', group: '导航' },
  { id: 'nav.workspace', label: '打开产物', defaultWord: '打开产物', group: '导航' },
  { id: 'nav.usage', label: '打开消耗', defaultWord: '打开消耗', group: '导航' },
  { id: 'nav.calendar', label: '打开日历', defaultWord: '打开日历', group: '导航' },
  { id: 'nav.audit', label: '打开日志', defaultWord: '打开日志', group: '导航' },
  { id: 'nav.preference', label: '打开安全', defaultWord: '打开安全', group: '导航' },
  {
    id: 'nav.benefits',
    // ⚠️ 说法改过：左栏那个入口早就叫「社区」了，命令词却还停在
    // 旧名字（"权益"）上 —— 用户照着界面念，是念不出来的。
    label: '打开社区',
    defaultWord: '打开社区',
    group: '导航',
    hint: '打开社区页面',
  },
  {
    id: 'nav.about',
    // ⚠️ 说法改过：与上面几条统一成「打开X」句式；而且旧说法
    // 听起来只值一个版本号，实际打开的是整个关于页。
    label: '打开关于',
    defaultWord: '打开关于',
    group: '导航',
    hint: '打开关于页面（版本号与更新记录）',
  },
  {
    // 这一条和上面几条不一样：反馈是**弹窗**，不是页面（ViewKey 里没有 feedback），
    // 所以它的实现是 openFeedback()。单独占一个 `action.` 前缀，免得以后有人
    // 照着 `nav.*` 的写法把它当页面切过去（那个 view 值并不存在）。
    id: 'action.feedback',
    // ⚠️ 说法改过，与同组统一成「打开X」句式。
    label: '打开反馈',
    defaultWord: '打开反馈',
    group: '导航',
    hint: '打开反馈窗口',
  },
  {
    /*
      「添加技能」：同样是弹窗、同样不走 setView。

      ⚠️ 这条命令是"任何页面都能用"的（产品要求）。所以那个弹层
      被提出了技能页 —— 原先它只是技能页里一个组件内部的 state，在你正看着群聊
      或任务页时说了也没用（`useVoiceCommand` 的实现只存在于挂载它的组件里）。
    */
    id: 'action.addSkill',
    label: '添加技能',
    defaultWord: '添加技能',
    group: '导航',
    hint: '打开「添加技能」弹窗（上传技能包 / 导入文件夹）',
  },
  {
    /*
      「关闭弹窗」关的是**应用自己弹的浮层** —— 反馈、添加技能这类。

      ⚠️ 它**故意不管**搭子发起的那两类：权限确认弹窗（`ConfirmDialog`）与
      任务计划卡片（`PlanCard`）。那两个是在问"允不允许执行" —— 随口一句
      "关闭弹窗"就把它们关掉，等于用一个含糊的词驳回了一次高危操作；
      而要驳回，本来就有「拒绝执行」这条精确得多的命令（见下面「确认」组）。

      ⚠️ 这条命令**只在真有弹窗时才出现**（见 App.tsx 的注册点传 `null` 的分支）：
      没有弹窗可关的时候它还挂在面板里，用户说了没反应，就变成"这功能坏了"。
    */
    id: 'action.closeDialog',
    label: '关闭弹窗',
    defaultWord: '关闭弹窗',
    group: '导航',
    hint: '关掉当前打开的弹窗（反馈 / 添加技能这类）',
  },

  // ---- 面板 ----
  {
    id: 'panel.drawer',
    label: '看执行链路',
    defaultWord: '看执行链路',
    group: '面板',
    hint: '打开右侧的任务详情抽屉',
  },
  {
    // ⚠️ 与上一条成对（报"只有看执行链路，没有关闭执行链路"）。
    // 拆成**定向**命令而不是让它 toggle：说"关闭"的时候抽屉本来就开着，toggle 会把它
    // 再开一次，用户只会认为识别错了（助手栏那两条踩过同一个坑，见 lib/collapse.ts）。
    id: 'panel.drawerClose',
    label: '关闭执行链路',
    defaultWord: '关闭执行链路',
    group: '面板',
    hint: '收起右侧的任务详情抽屉',
  },
  /*
    ⚠️ 收起 / 展开是**两条命令**，但作用在同一个开关上（见 lib/collapse.ts 的
    setCollapsed）。以前只有"收起"这一条，而它的实现是 toggle —— 于是
    "说收起"在已经收起时反而会把栏**弹出来**，用户看到的就是"只有收起没有展开"，
    甚至怀疑识别错了。拆成两条定向命令之后，说什么就是什么。
  */
  // ⚠️ 「搭子栏」→「助手栏」。三条命令的**默认说法**也跟着换，
  // 否则面板里写着"助手栏"、让用户说的却是"收起搭子栏"，对不上。
  // 已经自己改过命令词的用户不受影响（commandWord() 里 overrides 优先）。
  {
    id: 'panel.assistantRail',
    label: '折叠助手栏',
    defaultWord: '折叠助手栏',
    group: '面板',
    hint: '把左侧助手栏收起来',
  },
  {
    id: 'panel.assistantRailExpand',
    label: '展开助手栏',
    defaultWord: '展开助手栏',
    group: '面板',
    hint: '把收起的助手栏放出来',
  },
  {
    id: 'panel.sessionRail',
    // ⚠️ 「折叠对话表」是的原话（确认过"没漏字"）——
    // 不要擅自补成"折叠对话列表"。
    label: '折叠对话表',
    defaultWord: '折叠对话表',
    group: '面板',
    hint: '把左侧对话列表收起来',
  },
  {
    id: 'panel.sessionRailExpand',
    // ⚠️ 与上面那条"折叠对话表"配套：收/放两条措辞要一致，
    // 否则面板里一条叫"对话表"一条叫"对话列表"，用户会以为是两样东西。
    label: '展开对话表',
    defaultWord: '展开对话表',
    group: '面板',
    hint: '把收起的对话表放出来',
  },
  /*
    ---- 群聊页的两栏----

    群聊页与单聊的"对话表 / 助手栏"是**两套不同的栏**（群聊有自己的一份），
    所以单聊那两条 `panel.sessionRail*` / `panel.assistantRail*` 管不到这里，
    必须各配一组。

    ⚠️ 命名照用户原话：「群聊对话表」= 群聊页中间那栏对话列表；
    「群聊名称栏」= 最左边那栏群列表（用户确认过就是它）。

    ⚠️ 四条命令只在**群聊页挂载时**注册（见 GroupChatPage），离开页面即失效——
    与其它面板命令同一套规则：界面上没有那一栏，说了也不该有反应。
  */
  {
    id: 'panel.groupThreads',
    label: '折叠群聊对话表',
    defaultWord: '折叠群聊对话表',
    group: '面板',
    hint: '把群聊页中间的对话列表收起来',
  },
  {
    id: 'panel.groupThreadsExpand',
    label: '展开群聊对话表',
    defaultWord: '展开群聊对话表',
    group: '面板',
    hint: '把收起的群聊对话列表放出来',
  },
  {
    id: 'panel.groupList',
    label: '折叠群聊名称栏',
    defaultWord: '折叠群聊名称栏',
    group: '面板',
    hint: '把群聊页最左边的群列表收起来',
  },
  {
    id: 'panel.groupListExpand',
    label: '展开群聊名称栏',
    defaultWord: '展开群聊名称栏',
    group: '面板',
    hint: '把收起的群列表放出来',
  },

  // ---- 助手 ----
  { id: 'buddy.new', label: '新建助手', defaultWord: '新建助手', group: '助手' },

  // ---- 确认（最该用语音的一类：手正忙着，点不到那个按钮）----
  {
    id: 'plan.approve',
    label: '计划：开始执行',
    defaultWord: '开始执行',
    group: '确认',
    dangerous: true,
    hint: '让 AI 把它刚拟的任务计划真正跑起来',
  },
  { id: 'plan.revise', label: '计划：改一下', defaultWord: '改一下', group: '确认' },
  { id: 'plan.abort', label: '计划：不用了', defaultWord: '不用了', group: '确认' },
  {
    id: 'confirm.allow',
    label: '批准高危操作',
    defaultWord: '允许执行',
    group: '确认',
    dangerous: true,
    hint: '等价于点确认弹窗上的「允许执行」',
  },
  { id: 'confirm.reject', label: '拒绝高危操作', defaultWord: '拒绝执行', group: '确认' },
]

/** 按分组排好序的目录（设置面板直接按这个渲染）。 */
export const VOICE_COMMAND_GROUPS: VoiceCommandGroup[] = [
  '对话',
  '导航',
  '面板',
  '助手',
  '确认',
]

/** 动作 id → 声明，便于反查。 */
export const VOICE_COMMAND_BY_ID: Record<string, VoiceCommandSpec> = Object.fromEntries(
  VOICE_COMMANDS.map((item) => [item.id, item]),
)

/** 某条命令**当前生效**的命令词（用户改过的优先，空串视为没改）。 */
export function commandWord(spec: VoiceCommandSpec, overrides: Record<string, string>): string {
  return (overrides?.[spec.id] ?? '').trim() || spec.defaultWord
}
