# 抖音自动回复评论 · 完整工作流（v2.0）

> 2026-05-12 实战验证。使用 OpenClaw 内置浏览器（`browser.*` 工具）。

---

## 一、进入评论管理

```javascript
browser.navigate("https://creator.douyin.com/creator-micro/interactive/comment")
browser.wait(2000)
```

## 二、选择目标作品

评论管理默认显示最新作品。最新作品通常是刚发布的（定时），可能没有评论。

```javascript
// 1. 点击「选择作品」
browser.snapshot()
browser.click(ref)  // 找到「选择作品」按钮 ref
browser.wait(1500)

// 2. 在弹窗中找到有评论数量的文章
//    inspect 页面找到包含目标文章标题的可点击元素
//    优先选评论数 > 0 的文章
browser.evaluate(`() => {
  const el = Array.from(document.querySelectorAll('*')).find(el =>
    el.offsetParent && el.textContent.includes('目标文章标题关键词') && window.getComputedStyle(el).cursor === 'pointer'
  );
  if (el) { el.click(); return 'clicked'; }
  return 'not found';
}`)
browser.wait(1500)
```

**选择作品的判断**：
- 优先选已发布且评论数 > 0 的文章
- 定时/新发布的文章通常没有评论
- 从作品列表中可以看每篇文章的评论数量

## 三、识别未回复评论

判断方法：
- **已回复特征**：评论下方有「小小程序猿🐒 作者」的子回复区域
- **未回复特征**：评论下方只有「回复」「删除」「举报」按钮，没有作者回复

```javascript
// 查看页面有多少条评论
// 如果显示「暂无更多评论」= 没有评论
// 检查每条评论是否已有作者回复
```

## 四、逐条回复未回复评论 ⚠️ 关键步骤

### Step 1: 点击「回复」按钮

```javascript
// 用 ref 点击（不要用 evaluate 查找）
browser.snapshot()
browser.click(replyRef)  // 找到该评论的「回复」按钮 ref
browser.wait(1000)
```

### Step 2: 在回复框中填入内容 ⚠️ 易错

```javascript
// ✅ 正确方式：execCommand('insertText') — React 会检测到
browser.evaluate(`() => {
  const inputs = document.querySelectorAll('[contenteditable]');
  const target = inputs[inputs.length - 1];
  if (target && target.offsetParent) {
    target.focus();
    document.execCommand('insertText', false, '你的回复内容');
    target.dispatchEvent(new Event('input', {bubbles:true}));
    return 'typed';
  }
  return 'no target';
}`)

// ❌ 错误方式：innerHTML — React 不会检测到，发送按钮保持禁用！
// inputs[lastIndex].innerHTML = '内容'  ← 没用！
```

### Step 3: 点击「发送」按钮

```javascript
browser.evaluate(`() => {
  const btns = document.querySelectorAll('button');
  for (const btn of btns) {
    if (btn.offsetParent && btn.textContent.trim() === '发送' && !btn.disabled) {
      btn.click();
      return 'sent';
    }
  }
  return 'no enabled send';
}`)
// 返回 'sent' = 发送成功
// 返回 'no enabled send' = 内容没填上或按钮不可用
```

### Step 4: 重复直到所有未回复评论处理完毕

每次回复后等 1 秒，然后检查是否还有未回复的「回复」按钮。如果没有新的「回复」按钮，说明全部处理完毕。

## 五、回复内容参考（实际案例）

| 评论 | 回复内容 |
|------|---------|
| "hermes的记忆很强" | "哈哈谢谢！Hermes的记忆确实强，长对话也能记住上下文" |
| "这个和openclaw比起来那个更实用" | "Hermes偏智能体对话，OpenClaw偏工具链集成。做AI对话用Hermes，做自动化工作流用OpenClaw更合适" |
| "这个都可以干什么，能解释一下吗" | "主要能做智能对话、任务规划、代码生成这些，像个AI助手一样帮你干活。具体可以看看我之前发的OpenClaw那篇" |

**回复风格要点**：
- 要自然，像真人在说话
- 不要用模板套话
- 技术问题给具体答案
- 可以引导看其他文章

## 六、常见问题

### Q: 内容填了但发送按钮一直是禁用状态
**原因**：用了 `innerHTML` 或 value setter。抖音回复框是 React 组件，只识别通过键盘/`execCommand` 的输入。
**解决**：用 `document.execCommand('insertText', false, text)`。

### Q: 回复发成了独立评论而不是子回复
**原因**：点的是主输入框（"有爱评论，说点好听的~"）而不是「回复」按钮。
**解决**：找到「回复」按钮（在每条评论下方）点击它，才会出现子回复框。

### Q: 弹出了身份验证弹窗
**原因**：抖音安全机制，检测到批量操作。
**解决**：用户手动完成短信验证或扫码验证后继续。

### Q: 页面显示「暂无更多评论」但管理页显示有评论数
**原因**：可能选择了错误的文章（定时文章没有评论）或需要刷新。
**解决**：点「选择作品」切换到已发布的文章。

### Q: 删错了评论
**原因**：误点了删除确认。
**解决**：目前无法恢复。操作前仔细看要删的是子回复还是主评论。

### Q: 浏览器断开
```javascript
// 重启浏览器
openclaw browser stop
openclaw browser start
// 重新导航到目标页面
```

## 七、完整示例

```
1. navigate(评论管理页)
2. snapshot → click(选择作品) → wait → 找到有评论的文章并点击 → wait
3. 检查页面：看到 3 条评论，都没有作者回复 → 未回复 ✅
4. click(第一条评论的「回复」按钮) → wait
5. evaluate: execCommand('insertText') 填内容
6. evaluate: 点 enabled 的「发送」按钮
7. wait 1秒
8. click(第二条评论的「回复」按钮) → wait
...重复直到全部回复完毕
9. 完成 ✅
```
