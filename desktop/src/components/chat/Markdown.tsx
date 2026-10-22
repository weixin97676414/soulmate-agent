import { Check, Copy } from 'lucide-react'
import { memo, useRef, useState, type ReactNode } from 'react'
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown'
import rehypeHighlight from 'rehype-highlight'
import rehypeKatex from 'rehype-katex'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'

import { MarkdownImage, isLocalImagePath } from '@/components/chat/MarkdownImage'
import { remarkLineBreaks } from '@/lib/remarkLineBreaks'











function transformUrl(url: string, key: string): string {
  if (key === 'src' && (isLocalImagePath(url) || url.startsWith('data:image/'))) return url
  return defaultUrlTransform(url)
}


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
