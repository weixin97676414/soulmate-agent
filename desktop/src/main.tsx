import { createRoot } from 'react-dom/client'

import App from '@/App'
// 公式（KaTeX）的样式必须排在 index.css **之前**：我们对它的覆盖（过宽时横向滚动、
// 深色主题下的对比度）写在 index.css 里，同优先级时后加载的胜出。
import 'katex/dist/katex.min.css'
import '@/index.css'
// 自定义鼠标指针（按皮肤生成，见 scripts/make-cursors.mjs）。
// ⚠️ 必须排在 index.css **之后**：它按 `[data-theme='x']` 定义每套皮肤的 `--cur-*`
// 变量，并给出"哪个区域用哪种指针"的全部规则。
import '@/cursors.css'

// 刻意不使用 StrictMode：它会重复执行 effect 与异步副作用，
// 而这里的流式对话、后端握手都是"只能跑一次"的副作用。
const container = document.getElementById('root')
if (!container) throw new Error('未找到 #root 挂载点')

createRoot(container).render(<App />)
