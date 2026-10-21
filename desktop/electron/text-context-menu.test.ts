import { describe, expect, it, vi } from 'vitest'










vi.mock('electron', () => ({
  Menu: {
    buildFromTemplate: vi.fn(() => ({ popup: vi.fn() })),
  },
  clipboard: { writeText: vi.fn() },
  shell: { openExternal: vi.fn() },
}))

import {
  buildTextContextMenu,
  type TextContextMenuActions,
  type TextContextMenuParams,
} from './text-context-menu'


function params(overrides: Partial<TextContextMenuParams> = {}): TextContextMenuParams {
  return {
    isEditable: false,
    selectionText: '',
    linkURL: '',
    editFlags: {
      canUndo: true,
      canRedo: true,
      canCut: true,
      canCopy: true,
      canPaste: true,
      canSelectAll: true,
    },
    ...overrides,
  }
}

function actions(): TextContextMenuActions {
  return { openExternal: vi.fn(), copyText: vi.fn() }
}


function labels(items: ReturnType<typeof buildTextContextMenu>): string[] {
  return items.filter((item) => item.type !== 'separator').map((item) => String(item.label))
}

describe('buildTextContextMenu —— 作用域', () => {
  it('列表行那种情况（不可编辑、无选文、不是链接）→ 空数组，即不弹原生菜单', () => {
    
    
    expect(buildTextContextMenu(params(), actions())).toEqual([])
  })

  it('只有空白字符的选文也算"没有选文"（否则点一下列表行都会弹）', () => {
    expect(buildTextContextMenu(params({ selectionText: '   \n\t ' }), actions())).toEqual([])
  })

  it('可编辑时即使没有选文也要弹（输入框要能粘贴）', () => {
    const items = buildTextContextMenu(params({ isEditable: true }), actions())
    expect(labels(items)).toContain('粘贴')
  })
})

describe('buildTextContextMenu —— 可编辑的项', () => {
  it('凑齐 撤销/重做/剪切/复制/粘贴/全选 六个动作，且都用 role 走系统编辑链路', () => {
    const items = buildTextContextMenu(params({ isEditable: true }), actions())
    const roles = items.map((item) => item.role).filter(Boolean)
    expect(roles).toEqual(['undo', 'redo', 'cut', 'copy', 'paste', 'selectAll'])
    expect(labels(items)).toEqual(['撤销', '重做', '剪切', '复制', '粘贴', '全选'])
  })

  it('用 Chromium 给的 editFlags 决定灰不灰，而不是自己猜', () => {
    const items = buildTextContextMenu(
      params({
        isEditable: true,
        editFlags: {
          canUndo: false,
          canRedo: false,
          canCut: false,
          canCopy: false,
          canPaste: false,
          canSelectAll: false,
        },
      }),
      actions(),
    )
    expect(items.filter((item) => item.type !== 'separator').every((item) => item.enabled === false)).toBe(
      true,
    )
  })
})

describe('buildTextContextMenu —— 选文', () => {
  it('不可编辑但有选文 → 复制 / 全选', () => {
    const items = buildTextContextMenu(params({ selectionText: '搭子刚回答的一段话' }), actions())
    expect(labels(items)).toEqual(['复制', '全选'])
  })

  it('选文那一支**不该**出现剪切/粘贴（不可编辑的地方没有这两个动作）', () => {
    const items = buildTextContextMenu(params({ selectionText: '选中的字' }), actions())
    expect(labels(items)).not.toContain('剪切')
    expect(labels(items)).not.toContain('粘贴')
  })
})

describe('buildTextContextMenu —— 链接', () => {
  it('点在链接上 → 追加「在浏览器中打开链接」与「复制链接地址」', () => {
    const items = buildTextContextMenu(params({ linkURL: 'https://example.com/a' }), actions())
    expect(labels(items)).toEqual(['在浏览器中打开链接', '复制链接地址'])
  })

  it('「打开」走 openExternal、「复制」走剪贴板，不能被接错', () => {
    const act = actions()
    const items = buildTextContextMenu(params({ linkURL: 'https://example.com/b' }), act)
    const open = items.find((item) => item.label === '在浏览器中打开链接')
    const copy = items.find((item) => item.label === '复制链接地址')
    ;(open?.click as () => void)()
    ;(copy?.click as () => void)()
    expect(act.openExternal).toHaveBeenCalledWith('https://example.com/b')
    expect(act.copyText).toHaveBeenCalledWith('https://example.com/b')
  })

  it('输入框里的链接：两组都在，且中间有分隔线（不能粘成一坨）', () => {
    const items = buildTextContextMenu(
      params({ isEditable: true, linkURL: 'https://example.com/c' }),
      actions(),
    )
    expect(labels(items)).toEqual([
      '撤销',
      '重做',
      '剪切',
      '复制',
      '粘贴',
      '全选',
      '在浏览器中打开链接',
      '复制链接地址',
    ])
    expect(items.some((item) => item.type === 'separator')).toBe(true)
  })
})
