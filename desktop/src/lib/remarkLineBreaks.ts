




























type MdNode = { type: string; value?: string; children?: MdNode[] }


const VERBATIM = new Set(['code', 'inlineCode', 'html', 'yaml', 'toml', 'math', 'inlineMath'])

export function remarkLineBreaks() {
  
  
  
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
      
      index += parts.length - 1
      continue
    }

    if (!VERBATIM.has(child.type)) walk(child)
  }
}


function splitLines(value: string): MdNode[] {
  const lines = value.replace(/\r\n?/g, '\n').split('\n')
  const nodes: MdNode[] = []

  lines.forEach((line, index) => {
    if (index > 0) nodes.push({ type: 'break' })
    if (line) nodes.push({ type: 'text', value: line })
  })

  
  
  while (nodes.length > 0 && nodes[nodes.length - 1].type === 'break') nodes.pop()

  return nodes
}
