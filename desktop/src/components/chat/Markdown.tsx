import { Check, Copy } from 'lucide-react'
import { memo, useRef, useState, type ReactNode } from 'react'
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown'
import rehypeHighlight from 'rehype-highlight'
import rehypeKatex from 'rehype-katex'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'

import { MarkdownImage, isLocalImagePath } from '@/components/chat/MarkdownImage'
import { remarkLineBreaks } from '@/lib/remarkLineBreaks'

/**
 * 图片地址的放行规则。
 *
 * react-markdown 默认只放行 http/https/mailto 等协议，**会把本机路径
 * （`D:\图片\a.png`、`file:///D:/a.png`）与 `data:` 图片一起清成空串** ——
 * 这正是"对话里贴本地图必然破图"的直接原因（`src` 变空）。
 *
 * 这里只为**图片地址**（`src`）放开本机路径与 `data:image/`；链接（`href`）继续走默认策略，
 * 所以 `javascript:` 之类仍然会被清掉 —— 放开的范围刚好是"能显示一张图"，不是"能跳任意协议"。
 */
function transformUrl(url: string, key: string): string {
  if (key === 'src' && (isLocalImagePath(url) || url.startsWith('data:image/'))) return url
  return defaultUrlTransform(url)
}

/** 代码块：右上角常驻复制按钮 */
function CodeBlock({ children }: { children?: ReactNode }) {
  const ref = useRef<HTMLPreElement>(null)
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    const text = ref.current?.innerText ?? ''
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      // 剪贴板不可用时静默失败，不打断阅读
    }
  }

  return (
    <div className="group relative">
      <pre ref={ref}>{children}</pre>
      <button
        type="button"
        onClick={() => void copy()}
        className="absolute top-2 right-2 flex items-center gap-1 rounded-[6px] border border-line bg-canvas px-1.5 py-0.5 text-[11px] text-ink-soft opacity-0 transition-opacity group-hover:opacity-100 hover:text-ink"
      >
        {copied ? <Check size={11} /> : <Copy size={11} />}
        {copied ? '已复制' : '复制'}
      </button>
    </div>
  )
}

/**
 * Markdown 渲染。
 *
 * 用 memo 按 content 缓存：流式输出时每个动画帧都会调用，但只有内容真正
 * 变化时才重新解析 Markdown，避免无谓的重排。
 *
 * 插件链的顺序都不是随手排的：
 * - `remarkMath` 必须在 `remarkLineBreaks` **之前**：先把 `$...$` 收成 math 节点，
 *   剩下的文本换行才是后者要处理的（详见 lib/remarkLineBreaks.ts 的说明）。
 * - `rehypeKatex` 在 `rehypeHighlight` 之前：先把公式渲染成 DOM，再让代码高亮去
 *   扫代码块 —— 高亮没必要去看公式的产物。
 * - `rehypeKatex` 显式给 `throwOnError: false`：模型写出非法公式时，红字标出那一处
 *   即可，绝不能因为一行 LaTeX 写错就让整条消息渲染失败。
 *
 * `compact`：给小字号、窄容器的场景用（搭子简介那几处）。它只多加一个修饰
 * 类，样式在 index.css 的 `.md-compact` 里 —— **刻意不去改 `.md-body`**，
 * 那个类管着所有聊天气泡。它只做一件事：把标题与段距压到正文尺度
 * （简介是 11~12px 的小字）。
 * 这里曾用 `white-space: pre-wrap` 实现"单个换行也断行"，已撤掉：那会把松列表
 * 撑出一堆空白（原因写在 remarkLineBreaks.ts 顶部），现在换行由插件统一负责。
 */
export const Markdown = memo(function Markdown({
  content,
  compact = false,
}: {
  content: string
  compact?: boolean
}) {
  return (
    <div className={compact ? 'md-body md-compact' : 'md-body'}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath, remarkLineBreaks]}
        rehypePlugins={[
          [rehypeKatex, { throwOnError: false }],
          [rehypeHighlight, { detect: true, ignoreMissing: true }],
        ]}
        urlTransform={transformUrl}
        components={{
          // 链接一律交给系统浏览器打开，应用内不做任意页面跳转
          a: ({ href, children }) => (
            <a
              href={href}
              onClick={(event) => {
                event.preventDefault()
                if (href) void window.agentBridge.openExternal(href)
              }}
            >
              {children}
            </a>
          ),
          pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
          // 图片分两类加载（外链直连、本机路径走核心代理），失败时给出可读原因
          img: ({ src, alt }) => (
            <MarkdownImage
              src={typeof src === 'string' ? src : ''}
              alt={typeof alt === 'string' ? alt : ''}
            />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
})
