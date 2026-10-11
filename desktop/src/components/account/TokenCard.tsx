import { Card } from '@/components/account/Card'
import { useAccountStore } from '@/stores/accountStore'
import { formatToken } from '@/utils/amount'

/**
 * 「我的 Token」卡：余额 + 它是什么。
 *
 * 与充值卡里的余额**故意各显示一次**：充值卡回答"怎么充"，这张卡回答"这东西是什么"。
 * 用户问得最多的就是这两件事，分开放反而更容易被漏看。
 *
 * 标题里的「新用户赠送 20、填邀请码 XJX 再得 20」是**获客闭环的说明**：Token 的来路
 * 除了赞助还有新用户赠送与邀请码奖励，邀请码卡就在同页上方 —— 卡片标题点名了它，
 * 用户不用自己把两件事联系起来。
 *
 * ## ⚠️ 这里删掉了一段红字用途说明
 *
 * 原文是「Token 仅用于"人际关系运营"Skill 使用消耗，其余所有功能**永久免费**」，
 * 用红字显示。它现在**两头都不对**了：
 *
 * · 那时 Token 的定位是"消耗品"——花在某个特定技能上。产品约定
 *   改成了 **「Soulmate Agent 开源社区的贡献值」**，那是**身份的度量**，
 *   不是计价单位；
 * · 而且那句话里的"仅人际关系运营消耗"也已经过时：那个 Skill 现在**免费**
 *   （见 `core/src/my_agent/resources/xjx/buddies-*.md` 的口径）。
 *
 * 一句话说错两次，比不说更糟 —— 用户会拿它去推断"我该充多少"。所以整段剔除，
 * 只留下面那句定性。
 *
 * ⚠️ **不要**再把"Token 用来干什么"写回来：那一栏现在没有可写的正确答案。
 * 等用途定下来（比如能换什么、能做什么）再补，而不是拿旧口径凑一句。
 */
export function TokenCard() {
  const snapshot = useAccountStore((state) => state.snapshot)

  if (!snapshot) return null
  const current =
    snapshot.accounts.find((item) => item.id === snapshot.currentId) ?? snapshot.accounts[0] ?? null

  return (
    /*
      ⚠️ 标题里的「（新用户赠送 20 Token，填邀请码 XJX 再得 20）」按
      要求**剔除**。

      它原先有两个作用：讲清 Token 的来路、并顺手把"填邀请码"这条获客闭环带出来。
      但 Token 的口径已经从"额度"改成**开源社区的贡献值**之后，"赠送 20"这种
      报价式的表述就与定性冲突了 —— 贡献值不该是被"送"的。来路那件事交给
      `InviteCard` 自己讲（它就在同一页），不必挤在标题里。
    */
    <Card
      // 标题带上「（社区贡献值）」：单看"我的 Token"这三个字，没人知道它是什么 —— 是
      // 余额？是流量？还是某种虚拟货币？**定性写在最显眼的地方**。
      title="我的 Token（社区贡献值）"
    >
      {!current ? (
        <p className="text-[12.5px] text-ink-soft">账号就绪后即可查看 Token 余额。</p>
      ) : (
        <div className="space-y-2">
          <div className="flex items-end gap-2">
            <span className="text-[22px] font-semibold leading-none tracking-tight text-ink tabular-nums">
              {formatToken(current.token_balance)}
            </span>
            {/*
              ⚠️ 单位后面这句说明是产品要求加的：光看一个数字，
              用户不知道"这些 Token 现在能干嘛" —— 而答案恰恰是"暂时没有地儿花"。
              与其让人疑心"是不是我哪里没开通"，不如直接说清。

              ⚠️ 括号内不空格（照用户给的字面）：`技能与MCP`。
            */}
            <span className="pb-0.5 text-[12.5px] text-ink-soft">
              Token（暂无需要消耗 Token 的技能与MCP）
            </span>
          </div>
          {/* 定性用**普通色**而不是红字：
              它是一句说明，不是"钱花在哪"的警告。原来的红字把"我是谁"
              渲染成了"我欠什么"，视觉上先吓人一跳。 */}
          <p className="text-[13px] font-medium leading-relaxed text-ink-soft">
            Token 是 Soulmate Agent 开源社区的<b className="text-ink-soft">贡献值</b>，
            在社区里用它记录你的贡献。
          </p>
        </div>
      )}
    </Card>
  )
}
