import { Info } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { AssistantAvatar } from '@/components/chat/AssistantFormModal'
import { Button, Input, Select } from '@/components/ui'
import { AVATAR_MAX_SIZE, readImageAsDataUrl } from '@/lib/image'
import { useAppStore } from '@/stores/appStore'
import { useAssistantStore } from '@/stores/assistantStore'
import type { AssistantProfile } from '@/types'

/**
 * 内置搭子的「快捷设置」卡片（产品要求）。
 *
 * ## 它是什么
 *
 * 挂在对话栏顶部那张「搭子名称 + 简介」卡片下面，只对**四个内置搭子**出现，四行：
 * 头像 / 昵称 / 性别 / 怎么称呼你，右下角一个「保存」。**保存一次即完成**：
 * 卡片淡出收起，原地留下一句「左侧右键点击搭子，可修改配置」。
 *
 * ## 为什么要有它
 *
 * 内置搭子的人格文件是出厂预设，用户第一次打开会看到"我是你的 Soulmate"这类
 * 自我介绍，但**没有任何入口告诉它"你叫什么、我该怎么称呼你"** ——
 * 只能自己去「设置 → 搭子」里翻。这一步是产品最想让人做对的事，所以摆到最显眼的地方。
 *
 * ## 两处容易做错的地方
 *
 * 1. **实时替换 ≠ 保存**：选完头像 / 打字改昵称，界面要**当场**跟着变。
 *    实现是往 store 里塞一份"预览"（`useAssistantStore.preview`，只改内存不落盘）；
 *    没保存就离开时**必须把预览撤回**（见下面的卸载清理），否则会留下
 *    "界面显示新昵称、文件里是旧的"，下次启动又变回去。
 * 2. **写进去的是文件里的原文**：昵称与性别写进 `IDENTITY.md`、称呼写进 `USER.md`，
 *    都是**读原文 → 换掉那一行 → 写回**，绝不用界面上的值整份覆盖（那会把搭子的
 *    自我介绍、用户的动态档案一起抹掉）。替换规则见下面三个 apply* 函数。
 *
 * ⚠️ 内置搭子的 `RULES.md` 是锁死的（服务端 409），但 `IDENTITY.md` / `USER.md` 可写 ——
 * 所以这里走的是现成的人格文件接口，没有新增 IPC 通道。
 */

/** 已完成快捷设置的搭子 id（**按搭子分别记、永久生效**，只存本机） */
const DONE_KEY = 'soulmate.quick-setup.done'

/**
 * `IDENTITY.md` 里那句"给模型的批注"。
 *
 * 它是规则（没设昵称先用出厂名、设了要改成用户给的称呼），写在文件里给模型看；
 * 用户在这里设了昵称之后，它就被换成实际值 —— 这是指定的替换规则。
 */
const NICKNAME_HINT =
  '（用户未设置昵称前使用，设置昵称后需要你更改为用户设置的昵称或约定称呼）'

/**
 * 昵称在 IDENTITY.md 里的前缀。
 *
 * ⚠️ 它**不在行首**：按用户的替换规则，这句是接在「名字」与「我是你的 …」后面的
 * （`Soulmate用户为你设定的昵称：小伴`），所以读、写都不能按"整行"处理 ——
 * 按行匹配会一个字都读不到 / 一处都改不掉（预检脚本在真文件上实测过这一点）。
 */
const NICKNAME_PREFIX = '用户为你设定的昵称：'

/** 昵称写进 IDENTITY.md 的样子 */
const nicknameLine = (value: string) => `${NICKNAME_PREFIX}${value}`

/**
 * 性别那行的前缀（IDENTITY.md 里写的是**搭子自己**的性别，不是用户的）。
 *
 * ⚠️ 下拉只有三项：「暂不设置」（默认）/ 男 / 女。产品约定：
 * 这一项设的是搭子的性别，所以不需要"不愿透露"这种回避项；同时**保留"暂不设置"**
 * （它是一项真实可选的选择，也是默认值）—— 没有它就没法表达"用户还没选过"，
 * 而一旦把默认值直接定成「男」，用户只是打开一次卡片就替搭子定了性别。
 */
const GENDER_PREFIX = '性别：'

/** 只认「男 / 女」；其余历史值（例如早期版本写下的「不愿透露」）一律按"没选过"处理 */
function normalizeGender(raw: string): string {
  return raw === '男' || raw === '女' ? raw : ''
}

/** 用户称呼那行的前缀（USER.md） */
const ADDRESS_PREFIX = '用户称呼：'

function readDone(): string[] {
  try {
    const raw = window.localStorage.getItem(DONE_KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : []
  } catch {
    // localStorage 在某些受限上下文里会直接抛（隐私模式 / 配额）。读不出来就当"没完成过"：
    // 最坏结果是卡片再出现一次，而不是整个侧栏烂掉。
    return []
  }
}

function markDone(id: string): void {
  try {
    const done = readDone()
    if (done.includes(id)) return
    window.localStorage.setItem(DONE_KEY, JSON.stringify([...done, id]))
  } catch {
    // 写不进去只影响"下次还显示卡片"，不影响已经保存的内容
  }
}

/**
 * 把昵称写进 IDENTITY.md。
 *
 * ⚠️ 那句批注在每份 IDENTITY.md 里出现**两次**（「名字行」与「我是你的 …」自我介绍行），
 * 按用户的替换规则**两处都要换**（预检脚本在真文件上量过：3 份文件各 2 处）。
 * 只换一处会留下"没设昵称就用出厂名"这条已经过期的指令 —— 模型读到自相矛盾的
 * 两句话时，最容易的处置恰恰是**忽略昵称**，那样这个功能就白做了。
 *
 * 三级兜底，否则用户改第二次会一无所获：批注句还在就换它（全部）；批注已经被换掉了，
 * 就改写已有的 `用户为你设定的昵称：…` 行；两样都没有才追加到文件末尾。
 */
function applyNickname(identity: string, nickname: string): string {
  if (identity.includes(NICKNAME_HINT)) {
    // split/join 而不是 replace：replace 只换第一处，另一处会留下过期指令
    return identity.split(NICKNAME_HINT).join(nicknameLine(nickname))
  }
  // 上面换过一次之后，这句同样有**两处**，而且都嵌在行中 —— 所以这里按"前缀 + 到句号/行尾"
  // 全局替换：少一个 g 就会留下一个不同的旧昵称，少写"句末不算值"就会把自我介绍句的
  // 句号一起吃掉（预检脚本在真文件上实测过这两点）
  const updated = identity.replace(
    new RegExp(`${NICKNAME_PREFIX}[^。\\n]*`, 'g'),
    nicknameLine(nickname),
  )
  if (updated !== identity) return updated
  return `${identity.trimEnd()}\n${nicknameLine(nickname)}\n`
}

/** 把性别写进 IDENTITY.md（**替换那一行的值**，不是覆盖整份文件）。 */
function applyGender(identity: string, gender: string): string {
  const line = new RegExp(`^${GENDER_PREFIX}.*$`, 'm')
  if (line.test(identity)) return identity.replace(line, `${GENDER_PREFIX}${gender}`)
  return `${identity.trimEnd()}\n${GENDER_PREFIX}${gender}\n`
}

/** 把"怎么称呼用户"写进 USER.md。 */
function applyAddress(user: string, address: string): string {
  const line = new RegExp(`^${ADDRESS_PREFIX}.*$`, 'm')
  if (line.test(user)) return user.replace(line, `${ADDRESS_PREFIX}${address}`)
  return `${user.trimEnd()}\n${ADDRESS_PREFIX}${address}\n`
}

/**
 * 从文件内容里把"某一项已有的值"读回来（用户第二次打开卡片时要显示当前值，而不是空白）。
 *
 * 不能按「行首 + 整行」读：昵称那一项**不在行首**（见 `NICKNAME_PREFIX` 的说明）。
 * 值的边界是行尾或句号 —— 自我介绍句后面那个句号是标点，不该被当成值的一部分。
 */
function currentValue(content: string, prefix: string): string {
  const match = new RegExp(`${prefix}([^。\\n]*)`).exec(content)
  return match ? match[1].trim() : ''
}

function fileName(
  files: Array<{ name: string; content: string }>,
  name: string,
): string {
  return files.find((item) => item.name === name)?.content ?? ''
}

export function QuickSetupCard({ assistant }: { assistant: AssistantProfile }) {
  const api = useAppStore((state) => state.api)
  const save = useAssistantStore((state) => state.save)
  const preview = useAssistantStore((state) => state.preview)
  const reload = useAssistantStore((state) => state.load)

  const [avatar, setAvatar] = useState(assistant.avatar)
  const [nickname, setNickname] = useState(assistant.nickname)
  const [gender, setGender] = useState('')
  const [address, setAddress] = useState('')
  const [saving, setSaving] = useState(false)
  const [leaving, setLeaving] = useState(false)
  const [error, setError] = useState('')
  /** 这一家已完成过：卡片换成一句固定说明（关掉客户端再回来也保持） */
  const [done, setDone] = useState(() => readDone().includes(assistant.id))
  const fileRef = useRef<HTMLInputElement>(null)

  /** 卸载时要把预览撤回成这个样子（= 这张卡片出现那一刻的真实值） */
  const baseline = useRef({
    avatar: assistant.avatar,
    nickname: assistant.nickname,
    dirty: false,
    saved: false,
  })

  /**
   * 把已有的性别 / 称呼读回来做初值。
   *
   * 只读、只在挂载时跑一次：写入那一步会把原文重新拉一遍再做替换，
   * 所以这里读到的是"上一次保存时的样子"，够用且不会和写入抢文件。
   */
  useEffect(() => {
    let cancelled = false
    void (async () => {
      if (!api || done) return
      try {
        const payload = await api.getPersonaFiles(assistant.id)
        if (cancelled) return
        const identity = fileName(payload.files, 'IDENTITY.md')
        const user = fileName(payload.files, 'USER.md')
        // 回填时就把"不认识的历史值"剔掉：老数据里可能是「不愿透露」（那一项已经删了），
        // 带进状态会出现"下拉显示暂不设置、而保存时又把旧值写回去"的错位。
        // 注意这里**只回落到空**，不主动改写文件 —— 用户重选一次才覆盖。
        setGender(normalizeGender(currentValue(identity, GENDER_PREFIX)))
        setAddress(currentValue(user, ADDRESS_PREFIX))
        setNickname((value) => value || currentValue(identity, '用户为你设定的昵称：'))
      } catch (failure) {
        // 读不到不算失败：用户照样能把四项填完保存（写入那一步会再读一次）
        console.error('读取人格文件失败', failure)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [api, assistant.id, done])

  // 没保存就离开（切了搭子 / 收起侧栏 / 退出对话视图）→ 把预览撤回
  useEffect(() => {
    const snapshot = baseline.current
    return () => {
      if (snapshot.dirty && !snapshot.saved) {
        preview(assistant.id, { avatar: snapshot.avatar, nickname: snapshot.nickname })
      }
    }
  }, [assistant.id, preview])

  const pushPreview = (changes: Partial<AssistantProfile>): void => {
    baseline.current.dirty = true
    preview(assistant.id, changes)
  }

  const pickAvatar = async (file: File | undefined): Promise<void> => {
    if (!file) return
    const dataUrl = await readImageAsDataUrl(file, AVATAR_MAX_SIZE)
    setAvatar(dataUrl)
    pushPreview({ avatar: dataUrl }) // 实时替换：卡片与左侧列表同一帧变
  }

  const submit = async (): Promise<void> => {
    if (!api) return
    setSaving(true)
    setError('')
    try {
      // ① 头像 / 昵称落 assistants.json。昵称**必须**也写这里：不写的话左侧列表里
      //    的称呼不会变，用户会当成"改了没生效"。
      await save({ ...assistant, avatar, nickname: nickname.trim() })
      // ② 昵称 / 性别 → IDENTITY.md，称呼 → USER.md。每一步都是"重新读原文 → 换行 → 写回"。
      const payload = await api.getPersonaFiles(assistant.id)
      const identity = fileName(payload.files, 'IDENTITY.md')
      const user = fileName(payload.files, 'USER.md')
      const nicknameValue = nickname.trim()
      if (nicknameValue) {
        await api.writePersonaFile(
          assistant.id,
          'IDENTITY.md',
          applyGender(applyNickname(identity, nicknameValue), gender),
        )
      } else if (gender) {
        await api.writePersonaFile(assistant.id, 'IDENTITY.md', applyGender(identity, gender))
      }
      if (address.trim()) {
        await api.writePersonaFile(assistant.id, 'USER.md', applyAddress(user, address.trim()))
      }
      baseline.current.saved = true
      markDone(assistant.id)
      // 淡出收起（160ms，与动效规范一致）；收完这一帧才换成固定说明
      setLeaving(true)
      window.setTimeout(() => {
        setLeaving(false)
        setDone(true)
        // 收尾再拉一次：搭子栏 / 消息区的称呼要跟着落盘后的真值走一遍
        void reload()
      }, 160)
    } catch (failure) {
      // 任一步失败都不置"已完成"：卡片留在原地并说清楚 ——
      // 最怕的是"以为保存了其实没写"
      setError(
        `保存失败，请重试：${failure instanceof Error ? failure.message : String(failure)}`,
      )
    } finally {
      setSaving(false)
    }
  }

  if (done) {
    return (
      <div className="mx-2.5 mb-1 flex items-center gap-1.5 rounded-[8px] border border-line-soft bg-canvas px-2.5 py-1.5 text-[11.5px] text-ink-faint">
        <Info size={12} className="shrink-0" aria-hidden="true" />
        {/* 产品要求换掉原话（原为"左侧右键点击搭子，可修改配置"）：
            右键是个**发现性极差**的入口，而头像现在能直接点开大图、里面就有
            「配置搭子」—— 那条路用户看得见。 */}
        <span>点击搭子头像，可修改配置</span>
      </div>
    )
  }

  return (
    <div
      className={
        'mx-2.5 mb-1 rounded-[8px] border border-line-soft bg-canvas px-2.5 py-2 ' +
        'transition-opacity duration-[160ms] motion-reduce:transition-none ' +
        (leaving ? 'opacity-0' : 'opacity-100')
      }
    >
      <div className="mb-1.5 text-[11.5px] font-medium text-ink-soft">快速设置</div>

      <div className="space-y-1.5">
        <div className="flex items-center gap-2">
          <span className="w-[52px] shrink-0 text-[11.5px] text-ink-soft">头像</span>
          {/*
            ⚠️ 尺寸 **32**（"搭子快速设置卡片当中的搭子头像图片显示
            太小了，放大一圈"）。原先是 22 —— 它右边的「选择图片」按钮是 h-7（28px），
            头像比按钮还小，看起来像按钮的附属小图标，而不是"这个搭子的脸"。
            32 之后与这一整行齐平，也正好是群名卡片那个群头像的尺寸。
          */}
          <AssistantAvatar profile={{ ...assistant, avatar }} size={32} />
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(event) => void pickAvatar(event.target.files?.[0])}
          />
          <Button
            size="sm"
            className="ml-auto h-7"
            disabled={saving}
            onClick={() => fileRef.current?.click()}
          >
            选择图片
          </Button>
        </div>

        <div className="flex items-center gap-2">
          <span className="w-[52px] shrink-0 text-[11.5px] text-ink-soft">昵称</span>
          <Input
            value={nickname}
            maxLength={24}
            placeholder="它叫什么"
            // 左边的标签是个 <span>（这一行是"标签 + 控件"的横排），所以用 aria-label
            // 把名字补上：屏幕阅读器读不出"昵称"两个字，这个输入框就只剩一个孤零零的框
            aria-label="昵称"
            className="h-8 min-w-0 flex-1 text-[12.5px]"
            disabled={saving}
            onChange={(event) => {
              setNickname(event.target.value)
              pushPreview({ nickname: event.target.value })
            }}
          />
        </div>

        <div className="flex items-center gap-2">
          <span className="w-[52px] shrink-0 text-[11.5px] text-ink-soft">性别</span>
          <Select
            value={gender}
            aria-label="性别"
            className="h-8 min-w-0 flex-1 text-[12.5px]"
            disabled={saving}
            onChange={(event) => setGender(event.target.value)}
          >
            <option value="">暂不设置</option>
            <option value="男">男</option>
            <option value="女">女</option>
          </Select>
        </div>

        <div className="flex items-center gap-2">
          <span className="w-[52px] shrink-0 text-[11.5px] text-ink-soft">称呼你</span>
          <Input
            value={address}
            maxLength={24}
            placeholder="它该怎么叫你"
            aria-label="怎么称呼你"
            className="h-8 min-w-0 flex-1 text-[12.5px]"
            disabled={saving}
            onChange={(event) => setAddress(event.target.value)}
          />
        </div>
      </div>

      {/*
        ⚠️ 产品要求：剔除原来那行说明（"填了之后它会这样叫你，并记住你是谁"），
        保存按钮改成**占满这一行**。

        说明原本占掉一半宽度，而这句话对"要不要填、填什么"没有任何帮助 ——
        它只是在复述输入框的用途。腾出来的宽度给按钮，点击目标从半行变成整行。
        底色沿用 `primary`（= `--app-brand`），所以它天然跟随 UI 主色。
      */}
      <Button
        size="sm"
        variant="primary"
        className="mt-2 w-full"
        disabled={saving}
        onClick={() => void submit()}
      >
        {saving ? '保存中…' : '保存'}
      </Button>

      {error ? (
        // aria-live：保存失败是**异步**结论，读屏用户不被告知就等于没提示
        <p role="status" aria-live="polite" className="mt-1 text-[11.5px] break-words text-danger">
          {error}
        </p>
      ) : null}
    </div>
  )
}
