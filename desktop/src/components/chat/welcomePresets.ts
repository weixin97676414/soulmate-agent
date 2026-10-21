import type { AssistantProfile } from '@/types'






























export interface WelcomePreset {
  
  label: string
  
  template: string
}


export const WELCOME_PRESETS: Record<string, WelcomePreset[]> = {
  BuddyManager: [
    {
      label: '搭子助手',
      template: '我需要一个搭子助手，你给我一个完整模板我来填写',
    },
    {
      label: '搭子团队',
      template: '我需要一个干活的团队，你给我一个完整模版我来填写',
    },
    {
      label: '搭子辩论',
      template: '我需要一个辩论群，来围绕一个话题做辩论，你给我一个完整模版我来填写',
    },
  ],
  soulmate: [
    {
      label: '首次邂逅',
      template: '我们第一次相遇，我需要给你提供什么，才能让你使用完整的功能？',
    },
    {
      label: '补充信息',
      template: '我现在需要补充关于我的信息，你看看我哪里需要补充？',
    },
    {
      label: '当下建议',
      template: '根据我的情况，给我一份近期+今天+当下的可执行建议，要写清时间区间',
    },
  ],
  LoveBuddy: [
    {
      label: '首次使用',
      template: '我第一次使用你，我需要给你提供什么，才能让你使用完整的功能？',
    },
    {
      label: '情感档案',
      template: '记录一份与我情感相关的某个人的档案，给我一个完整模版我来填写',
    },
    {
      label: '查看记录',
      template: '我现在需要查某个人的档案记录，把所有档案记录的人物做一份列表给我',
    },
  ],
  RelationBuddy: [
    {
      label: '首次使用',
      template: '我第一次使用你，我需要给你提供什么，才能让你使用完整的功能？',
    },
    {
      label: '社交档案',
      template: '记录一份与我人际关系相关的某个人的档案，给我一个完整模版我来填写',
    },
    {
      label: '查看记录',
      template: '我现在需要查某个人的档案记录，把所有档案记录的人物做一份列表给我',
    },
  ],
  
  
  FortuneTellingBuddy: [
    {
      label: '首次使用',
      template:
        '我第一次使用你，给我详细说说八字、占星、梅花、塔罗使用的时候都需要我提供什么以及需要注意什么？',
    },
    {
      label: '近期运势',
      template: '我希望你能帮我分析下我的近期运势，我需要给你提供什么信息？',
    },
    {
      label: '事件预测',
      template: '我想请你帮我占卜预测一件事，需要我提供给你什么以及需要注意些什么？',
    },
  ],
}








export function welcomePresetsFor(
  assistant: Pick<AssistantProfile, 'id' | 'builtin'> | undefined,
): WelcomePreset[] {
  if (!assistant?.builtin) return []
  return WELCOME_PRESETS[assistant.id] ?? []
}
