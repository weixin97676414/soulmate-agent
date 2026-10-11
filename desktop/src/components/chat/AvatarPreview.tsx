/**
 * 搭子头像的大图弹窗。
 *
 * 产品要求："对话框中，用户点击搭子头像，可以查看 800×800 的搭子
 * 头像大图，群聊也要适用"。
 *
 * 因为头像组件自己会往 `avatarPreviewStore` 里写要看的图（见 `AssistantAvatar`），
 * 所以这个弹窗**只需要在 App 顶层挂一次**，所有位置的点头像都会弹它 ——
 * 包括以后新加的头像渲染点、以及群聊里那几个不同的渲染位置。
 */

import { Settings2 } from 'lucide-react'

import { Modal } from '@/components/ui'
import { useAssistantStore } from '@/stores/assistantStore'
import { useAvatarPreviewStore } from '@/stores/avatarPreviewStore'
import { useGroupStore } from '@/stores/groupStore'

export function AvatarPreview() {
  const src = useAvatarPreviewStore((state) => state.src)
  const name = useAvatarPreviewStore((state) => state.name)
  const assistantId = useAvatarPreviewStore((state) => state.assistantId)
  const groupId = useAvatarPreviewStore((state) => state.groupId)
  const close = useAvatarPreviewStore((state) => state.close)

  // ⚠️ 按钮只在**看得出这是谁**时出现：
  // · 搭子的（`assistantId` 非空）→ 「配置搭子」
  // · 群的（`groupId` 非空）→ 「群设置」
  // · 用户自己的（两个都空）→ 什么都不给（给一个点了不知道会打开谁的按钮，
  //   比没有按钮更糟）
  const assistants = useAssistantStore((state) => state.assistants)
  const profile = assistantId ? assistants.find((item) => item.id === assistantId) : undefined

  if (!src) return null

  return (
    /* `width` 收的是 Tailwind 的 max-w-* 类名，不是像素数 */
    <Modal
      open
      onClose={close}
      title={name}
      width="max-w-[640px]"
      // ⚠️ 标题**仍靠左**，只有旁边那个按钮**相对整个标题栏居中**
      // （"我说的是按钮居中，群名和搭子名还是居左呀"）。
      // 别把它做成"标题 + 按钮整组居中" —— 那样标题就不在左边了。
      centerTitleExtra
      /*
        ⚠️ 「配置搭子」/「群设置」在**标题同一行**（
        "标题（搭子名）要和配置搭子按钮为同一行"）。

        原先它单独占标题下面的一行、还居中 —— 标题与它之间空出一块，
        看起来像"标题属于上面那块、按钮属于下面那块"，而它们是同一件事：
        "看的是谁" 和 "改谁"。
      */
      titleExtra={
        profile ? (
          <button
            type="button"
            onClick={() => {
              close()
              // 打开搭子编辑弹窗。走 store 而不是把 modal 状态也搬进大图组件：
              // 搭子栏的右键菜单、设置页也都能打开它，那几个入口共用同一份状态。
              useAssistantStore.getState().openEditor(profile.id)
            }}
            className="flex shrink-0 items-center gap-1.5 rounded-[8px] border border-line px-3 py-1 text-[12.5px] text-ink-soft transition-colors hover:bg-hover hover:text-ink"
          >
            <Settings2 size={13} />
            配置搭子
          </button>
        ) : groupId ? (
          <button
            type="button"
            onClick={() => {
              close()
              /*
                「群设置」那个 Modal 在 `GroupChatPage` 里，而本组件挂在 App 顶层 ——
                两者之间没有可用的调用路径，所以走 store 传一个"请求"：
                页面订阅这个字段，看到就打开自己的弹窗。
                与「配置搭子」走 `assistantStore.openEditor` 是同一个套路。
              */
              useGroupStore.getState().requestGroupSettings(groupId)
            }}
            className="flex shrink-0 items-center gap-1.5 rounded-[8px] border border-line px-3 py-1 text-[12.5px] text-ink-soft transition-colors hover:bg-hover hover:text-ink"
          >
            <Settings2 size={13} />
            群设置
          </button>
        ) : null
      }
    >
      {/*
        图**固定成正方形**，用 `aspect-square` + `object-cover`（
        "无论用户上传多大的图片，都固定以 800*800 展示即可，不用说明"）。

        ⚠️ 不再用 `h-auto`（按原图比例）：那样一张 800×600 的图会显示成扁的，
        而它是个**头像** —— 用户上传时看到的应该是圆的/方的那个东西本身。
        裁掉两边不影响识别，比例不对反而让人以为传错了图。

        说明那句「800 × 800 以内的原图」按产品要求**剔除**了：尺寸是系统的事，
        用户不需要知道，而且那句话会让人以为"我只能传 800 以内的"。
      */}
      <div className="flex justify-center">
        <img
          src={src}
          alt={name}
          className="aspect-square w-full max-w-[560px] rounded-[12px] border border-line object-cover select-none"
          draggable={false}
        />
      </div>
    </Modal>
  )
}
