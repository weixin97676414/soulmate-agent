# 公众号编辑器兼容 HTML 样式指南

> 本指南是 `wechat-article-writer` skill 的配套样式参考。AI 生成 `<topic>-wechat.html` 时，**直接套用下方 9 类元素的成品代码片段**，把文案往里填即可。
>
> 本文件的设计目标是：**单文件 HTML + 全部 inline style，复制到公众号后台编辑器「HTML」模式后，手机端视觉直接可用**。

---

## 0. 三句话规则（开始前先背）

1. **全部 inline**：禁止 `<style>` 块、外联 CSS、自定义属性、grid、flex、transform、box-shadow、@media。任何细节样式都要写进 `style="…"`。
2. **不写左右 padding**：公众号后台默认给左右各 ~30px 内边距，再写就挤。**只管上下 margin**。
3. **手机端 375px 默念测试**：每段 ≤ 5 行，每行 ≤ 35 个汉字，全篇字号 ≥ 15px。

---

## 1. 调色板速记

下面这套是中性公众号审美，**不要引入任何个人/地域/设备相关的私货**。若整篇文章需要换主题色，下面这些 hex 是「和谐替换表」：

| 用途 | 默认（深绿主） | 商业蓝替 | 情感红替 | 暖金替 |
|------|------|------|------|------|
| 主字 | `#3d3d3d` | `#3d3d3d` | `#3d3d3d` | `#3d3d3d` |
| 强调字 | `#111` | `#111` | `#111` | `#111` |
| 主题色（标题/引用/边框） | `#2f4a3a` | `#1a3a6b` | `#7a2a30` | `#8a5a2a` |
| 金色亮点（标签/金句/反驳边） | `#b88a3a` | `#c19a3a` | `#a8404a` | `#b88a3a` |
| 浅金底（摘要/反驳底） | `#f7eed8` | `#f0ecdc` | `#f7e3df` | `#f7eed8` |
| 米白背景（preview 版） | `#f5f1e8` | `#f5f1e8` | `#f5f1e8` | `#f5f1e8` |
| 卡片白底（preview 版） | `#ffffff` | `#ffffff` | `#ffffff` | `#ffffff` |
| 弱化小字 | `#8a8a82` | `#8a8a82` | `#8a8a82` | `#8a8a82` |

> **判断该用哪个主题色**：
> - 商业洞察 / 行业分析 / 财报类 → 商业蓝 `#1a3a6b`
> - 个人成长 / 复盘 / 情感 / 人生选择 → 情感红 `#7a2a30`
> - 文化 / 历史 / 生活方式 → 深绿（默认） `#2f4a3a`
> - 美食 / 旅行 / 手作 → 暖金 `#8a5a2a`
> - 不确定 → 用深绿（默认）。

---

## 2. 字号 / 行高 / 间距速查表

| 场景 | font-size | line-height | letter-spacing | margin-bottom | 备注 |
|------|------|------|------|------|------|
| 正文段落 | 17px | 2 | 1.5px | 18px | 默认；不要写 margin-top |
| 二级小标题 | 18.5–19px | 1.45 | 0.5px | — | margin: `32px 0 14px` |
| 引言 / 卷首小段 | 14px | 1.8 | 1px | 12px | 灰色 `#8a8a82` |
| 强金句（居中） | 17–18px | 1.85 | 1.5px | 22px | `color:#b88a3a;font-weight:bold;text-align:center` |
| 引用块 | 15.5px | 1.9 | 1px | 22px | `<blockquote>` 加内联样式 |
| 数据数字（高亮） | 17px 默认，加粗 | — | — | — | `<span style="color:#111;font-weight:bold;">` |
| 来源 / 注释小字 | 13px | 1.85 | 0.5px | 6px | 灰色 `#8a8a82` |

---

## 3. 九类元素的成品代码片段

### 3.1 顶部卷首标签（非必需）

```html
<p style="font-size:13px;color:#b88a3a;letter-spacing:2px;margin-bottom:14px;">
  ◆ 商业洞察 · 深度长文
</p>
```

### 3.2 主标题（公众号后台另开标题区，本段可在正文首段显示）

```html
<p style="font-size:20px;font-weight:bold;color:#111;text-align:center;
          margin:16px 0 24px;line-height:1.5;">
  99.9% 和 62.7% 是同一周、同一台模型的两次跑分
</p>
```

### 3.3 标题三选一

```html
<p style="font-size:16px;color:#b88a3a;font-weight:bold;margin:14px 0 10px;
          letter-spacing:1px;">
  ◆ 标题三选一
</p>

<p style="font-size:15.5px;line-height:1.85;color:#3d3d3d;margin-bottom:10px;">
  <b style="color:#b88a3a;">【悬念】</b>
  <b style="color:#111;">GPT-6 拿了个 99.9%，隔壁跑同一台模型只有 62.7%</b>
</p>

<p style="font-size:15.5px;line-height:1.85;color:#3d3d3d;margin-bottom:10px;">
  <b style="color:#b88a3a;">【利益】</b>
  GPT-6 真实用法：从"替你写"到"替你做完一整件事"
</p>

<p style="font-size:15.5px;line-height:1.85;color:#3d3d3d;margin-bottom:22px;">
  <b style="color:#b88a3a;">【对比】</b>
  OpenAI 喊 AGI 时代开幕，真正改变打工人命运的是另一组数字
</p>
```

### 3.4 摘要框（金边 + 浅金底）

```html
<blockquote style="border-left:4px solid #b88a3a;background:#f7eed8;
                    padding:16px 20px;margin:20px 0 24px;border-radius:0 8px 8px 0;">
  <p style="font-size:12px;color:#b88a3a;font-weight:bold;letter-spacing:2px;
            margin-bottom:8px;">
    ◆ 摘 要
  </p>
  <p style="font-size:16px;line-height:1.9;color:#4a3a1a;margin:0;
            letter-spacing:0.5px;">
    99.9% 和 62.7% 是同一周、同一台模型的两次跑分。这 37.2% 的差别里，藏着这一代 AI
    真正会改变你工作方式的入口——不是更会聊天，而是能替你跑完一整段流程。
  </p>
</blockquote>
```

### 3.5 核心观点黑卡

```html
<p style="background:#111111;color:#f1ece0;padding:20px 22px;
          margin:24px 0;border-left:4px solid #b88a3a;font-size:15.5px;
          line-height:1.95;letter-spacing:0.5px;">
  <span style="color:#b88a3a;font-weight:bold;letter-spacing:2px;font-size:12px;
               display:block;margin-bottom:8px;">
    ◆ 核 心 观 点
  </span>
  GPT-6 的发布，真正的分水岭不在那个 99.9% 的跑分，而在它能"替一个人把一整件事
  从头做到尾"。营销喊的 AGI 你可以不信，但能不能用它替代自己某个岗位——
  这一代人，得自己掂量清楚。
</p>
```

### 3.6 二级小标题

```html
<h3 style="font-size:18.5px;color:#2f4a3a;font-weight:bold;margin:32px 0 14px;
           padding-left:12px;border-left:4px solid #2f4a3a;line-height:1.45;
           letter-spacing:0.5px;">
  一、跑分变 99.9% 不是奇迹，是把规则改了
</h3>
```

### 3.7 强金句（口语化、居中加粗）

```html
<p style="text-align:center;font-size:17px;color:#b88a3a;font-weight:bold;
          line-height:1.85;letter-spacing:1px;margin:22px 0;">
  以前 AI 帮你查个东西，你还得再花 5 分钟理解、过滤、二次提问。
  现在模型不仅给答案，还替你把二三次提问那部分工作一起做完了。
</p>
```

> 同主题色要换：把 `#b88a3a` 替换成对应色——商业蓝用 `#c19a3a`，情感红用 `#a8404a`。

### 3.8 引用块（blockquote）

```html
<blockquote style="border-left:3px solid #2f4a3a;background:#faf6ea;
                    padding:14px 18px;margin:22px 0;border-radius:0 6px 6px 0;
                    font-size:15.5px;line-height:1.9;color:#4a3a1a;">
  这事的本质是：模型在自适应推理框架下能达到 99.9%，说明它具备了非常强的"干中学"
  能力。但现实世界的开放性、噪音、长尾，跟一个封闭小游戏比，是两个量级。
</blockquote>
```

### 3.9 读者反驳（金边渐近色块）

```html
<p style="background:#f7eed8;border:1px dashed #b88a3a;padding:18px 22px;
          margin:28px 0 24px;font-size:15.5px;line-height:1.9;color:#5a4a26;
          border-radius:6px;">
  <span style="background:#b88a3a;color:#ffffff;font-size:12px;padding:2px 9px;
               border-radius:4px;display:inline-block;margin-bottom:10px;
               letter-spacing:1px;font-weight:bold;">
    ◆ 读 者 反 驳
  </span>
  <br>
  你可能在想：GPT-5.6 Sol 你都没用熟，API 价格涨了 2.5 倍，你给我吹这么神，是不是又一波噱头？——
  大多数打工人关心的是：这玩意儿落地到我这个岗位，到底能不能用上？
</p>

<p style="font-size:15.5px;line-height:1.95;color:#3d3d3d;margin-bottom:18px;
          letter-spacing:0.5px;">
  我认真说，这是这一代 AI 最公平的一点——噱头不噱头，不是发布会说了算，
  是你下班回家用它干一件事，结果说了算。
</p>
```

### 3.10 落地 case-card（浅米底 + 细边框）

```html
<section style="border:1px solid #e8e2d4;background:#fcfaf2;padding:18px 20px;
                 margin:16px 0 22px;border-radius:8px;">
  <p style="margin:0 0 8px;font-size:13px;color:#b88a3a;letter-spacing:1.5px;
            font-weight:bold;">
    ◆ 第一类 · 程序员
  </p>
  <p style="font-size:15.5px;line-height:1.9;color:#3d3d3d;margin:0 0 12px;
            letter-spacing:0.5px;">
    <b style="color:#111;">不在 IDE 里继续写新代码。</b>是把 GPT-6
    接进你的运维值班流、code review、事故复盘文档。
  </p>
  <p style="font-size:15px;line-height:1.9;color:#5a5a52;margin:0;
            letter-spacing:0.5px;">
    同样是接一个新模块：A 的做法是，让 GPT-6 解释"这段代码为什么要这么写"，
    生成注释后存进 Confluence，下次 review 直接复用。B 的做法是，继续按过去习惯写，
    周末补一份"新人入门手册"，绝大多数情况这手册永远停在 draft 状态。
    老板感受到的，前者是一个人干两个人的活儿还留资产，后者只是另一个还在写手册的程序员。
  </p>
</section>
```

### 3.11 互动引导（结尾）

```html
<p style="font-size:17px;font-weight:bold;color:#111;line-height:1.7;
          margin:36px 0 14px;text-align:center;">
  你最近打算先让 GPT-6 替你干哪件具体的活儿？
</p>

<p style="font-size:15.5px;line-height:1.95;color:#3d3d3d;margin:0 0 22px;
          text-align:center;letter-spacing:0.5px;">
  评论区聊聊，挑几个有意思的接着拆 👇
</p>
```

### 3.12 数据来源 / 注释

```html
<p style="font-size:13px;color:#8a8a82;line-height:1.85;margin:24px 0 6px;
          letter-spacing:0.5px;">
  <b style="color:#b88a3a;">◆ 数据来源</b>
</p>

<p style="font-size:13px;color:#8a8a82;line-height:1.85;margin:0 0 4px;
          letter-spacing:0.5px;">
  · 量子位 / 腾讯新闻《GPT-6 发布！105万上下文、OSWorld 72.6%》
</p>

<p style="font-size:13px;color:#8a8a82;line-height:1.85;margin:0 0 4px;
          letter-spacing:0.5px;">
  · 腾讯新闻《跑分 99.9%、自主操作电脑，GPT-6 到底强到什么程度？》
</p>

<p style="font-size:13px;color:#8a8a82;line-height:1.85;margin:0 0 18px;
          letter-spacing:0.5px;">
  · OpenAI 官方：openai.com/index/gpt-6-astra/
</p>
```

---

## 4. 移动端常见问题与修复

| 现象 | 原因 | 修复 |
|------|------|------|
| 段落挤在一起看不过来 | 默认 line-height 1.6 偏紧 | `line-height:2` 起；正文 17px 起 |
| 金句在两行以上时偏色不对齐 | 居中 + 长字符串过长 | 用 `<br>` 手断句，每行 ≤ 18 字 |
| 黑卡背景在某些安卓公众号里丢色 | 安卓版微信旧内核过滤 `background` 一些组合 | 用 `border:1px solid #111;background-color:#111111;` 兜底 |
| 标题三选一在 paste 进 135 编辑器后样式丢失 | 135 编辑器会重新解析 HTML | 在 135 里改用「样式中心 → 分隔线 + 强调文字」手动对齐；或直接接收样式丢失的事实 |
| 引用块左边线被吃掉 | 公众号会自动加 `padding-left` | 在 blockquote 上手动 `padding-left:14px;` 兜底 |
| 数据小卡显示成横排 | 想 4 个并排用了 flex | 改用堆叠 `<p>` 一行一个，或用 `<table>`（如果必须并排） |

---

## 5. 移动端 fallback 速查

万一公众号某版本编辑器过滤了某个 inline 样式，按下面这套降级方案重新替换：

| 被过滤样式 | 降级方案 |
|------|------|
| `border-left`（金色亮条） | 改用 `border:1px solid #b88a3a;` 全包 |
| `background`（黑卡 / 浅金底） | 用 `border-color` 加深 1px 视觉补偿，并保留文字色对比 |
| `border-radius` > 8px | 全部降到 4–6px |
| `letter-spacing` | 关掉，靠字号缩小换行缓解 |
| `text-align:center` | 改用 `<center>` 标签（老内核兼容更好） |

---

## 6. 一键试读 checklist（每次交付前跑一遍）

每篇 HTML 文件交付前，逐项 ✅：

- [ ] 无 `<style>` 块、无外联 CSS、无 grid/flex/transform/box-shadow/@media
- [ ] 全部样式 inline 在 `style="…"` 内
- [ ] 全文 font-size ≥ 15px，正文 17px
- [ ] 段落 line-height ≥ 1.85，正文 2
- [ ] 段间距 margin-bottom ≥ 14px，正文 18px
- [ ] 不在内容里写左右 padding
- [ ] 金句居中、加粗、color 主题色，至少出现 3 次
- [ ] 至少 1 处读者反驳（金边色块）
- [ ] 实操建议部分每个 case ≥ 80 字
- [ ] 结尾不出现「记住 / 你一定要 / 请务必 / 切记」
- [ ] 数据来源小字颜色 `#8a8a82`
- [ ] mobile 默念测试：手机宽 375px 下逐段读，无过密行、无长串断不开

---

## 7. 完整样本（GPT-6 那篇的 HTML 主干）

下面是用本指南全套样式产出的成品骨架，AI 可直接复用：

```html
<p style="font-size:13px;color:#b88a3a;letter-spacing:2px;margin-bottom:14px;">
  ◆ 商业洞察 · AI 前线观察
</p>

<p style="font-size:20px;font-weight:bold;color:#111;text-align:center;
          margin:14px 0 24px;line-height:1.45;">
  99.9% 和 62.7% 是同一周、同一台模型的两次跑分
</p>

<p style="font-size:16px;color:#b88a3a;font-weight:bold;margin:14px 0 10px;
          letter-spacing:1px;">
  ◆ 标题三选一
</p>

<p style="font-size:15.5px;line-height:1.85;color:#3d3d3d;margin-bottom:8px;">
  <b style="color:#b88a3a;">【悬念】</b>
  <b style="color:#111;">GPT-6 拿了个 99.9%，隔壁跑同一台模型只有 62.7%</b>
</p>
<p style="font-size:15.5px;line-height:1.85;color:#3d3d3d;margin-bottom:8px;">
  <b style="color:#b88a3a;">【利益】</b>
  GPT-6 真实用法：从"替你写"到"替你做完一整件事"
</p>
<p style="font-size:15.5px;line-height:1.85;color:#3d3d3d;margin-bottom:20px;">
  <b style="color:#b88a3a;">【对比】</b>
  OpenAI 喊 AGI 时代开幕，真正改变打工人命运的是另一组数字
</p>

<blockquote style="border-left:4px solid #b88a3a;background:#f7eed8;
                    padding:16px 20px;margin:18px 0 24px;border-radius:0 8px 8px 0;">
  <p style="font-size:12px;color:#b88a3a;font-weight:bold;letter-spacing:2px;
            margin-bottom:8px;">
    ◆ 摘 要
  </p>
  <p style="font-size:16px;line-height:1.9;color:#4a3a1a;margin:0;
            letter-spacing:0.5px;">
    99.9% 和 62.7% 是同一周、同一台模型的两次跑分。
    这 37.2% 的差别里，藏着这一代 AI 真正会改变你工作方式的入口。
  </p>
</blockquote>

<p style="background:#111111;color:#f1ece0;padding:20px 22px;
          margin:24px 0;border-left:4px solid #b88a3a;font-size:15.5px;
          line-height:1.95;letter-spacing:0.5px;">
  <span style="color:#b88a3a;font-weight:bold;letter-spacing:2px;font-size:12px;
               display:block;margin-bottom:8px;">
    ◆ 核 心 观 点
  </span>
  GPT-6 的发布，真正的分水岭不在那个 99.9% 的跑分，而在它能"替一个人
  把一整件事从头做到尾"。营销喊的 AGI 你可以不信，但能不能用它替代
  自己某个岗位——这一代人，得自己掂量清楚。
</p>

<p style="font-size:17px;line-height:2;color:#3d3d3d;margin:0 0 18px;
          letter-spacing:1.5px;">
  GPT-6 Astra，这个 9 月 3 日被 OpenAI 直接端上桌的旗舰模型，把整个中文科技圈炸了一夜。
  Greg Brockman 在发布会最后甩出一句"Welcome to the AGI era"，
  然后那张 99.9% 的 ARC-AGI-3 跑分图，一夜之间被转了无数次。
</p>

<h3 style="font-size:18.5px;color:#2f4a3a;font-weight:bold;margin:32px 0 14px;
           padding-left:12px;border-left:4px solid #2f4a3a;line-height:1.45;
           letter-spacing:0.5px;">
  一、跑分变 99.9% 不是奇迹，是把规则改了
</h3>

<p style="font-size:17px;line-height:2;color:#3d3d3d;margin:0 0 18px;
          letter-spacing:1.5px;">
  <b style="color:#111;">同一个模型，两个分数。</b>
  差就差在那个框架。它会保留推理状态、做长上下文压缩、在下一步操作时回看前面的所有痕迹。
  换句话说，你看到的那个 99.9%，有相当一部分是"Agent 操作系统"的功劳，不是裸模型的智力。
</p>

<blockquote style="border-left:3px solid #2f4a3a;background:#faf6ea;
                    padding:14px 18px;margin:22px 0;border-radius:0 6px 6px 0;
                    font-size:15.5px;line-height:1.9;color:#4a3a1a;">
  这事的本质是：模型在自适应推理框架下能达到 99.9%，说明它具备了非常强的"干中学"
  能力。但现实世界的开放性、噪音、长尾，跟一个封闭小游戏比，是两个量级。
</blockquote>

<p style="text-align:center;font-size:17px;color:#b88a3a;font-weight:bold;
          line-height:1.85;letter-spacing:1px;margin:22px 0;">
  以前 AI 帮你查个东西，你还得再花 5 分钟理解、过滤、二次提问。
  现在模型不仅给答案，还替你把二三次提问那部分工作一起做完了。
</p>

<p style="background:#f7eed8;border:1px dashed #b88a3a;padding:18px 22px;
          margin:28px 0 24px;font-size:15.5px;line-height:1.9;color:#5a4a26;
          border-radius:6px;">
  <span style="background:#b88a3a;color:#ffffff;font-size:12px;padding:2px 9px;
               border-radius:4px;display:inline-block;margin-bottom:10px;
               letter-spacing:1px;font-weight:bold;">
    ◆ 读 者 反 驳
  </span>
  <br>
  你可能在想：GPT-5.6 Sol 你都没用熟，API 价格涨了 2.5 倍，你给我吹这么神，
  是不是又一波噱头？——大多数打工人关心的是：这玩意儿落地到我这个岗位，
  到底能不能用上？
</p>

<section style="border:1px solid #e8e2d4;background:#fcfaf2;padding:18px 20px;
                 margin:16px 0 22px;border-radius:8px;">
  <p style="margin:0 0 8px;font-size:13px;color:#b88a3a;letter-spacing:1.5px;
            font-weight:bold;">
    ◆ 第一类 · 程序员
  </p>
  <p style="font-size:15.5px;line-height:1.9;color:#3d3d3d;margin:0 0 12px;
            letter-spacing:0.5px;">
    <b style="color:#111;">不在 IDE 里继续写新代码。</b>
    是把 GPT-6 接进你的运维值班流、code review、事故复盘文档。
  </p>
  <p style="font-size:15px;line-height:1.9;color:#5a5a52;margin:0;
            letter-spacing:0.5px;">
    同样是接一个新模块：A 的做法是，让 GPT-6 解释"这段代码为什么要这么写"，
    生成注释后存进 Confluence，下次 review 直接复用。B 的做法是，
    继续按过去习惯写，周末补一份"新人入门手册"，
    绝大多数情况这手册永远停在 draft 状态。
  </p>
</section>

<p style="font-size:17px;font-weight:bold;color:#111;line-height:1.7;
          margin:36px 0 14px;text-align:center;">
  你最近打算先让 GPT-6 替你干哪件具体的活儿？
</p>

<p style="font-size:15.5px;line-height:1.95;color:#3d3d3d;margin:0 0 22px;
          text-align:center;letter-spacing:0.5px;">
  评论区聊聊，挑几个有意思的接着拆 👇
</p>

<p style="font-size:13px;color:#8a8a82;line-height:1.85;margin:24px 0 4px;
          letter-spacing:0.5px;">
  <b style="color:#b88a3a;">◆ 数据来源</b>
</p>
<p style="font-size:13px;color:#8a8a82;line-height:1.85;margin:0 0 4px;">
  · 量子位 / 腾讯新闻《GPT-6 发布！105万上下文》
</p>
<p style="font-size:13px;color:#8a8a82;line-height:1.85;margin:0 0 4px;">
  · 腾讯新闻《跑分 99.9%、自主操作电脑》
</p>
<p style="font-size:13px;color:#8a8a82;line-height:1.85;margin:0 0 18px;">
  · OpenAI 官方：openai.com/index/gpt-6-astra/
</p>
```

---

## 8. 反 hand-waving 提醒

- **别给某个段落用 `style="width:80%"`**——这种百分比宽度在公众号里被忽略。
- **别用 emoji 代替角标**：用 `◆` 或 `·` 这种 Unicode 符号，公众号 100% 兼容；如果用户特别要看 emoji，emoji 也能识别，但要写在 <p> 内、不能当 color-icon 用。
- **图片别嵌入 base64**：微信公众号编辑器不接受内联 base64，所有图片必须用 https 图床地址（OSS / COS / S3 公开 URL）。
- **慎用 `nowrap` 和 `white-space`**：微信公众号编辑器对这两个属性的处理不稳定，宁可手动断句也别强不断行。

---

**最后一句**：整套 HTML 完成后，建议在 PC 浏览器打开一次 `gpt6-wechat.html`，确认结构无误；再用 135 编辑器或公众号后台的"HTML 模式"粘贴走一遍。两个环境都过，才能算交付。
