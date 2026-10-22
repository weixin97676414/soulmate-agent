
import { beforeEach, describe, expect, it } from 'vitest'

import { useChatStore } from '@/stores/chatStore'








describe('群聊交互入队 setInteraction', () => {
  beforeEach(() => {
    useChatStore.setState({ interactions: [], interaction: null })
  })

  it('群聊 interaction_request 入队，并拍平群来源字段', () => {
    useChatStore.getState().setInteraction({
      request_id: 'r1',
      skill_name: 'ask_choice',
      display_name: '请你确认一下',
      kind: 'choice',
      payload: {
        question: '你想用哪个方案？',
        options: [
          { label: '方案 A', description: '' },
          { label: '方案 B', description: '' },
        ],
        allow_custom: true,
      },
      group_id: 'g1',
      group_name: '项目群',
      assistant_id: 'a1',
      assistant_name: '小助',
    })

    const state = useChatStore.getState()
    expect(state.interactions).toHaveLength(1)
    expect(state.interaction?.requestId).toBe('r1')
    expect(state.interaction?.kind).toBe('choice')
    expect(state.interaction?.question).toBe('你想用哪个方案？')
    expect(state.interaction?.groupId).toBe('g1')
    expect(state.interaction?.groupName).toBe('项目群')
    expect(state.interaction?.assistantName).toBe('小助')
  })

  it('敏感输入同样入队（kind 拍成 secret）', () => {
    useChatStore.getState().setInteraction({
      request_id: 'r2',
      skill_name: 'request_secret',
      kind: 'secret',
      payload: {
        reason: '需要一个 API Key',
        fields: [{ name: 'api_key', label: 'API Key', hint: '', multiline: false }],
      },
      group_id: 'g1',
      group_name: '项目群',
      assistant_name: '小助',
    })

    const state = useChatStore.getState()
    expect(state.interaction?.kind).toBe('secret')
    expect(state.interaction?.fields).toHaveLength(1)
    expect(state.interaction?.assistantName).toBe('小助')
  })

  it('setInteraction(null) 清队首', () => {
    useChatStore.getState().setInteraction({ request_id: 'r1', kind: 'choice' })
    expect(useChatStore.getState().interaction).not.toBeNull()

    useChatStore.getState().setInteraction(null)
    expect(useChatStore.getState().interaction).toBeNull()
    expect(useChatStore.getState().interactions).toHaveLength(0)
  })
})
