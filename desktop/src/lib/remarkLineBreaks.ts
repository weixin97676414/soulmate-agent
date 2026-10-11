/**
 * 把**段落内**的单个换行渲染成真正的换行。
 *
 * ## 要解决的问题
 *
 * Markdown 语义里，段落内的单个换行等于一个空格（要空行才换段）。模型却经常把并列信息
 * 写成多行**而不空行** —— 「名称：X」「时间：Y」这样连着写下来，渲染时就被连成一行。
 * 用户看到的是"我明明分了行，它却挤在一起"。
 *
 * ## 为什么不用 CSS（`white-space: pre-wrap`）
 *
 * 搭子简介那处最早就是这么绕过去的（为了不引 `remark-breaks` 依赖，改用 CSS 的 pre-wrap）。
 * 但它**不能**推广到聊天气泡：`mdast-util-to-hast` 会给**松列表**（条目之间有空行 ——
 * 模型写多行 TODO 时非常常见）的每个 `<li>` 里插进纯 `\n` 文本节点
 * （见它的 `lib/handlers/list-item.js`），`pre-wrap` 会把那些 `\n` 变成**真实空行**，
 * 列表被撑出一堆空白。所以简介那处的 pre-wrap 已随本插件一起撤掉。
 *
 * ## 为什么放在这里
 *
 * 本插件跑在 **mdast 阶段**，早于上面那次插入，而且只动**文本节点内部**的换行：
 * 松列表、代码块（换行的内容存在 `value` 上、不是子节点里的文本）、表格都不受影响。
 * 效果等价 `remark-breaks`，但不必为此新增依赖（本项目的口径）。
 *
 * ## 顺序
 *
 * 必须排在 `remark-math` **之后**：先把 `$...$` 交给 math 收走，剩下的文本换行才是要处理的。
 * 排前面也不会拆坏公式（下面的 `VERBATIM` 兜着），但排后面语义更清楚。
 */

type MdNode = { type: string; value?: string; children?: MdNode[] }

/** 这些节点的换行必须原样保留 —— 内容在 `value` 上，不是子节点里的文本 */
const VERBATIM = new Set(['code', 'inlineCode', 'html', 'yaml', 'toml', 'math', 'inlineMath'])

export function remarkLineBreaks() {
  // 参数标成 unknown 而不是导入 mdast 的类型：`@types/mdast` 只是 react-markdown 的
  // 传递依赖，本项目没有声明它 —— 从传递依赖里拿类型，等于给将来埋一个"某次升级后
  // 类型忽然找不到"的坑。这里的判断只用到 type / value / children 三个字段。
  return (tree: unknown): void => {
    walk(tree as MdNode)
  }
}

function walk(node: MdNode): void {
  const children = node.children
  if (!children) return

  for (let index = 0; index < children.length; index += 1) {
    const child = children[index]

    if (child.type === 'text' && child.value?.includes('\n')) {
      const parts = splitLines(child.value)
      children.splice(index, 1, ...parts)
      // 新节点已经处理过，跳过它们（-1 之后由循环的 +1 抵消）
      index += parts.length - 1
      continue
    }

    if (!VERBATIM.has(child.type)) walk(child)
  }
}

/** 把一段文本拆成 `text` + `break` 的序列 */
function splitLines(value: string): MdNode[] {
  const lines = value.replace(/\r\n?/g, '\n').split('\n')
  const nodes: MdNode[] = []

  lines.forEach((line, index) => {
    if (index > 0) nodes.push({ type: 'break' })
    if (line) nodes.push({ type: 'text', value: line })
  })

  // 末尾那个没有后续文本的 `break` 要去掉：它在浏览器里会额外占一行，
  // 而 Markdown 解析器本来也不会保留段落结尾的换行。
  while (nodes.length > 0 && nodes[nodes.length - 1].type === 'break') nodes.pop()

  return nodes
}
