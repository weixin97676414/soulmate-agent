/**
 * 技能导入相关的共享常量与文案。
 *
 * ⚠️ 为什么单独一个文件：这套东西现在有**两个**使用者 —— 技能页（列表、详情里
 * 显示来源标签）和「添加技能」弹窗（`components/AddSkillDialog.tsx`，它挂在应用
 * 顶层、任何页面都能唤起）。放在技能页里再让弹窗去 import 技能页，会绕成一个环
 * （技能页也要用弹窗里的 `openAddSkill`）。所以提到这个中立的小模块。
 */

/**
 * 技能包的**来源格式**标签。
 *
 * 后端判定（见 `core/src/my_agent/skill/formats.py`），界面只负责显示 ——
 * 用户拿到一张技能卡时，第一件事就是想知道"这是哪种技能"。
 */
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

/** 上传时允许选的扩展名。后端还按**内容**兜底识别，这里只是给文件框一个合理过滤 */
export const PACKAGE_ACCEPT =
  '.zip,.tar.gz,.tgz,.tar,.md,.txt,.json,.yaml,.yml,.mdc,.cursorrules,application/zip,application/gzip,application/json,text/markdown'

/**
 * 「添加技能」弹层里每个选项的样式。
 *
 * 两点刻意为之：整块可点（弹层里唯一要做的事就是选一个，不该逼用户瞄准那两个字）；
 * 焦点环必须可见（键盘用户的唯一线索，`outline-none` 只在有 ring 替代时才允许）。
 */
export const OPTION_BUTTON_CLASS =
  'flex w-full items-start gap-3 rounded-[10px] border border-line bg-canvas px-3.5 py-3 text-left transition-colors hover:border-brand/50 focus-visible:ring-2 focus-visible:ring-brand/40 focus-visible:outline-none'

export function sourceLabel(format?: string): string {
  if (!format) return ''
  return SOURCE_FORMAT_LABELS[format] ?? format
}
