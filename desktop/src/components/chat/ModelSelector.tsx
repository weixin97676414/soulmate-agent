/**
 * 选"这一轮用哪个模型回答"。
 *
 * ## 为什么单独一个文件
 *
 * 它原先长在 `ChatView` 里（对话框顶栏那块）。产品要求把它挪到**输入栏下方那一行**，
 * 而那一行由 `ComposerShell` 渲染、由 `Composer` 填充 —— 如果继续从 `ChatView`
 * 导出，就会形成 `ChatView → Composer → ChatView` 的循环依赖（能跑，但初始化
 * 顺序会变成一件要靠运气的事）。抽出来两边都干净。
 *
 * ## 为什么选项显示的是模型名，不是"服务商 · 模型名"
 *
 * 服务商已经在 `<optgroup>` 的分组标签上了，选项里再重复一遍只是白占宽度。
 * 「主对话模型」那个标签也一并去掉了（产品要求）：这一行的位置本身就说明了
 * 它管什么，而左下角的空间要留给两个入口。
 */

import { useMemo } from 'react'

import { useAppStore } from '@/stores/appStore'
import { useChatStore } from '@/stores/chatStore'

export function ModelSelector() {
  const models = useAppStore((state) => state.models)
  const effectiveDefault = useAppStore((state) => state.modelDefaults.effectiveDefault)
  const modelId = useChatStore((state) => state.modelId)
  const setModelId = useChatStore((state) => state.setModelId)
  const streaming = useChatStore((state) => state.streaming)

  const enabled = models.filter((model) => model.enabled)
  const current = modelId ?? effectiveDefault

  const grouped = useMemo(() => {
    const map = new Map<string, typeof enabled>()
    for (const model of enabled) {
      const key = model.provider || '其他'
      const list = map.get(key) ?? []
      list.push(model)
      map.set(key, list)
    }
    return [...map.entries()]
  }, [enabled])

  if (enabled.length === 0) {
    return <span className="text-[12.5px] text-danger">未配置可用模型</span>
  }

  return (
    <select
      value={current}
      disabled={streaming}
      onChange={(event) => setModelId(event.target.value)}
      /*
        宽度 = **输入栏卡片宽度的 1/4**，且随窗口自适应（产品要求）。

        ## 宽度历程：`max-w-[260px]` → `w-1/3` → `w-[25cqw]`

        · `max-w-[260px]`：写死的像素。窗口拉宽时它一直只占 260px，在一整行控件
          里显得局促；窗口收窄时又可能顶到旁边的按钮。**完全不自适应**。
        · `w-1/3`：看着像自适应，其实参照物是**它所在的那一格**——底栏是
          `grid-cols-3`，中间那格本身只有卡片宽的约 1/3，于是它实际只有卡片的
          **1/9**。"三分之一"和用户看到的宽度对不上。
        · `w-[25cqw]`：cqw = **容器**宽度的 1%，而容器就是输入栏那张卡片
          （`ComposerShell` 根元素上的 `@container`）。所以这一条是"恒等于卡片宽的
          1/4"，窗口怎么伸缩都成立 —— 这正是用户要的"比例一直保持一致"。

        ⚠️ 它依赖祖先上有 `@container`。那一句被删掉的话这里**不会报错**，
        只会静默退回成"视口宽度的 1/4"，窗口拉宽时下拉不再跟卡片走。

        `min-w-0` 保证里面的长模型名用省略号，而不是把那一格撑破。
      */
      // ⚠️ 这个下拉没有任何可见标签（设计上它就在输入栏里），第 90 批（M-34）补
      // `aria-label` 让读屏能说出它是什么；`focus-visible:ring-*`（M-35）只对键盘生效。
      aria-label="选择模型"
      className="h-7 w-[25cqw] min-w-0 max-w-full cursor-pointer rounded-[8px] border border-line bg-canvas px-2 text-[12.5px] text-ellipsis text-ink hover:border-ink-faint/60 focus:border-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 disabled:cursor-not-allowed disabled:opacity-60"
    >
      {grouped.map(([provider, list]) => (
        <optgroup key={provider} label={provider}>
          {list.map((model) => (
            <option key={model.id} value={model.id}>
              {model.model_name || model.display_name}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  )
}
