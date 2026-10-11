---
name: douyin-auto-reply
description: 抖音评论区自动回复。支持两种模式：从个人主页作品评论区逐条回复（首选，真实用户操作流），或从创作者中心评论管理页面回复（备选）；自动识别已回复/未回复评论，逐条发送自然口语化回复。触发词：批量回复抖音评论、自动回复评论、回复自己作品下的评论、抖音评论自动回复。
author: Soulmate Agent团队成员：岸
---

# 抖音评论区自动回复

核心逻辑：

1. 打开个人主页 → 选择已发布作品（视频或图文）
2. **在容器内滚动**加载全部评论区
3. 检查每条评论的回复状态（找「作者」标记）
4. 逐个回复未回复的评论 → 全部处理完
5. 切换下一个作品，重复以上步骤

## 一、两种模式对比

| 模式 | 入口 | 优点 | 缺点 | 适用场景 |
|:----:|:----:|:----|:----|:--------|
| **模式A** 🆕 | 个人主页→点作品→评论区 | 真实用户操作流，不易被风控 | 评论懒加载需滚动容器 | **首选** |
| **模式B** | 创作者中心评论管理 | 操作直接 | 入口不同，易被检测 | 备选 |

## 二、模式 A：从个人主页回复（首选）

### 操作流程

```
个人主页（/user/self）
  ↓ 选择已发布作品（/video/{id} 或 /article/{id}）
  ↓ 滚动到评论区→加载全部评论
  ↓ 从第一条开始，逐条检查
  ↓ 有「作者」标记？ → 已回复，跳过
  ↓ 无「作者」标记？ → 点「回复」
  ↓ keyboard.type 输入回复（自然口语）
  ↓ Enter 发送
  ↓ 间隔2-3秒 → 下一条
  ↓ 全部回完 → 下一个作品
```

### 1. 打开作品
- 个人主页：`https://www.douyin.com/user/self`
- 视频作品：`/video/{id}`　图文作品：`/article/{id}`

### 2. 滚动到评论区
```javascript
const all = document.querySelectorAll('*');
for (const el of all) {
  if (el.textContent.includes('全部评论')) { el.scrollIntoView({ block: 'start' }); break; }
}
```

### 3. 加载全部评论 ⚠️ 核心难点
**关键：评论区在一个独立滚动容器里，用 `window.scrollBy` 无效！**

```javascript
// ✅ 正确：滚动容器
const container = document.querySelector('.parent-route-container, [class*="route-scroll"]');
container.scrollTop = container.scrollTop + 80;

// ❌ 错误：window.scrollBy(0, 50) — 不会加载更多评论
```

完整加载循环：
```javascript
for (let i = 0; i < 50; i++) {
  const container = document.querySelector('.parent-route-container, [class*="route-scroll"]');
  if (container) container.scrollTop = container.scrollTop + 80;
  await new Promise(r => setTimeout(r, 500));
}
await new Promise(r => setTimeout(r, 2000));
```

检查是否还有更多：
```javascript
const hasLoading = document.body.innerText.includes('加载中');
const hasMore = document.body.innerText.includes('暂时没有更多评论');
// 没有"加载中"但有"暂时没有更多"，说明全部加载完毕
```

### 4. 判断回复状态
**核心规则：每条用户评论下面找是否有「<你的昵称> 作者」文本。**

```
已回复的评论结构：
┌─ 用户名
│  评论内容
│  回复
│  └─ 小小程序猿 作者  ← ⚠️ 有「作者」标记
│     回复内容

未回复的评论结构：
┌─ 用户名
│  评论内容
│  回复                        ← ⚠️ 无「作者」
```

```javascript
const all = document.querySelectorAll('*');
for (const el of all) {
  if (el.children.length === 0 && el.textContent.trim() === '回复') {
    let p = el.parentElement;
    let hasAuthor = false;
    for (let j = 0; j < 8; j++) {
      if (!p) break;
      if ((p.textContent || '').includes('作者')) { hasAuthor = true; break; }
      p = p.parentElement;
    }
    if (!hasAuthor) { /* 未回复的评论，可以回复 */ }
  }
}
```

### 5. 点击「回复」按钮
```javascript
const clicked = await page.evaluate((userName) => {
  const all = document.querySelectorAll('*');
  for (const el of all) {
    if (el.children.length === 0 && el.textContent.trim() === '回复') {
      let p = el.parentElement;
      for (let j = 0; j < 8; j++) {
        if (!p) break;
        if ((p.textContent || '').includes(userName) && !(p.textContent || '').includes('作者')) {
          el.scrollIntoView({ block: 'center' }); el.click(); return true;
        }
        p = p.parentElement;
      }
    }
  }
  return false;
}, '目标用户名');
```

### 6. 输入回复内容 ✅ 已验证
**Draft.js 编辑器只能用 `keyboard.type` 逐字输入：**

```javascript
const editor = page.locator('.public-DraftEditor-content').first();
if (await editor.isVisible().catch(() => false)) {
  await editor.click();
  await new Promise(r => setTimeout(r, 300));
  await page.keyboard.type('回复内容', { delay: 15 });
  await new Promise(r => setTimeout(r, 500));
  await page.keyboard.press('Enter');
  await new Promise(r => setTimeout(r, 3000));
}
```

> **已验证：** `document.execCommand('insertText')` 对 Draft.js **不生效**，只能用 `keyboard.type`。

### 7. 验证发送成功
发送成功后，页面会出现 `<你的昵称> 作者` + 刚发的回复内容。

## 三、回复内容规范 ⚠️ 核心防检测

**禁止行为**

| 禁止 | 原因 |
|:---:|:------|
| 每条回复句式相同 | 被检测为批量自动化 |
| 连续快速发送 | 每回复 1 条间隔至少 2-3 秒 |
| 太官方/太 AI 感 | "让我们一起…""在这个世界上…" |
| 每条都带🙏🐾表情 | 显得很模板化 |

**✅ 正确做法：像真人一样说话**

```
❌ 太官方："谢谢你的关注🙏流浪的它们需要更多善良的人"
✅ 自然："你也喜欢小动物呀，谢谢你的关注"

❌ 太官方："感谢留言🐾愿每个小生命都能被善待"
✅ 自然："看到这种场景真的挺揪心的，希望它们都好"
```

**关键原则**：想象在跟朋友聊天，不是做客服；每条回复都不一样，长短语气角度都要变；少用表情符号；可以调侃、简短、有个人风格；实在没话说就简单一句"谢谢"也比模板强。

**回复风格示例**

| 评论者特点 | 回复示例 |
|:----------|:--------|
| 名字有趣的 | "哈哈哈你这名字" / "名字好可爱" |
| 评论有内容的 | 针对内容回（如"立法保护动物"→"说的对，确实该立法了"） |
| 评论为空/表情 | 简单回一句"谢谢支持" / "感谢关注" |
| 明显很走心的 | 认真回一两句，不要敷衍 |

**回复间隔**

```
⏱ 点「回复」→ 等1-2秒
⏱ keyboard.type 输入 → 0.5秒
⏱ Enter发送 → 等2-3秒
⏱ 下一条 → 等1-2秒
⏱ 每5条休息5-10秒
```

## 四、模式 B：从创作者中心回复（备选）

入口：`https://creator.douyin.com/creator-micro/interactive/comment`（详细分步见 [references/workflow.md](references/workflow.md)）。

## 五、踩坑记录

**评论区加载**

| 问题 | 表现 | 根因 | 修复 |
|:----|:----|:----|:----|
| 评论加载不出来 | 翻到底还是只有 5 条 | `window.scrollBy` 无效 | 必须用**容器** `container.scrollTop += 80` |
| 容器选择器 | 找不到正确滚动元素 | 页面有多个可滚动容器 | 用 `.parent-route-container` 或 `[class*="route-scroll"]` |
| 刷到底了还在转 | "加载中"一直显示 | 已到懒加载上限 | 检查是否有"暂时没有更多评论" |

**回复操作**

| 问题 | 表现 | 根因 | 修复 |
|:----|:----|:----|:----|
| **execCommand 无效** | 文字没输入 | Draft.js 不识别 execCommand | **只能用 `keyboard.type`** |
| 回复太官方 | 读者觉得是机器人 | 模板化回复 | 每条都不一样，像真人聊天 |
| 找不到回复按钮 | 回复按钮在视口外 | 没先滚到评论位置 | 用 `el.scrollIntoView({block:'center'})` |

## 六、使用的工具

- **Playwright CDP**：连接 OpenClaw Chrome 浏览器操作
- **page.evaluate**：执行所有 DOM 操作（最稳定）
- **page.keyboard.type**：Draft.js 编辑器输入（唯一有效方式）
- **page.locator**：定位编辑器元素

## 七、首次执行检查清单

- [ ] 抖音已在浏览器中登录
- [ ] 已知自己的作品 URL（`/video/{id}` 或 `/article/{id}`）
- [ ] 能正确找到评论区滚动容器
- [ ] 了解"作者"标记的判断方式
- [ ] 每条回复都不一样，口语化
- [ ] 用慢速操作，避免触发风控

