
























export type VoiceCommandGroup = '对话' | '导航' | '面板' | '助手' | '确认'

export interface VoiceCommandSpec {
  id: string
  
  label: string
  
  defaultWord: string
  group: VoiceCommandGroup
  
  dangerous?: boolean
  hint?: string
}

export const VOICE_COMMANDS: VoiceCommandSpec[] = [
  
  {
    id: 'chat.stop',
    label: '停止生成',
    













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

  
  { id: 'nav.chat', label: '回到对话', defaultWord: '回到对话', group: '导航' },
  { id: 'nav.groups', label: '打开群聊', defaultWord: '打开群聊', group: '导航' },
  { id: 'nav.tasks', label: '打开任务', defaultWord: '打开任务', group: '导航' },
  { id: 'nav.appearance', label: '打开外观', defaultWord: '打开外观', group: '导航' },
  




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
    
    
    label: '打开社区',
    defaultWord: '打开社区',
    group: '导航',
    hint: '打开社区页面',
  },
  {
    id: 'nav.about',
    
    
    label: '打开关于',
    defaultWord: '打开关于',
    group: '导航',
    hint: '打开关于页面（版本号与更新记录）',
  },
  {
    
    
    
    id: 'action.feedback',
    
    label: '打开反馈',
    defaultWord: '打开反馈',
    group: '导航',
    hint: '打开反馈窗口',
  },
  {
    






    id: 'action.addSkill',
    label: '添加技能',
    defaultWord: '添加技能',
    group: '导航',
    hint: '打开「添加技能」弹窗（上传技能包 / 导入文件夹）',
  },
  {
    










    id: 'action.closeDialog',
    label: '关闭弹窗',
    defaultWord: '关闭弹窗',
    group: '导航',
    hint: '关掉当前打开的弹窗（反馈 / 添加技能这类）',
  },

  
  {
    
    
    
    id: 'panel.drawer',
    label: '打开执行链路',
    defaultWord: '打开执行链路',
    group: '面板',
    hint: '打开右侧的任务详情抽屉',
  },
  {
    
    
    
    id: 'panel.drawerClose',
    label: '关闭执行链路',
    defaultWord: '关闭执行链路',
    group: '面板',
    hint: '收起右侧的任务详情抽屉',
  },
  





  
  
  
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
    
    
    label: '折叠对话表',
    defaultWord: '折叠对话表',
    group: '面板',
    hint: '把左侧对话列表收起来',
  },
  {
    id: 'panel.sessionRailExpand',
    
    
    label: '展开对话表',
    defaultWord: '展开对话表',
    group: '面板',
    hint: '把收起的对话表放出来',
  },
  












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

  
  { id: 'buddy.new', label: '新建助手', defaultWord: '新建助手', group: '助手' },

  
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


export const VOICE_COMMAND_GROUPS: VoiceCommandGroup[] = [
  '对话',
  '导航',
  '面板',
  '助手',
  '确认',
]


export const VOICE_COMMAND_BY_ID: Record<string, VoiceCommandSpec> = Object.fromEntries(
  VOICE_COMMANDS.map((item) => [item.id, item]),
)


export function commandWord(spec: VoiceCommandSpec, overrides: Record<string, string>): string {
  return (overrides?.[spec.id] ?? '').trim() || spec.defaultWord
}
