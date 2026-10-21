import {
  clipboard,
  Menu,
  shell,
  type BrowserWindow,
  type MenuItemConstructorOptions,
} from 'electron'





















































































export interface TextContextMenuParams {
  
  isEditable: boolean
  
  selectionText: string
  
  linkURL: string
  
  editFlags: {
    canUndo: boolean
    canRedo: boolean
    canCut: boolean
    canCopy: boolean
    canPaste: boolean
    canSelectAll: boolean
  }
}


export interface TextContextMenuActions {
  
  openExternal: (url: string) => void
  
  copyText: (text: string) => void
}














export function buildTextContextMenu(
  params: TextContextMenuParams,
  actions: TextContextMenuActions,
): MenuItemConstructorOptions[] {
  const items: MenuItemConstructorOptions[] = []

  if (params.isEditable) {
    items.push(
      { label: '撤销', role: 'undo', enabled: params.editFlags.canUndo },
      { label: '重做', role: 'redo', enabled: params.editFlags.canRedo },
      { type: 'separator' },
      { label: '剪切', role: 'cut', enabled: params.editFlags.canCut },
      { label: '复制', role: 'copy', enabled: params.editFlags.canCopy },
      { label: '粘贴', role: 'paste', enabled: params.editFlags.canPaste },
      { type: 'separator' },
      { label: '全选', role: 'selectAll', enabled: params.editFlags.canSelectAll },
    )
  } else if (params.selectionText.trim()) {
    
    
    
    items.push(
      { label: '复制', role: 'copy', enabled: params.editFlags.canCopy },
      { label: '全选', role: 'selectAll', enabled: params.editFlags.canSelectAll },
    )
  }

  if (params.linkURL) {
    if (items.length) items.push({ type: 'separator' })
    items.push(
      
      
      { label: '在浏览器中打开链接', click: () => actions.openExternal(params.linkURL) },
      { label: '复制链接地址', click: () => actions.copyText(params.linkURL) },
    )
  }

  return items
}







export function attachTextContextMenu(win: BrowserWindow): void {
  win.webContents.on('context-menu', (_event, params) => {
    const template = buildTextContextMenu(params, {
      openExternal: (url) => void shell.openExternal(url),
      copyText: (text) => clipboard.writeText(text),
    })
    
    if (template.length === 0) return
    Menu.buildFromTemplate(template).popup({ window: win })
  })
}
