














export const SOURCE_FORMAT_LABELS: Record<string, string> = {
  'claude-skill': 'Claude 技能',
  'skill-json': '声明式技能',
  'cursor-mdc': 'Cursor 规则',
  cursorrules: 'Cursor 规则',
  clinerules: 'Cline 规则',
  'agents-md': '项目规则',
  'plain-md': '提示词文档',
  'mcp-json': 'MCP 配置',
  script: '脚本',
  folder: '本机文件夹',
  manual: '手动创建',
}


export const PACKAGE_ACCEPT =
  '.zip,.tar.gz,.tgz,.tar,.md,.txt,.json,.yaml,.yml,.mdc,.cursorrules,application/zip,application/gzip,application/json,text/markdown'







export const OPTION_BUTTON_CLASS =
  'flex w-full items-start gap-3 rounded-[10px] border border-line bg-canvas px-3.5 py-3 text-left transition-colors hover:border-brand/50 focus-visible:ring-2 focus-visible:ring-brand/40 focus-visible:outline-none'

export function sourceLabel(format?: string): string {
  if (!format) return ''
  return SOURCE_FORMAT_LABELS[format] ?? format
}
