/**
 * 朗读（文字转语音）。
 *
 * ## ⚠️ 识别部分已从这里移走
 *
 * 以前这里用 Web Speech API 的 `SpeechRecognition` 做语音输入。它有个绕不开的
 * 问题：Chromium 的实现**会把音频送到 Google 的服务端**，而"对话数据留在本机"
 * 是这个客户端的定位（语音里常有会议细节、地址、人名）。
 *
 * 现在识别改成本地模型：采集在 `voiceCapture.ts`，推理在核心的 `voice/` 包
 * （SenseVoice-Small ONNX，实测 8 秒音频约 300ms）。音频不出本机，也不再受
 * 系统语音包质量的影响。
 *
 * ## 这里剩下什么
 *
 * 只有朗读，用的仍是系统 `speechSynthesis`：它不联网、零体积、无需下载模型。
 *
 * ⚠️ **自动播报搭子回复**的功能已在 按产品要求剔除（试听本地 Kokoro
 * 中文样本后认为效果差）。所以朗读目前**只由用户手动触发** —— 点消息上的小喇叭。
 * 这属于既有能力，与"语音对话模式"是两回事。
 */

/** 朗读是否可用。 */
export function isSpeechSupported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
}

let speaking = false

/**
 * 把 Markdown 转成适合朗读的纯文本。
 *
 * **这一步不能省。** 直接把原文丢给语音合成，会把 ``` 念成"反引号反引号反引号"、
 * 把 `**` 念成"星号星号"、把链接 URL 一个字符一个字符读出来 —— 听感上全是噪声，
 * 真正的句子反而被淹掉。
 */
export function toSpeakableText(markdown: string): string {
  return markdown
    .replace(/```[\s\S]*?```/g, '（此处有一段代码）')
    .replace(/~~~[\s\S]*?~~~/g, '（此处有一段代码）')
    // 行内代码只去掉反引号：内容本身通常是要听的（命令名、参数值）
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
    // 表格：竖线读成停顿，分隔行（|---|---|）整行丢掉 —— 它没有任何语义
    .replace(/^\s*\|?[\s:|-]+\|[\s:|-]*$/gm, '')
    .replace(/\|/g, '，')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

/**
 * 朗读一段文字。
 *
 * 会**先取消上一次朗读**：用户点第二条消息的喇叭时，显然是想听新的那条，
 * 而不是让两条声音叠在一起。`speechSynthesis` 默认是排队而不是打断，
 * 不显式 cancel 就会变成后点的那条一直等前面念完。
 *
 * ``onEnd`` 是必需的：`speechSynthesis` **没有**全局的结束事件，
 * 不回调的话调用方没法知道该在什么时候把"正在朗读"的按钮状态复位。
 * 被 cancel 打断时也会触发 —— 这正是我们要的，上一条会自己复位。
 */
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
  // 默认语速偏慢，长段落听起来很拖；1.15 是试下来比较自然的值
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
