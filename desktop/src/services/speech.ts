






















export function isSpeechSupported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
}

let speaking = false








export function toSpeakableText(markdown: string): string {
  return markdown
    .replace(/```[\s\S]*?```/g, '（此处有一段代码）')
    .replace(/~~~[\s\S]*?~~~/g, '（此处有一段代码）')
    
    .replace(/`([^`]+)`/g, '$1')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '（图片）')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/^\s{0,3}#{1,6}\s+/gm, '')
    .replace(/^\s{0,3}>\s?/gm, '')
    .replace(/^\s{0,3}[-*+]\s+/gm, '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/__([^_]+)__/g, '$1')
    .replace(/~~([^~]+)~~/g, '$1')
    
    .replace(/^\s*\|?[\s:|-]+\|[\s:|-]*$/gm, '')
    .replace(/\|/g, '，')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}












export function speak(
  text: string,
  options: { lang?: string; rate?: number; onEnd?: () => void } = {},
): boolean {
  if (!isSpeechSupported()) return false

  const clean = text.trim()
  if (!clean) return false

  window.speechSynthesis.cancel()

  const utterance = new SpeechSynthesisUtterance(clean)
  utterance.lang = options.lang ?? 'zh-CN'
  
  utterance.rate = options.rate ?? 1.15

  const finish = () => {
    speaking = false
    options.onEnd?.()
  }
  utterance.onend = finish
  utterance.onerror = finish

  speaking = true
  window.speechSynthesis.speak(utterance)
  return true
}

export function stopSpeaking(): void {
  if (!isSpeechSupported()) return
  window.speechSynthesis.cancel()
  speaking = false
}

export function isSpeaking(): boolean {
  return speaking
}
