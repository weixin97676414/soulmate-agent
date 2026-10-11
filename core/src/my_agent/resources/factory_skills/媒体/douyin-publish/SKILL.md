---
name: douyin-publish
description: 抖音全类型作品自动发布，覆盖文章（≤8000 字）、图文（1-35 张图）、视频（≤16GB/≤60min）三种类型，支持 AI 封面、话题添加、背景音乐、自主声明与定时发布。当用户要发布抖音作品、自动发布抖音内容、定时发布抖音、上传抖音视频/图文时触发。基于多轮真实测试验证。
author: Soulmate Agent团队成员：岸
---

# 抖音全类型自动发布

> ⚠️ 基于多轮真实测试验证通过，覆盖文章/图文/视频三种类型。

## 📦 支持的类型

| 类型 | 适用场景 | 发布方式 | 流程步数 | 状态 |
|------|---------|---------|:--------:|:----:|
| 📝 **文章** | 长文内容(≤8000字) | 脚本一键 | 8 步 | ✅ 稳定 |
| 🖼️ **图文** | 图片+文字(≤1000字) | 浏览器操作 | 10 步 | ✅ 稳定 |
| 🎬 **视频** | 视频(≤16GB/≤60min) | 浏览器操作 | 8 步 | ✅ 稳定 |

## 🔧 环境要求

- **OpenClaw CDP Chrome 浏览器**（所有类型都需要）
  - 启动命令：`openclaw browser start`
  - CDP 端口：18800（`http://127.0.0.1:18800`）
  - 推荐 headed 模式（可见浏览器操作过程）
  - 登录态通过 cookie 持久化，首次需扫码
- 文章额外要求：**Playwright**（npm 全局安装）、**Node.js**、脚本 [scripts/douyin-publish.cjs](scripts/douyin-publish.cjs)
- 图文/视频额外要求：无（直接用浏览器操作）

## 👤 账号要求

- 拥有抖音账号
- 已在 `creator.douyin.com` 登录（首次需扫码）
- 登录态保持（cookie 持久化，重启浏览器后需重新扫码）
- 账号没有被封禁发布权限

## 🎬 素材准备

| 发布类型 | 需要的素材 | 格式 | 存放位置 |
|---------|-----------|------|---------|
| 📝 文章 | 头图 + 封面 各 1 张 | jpg/png | 任意路径→拷贝到 `/tmp/openclaw/uploads/` |
| 🖼️ 图文 | 1-35 张图片 | jpg/png/webp | 任意路径→拷贝到 `/tmp/openclaw/uploads/image_XX.jpg` |
| 🎬 视频 | 1 个视频文件 | mp4/webm | 任意路径 |

素材来源：**Pexels** 免费图库直链或本地文件；内容可由 AI 根据主题生成。

```bash
curl -sL --max-time 8 -H "Referer: https://www.pexels.com/" \
  -o /path/to/output.jpg \
  "https://images.pexels.com/photos/{id}/pexels-photo-{id}.jpeg?cs=srgb&fm=jpg"
# 视频下载：https://videos.pexels.com/video-files/{id}/{filename}.mp4
```

## 🔄 通用操作（所有类型通用）

### 连接浏览器
```javascript
const { chromium } = require('playwright');
const { execSync } = require('child_process');

const cdpHttp = 'http://127.0.0.1:18800';
const ver = JSON.parse(execSync(`curl -s ${cdpHttp}/json/version`).toString());
const browser = await chromium.connectOverCDP(ver.webSocketDebuggerUrl);
const context = browser.contexts()[0];
for (const p of context.pages()) {
  if (p.url().includes('creator.douyin.com')) await p.close();
}
```

### 填标题（React input）
```javascript
const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
const ti = document.querySelector('input[placeholder*="标题"]');
setter.call(ti, '标题内容');
ti.dispatchEvent(new Event('input', { bubbles: true }));
```

### 添加话题
```javascript
for (const topic of ['话题1', '话题2', '话题3']) {
  await page.evaluate(() => {
    for (const btn of document.querySelectorAll('.toolbar-button-spPS4r'))
      if (btn.textContent.includes('话题')) btn.click();
  });
  await new Promise(r => setTimeout(r, 300));
  await page.keyboard.type(topic, { delay: 10 });
  await new Promise(r => setTimeout(r, 1500));
  await page.evaluate(() => {
    const el = document.querySelector('.tag-dVUDkJ.tag-hash-o0tpyE');
    if (el) el.click();
  });
  await new Promise(r => setTimeout(r, 500));
}
```

### 设置自主声明
```javascript
await page.evaluate(() => window.scrollTo(0, 600));
await new Promise(r => setTimeout(r, 300));
await page.evaluate(() => { const sb = document.querySelector('.selectBox-buZRzi'); if (sb) sb.click(); });
await new Promise(r => setTimeout(r, 1500));
await page.evaluate(() => {
  const modals = document.querySelectorAll('.semi-modal');
  for (let i = 0; i < modals.length; i++) {
    if (modals[i].textContent.includes('内容由AI生成')) {
      const labels = modals[i].querySelectorAll('label, .semi-radio');
      for (let j = 0; j < labels.length; j++)
        if (labels[j].textContent.includes('内容由AI生成')) { labels[j].click(); break; }
      const btns = modals[i].querySelectorAll('button');
      for (let j = 0; j < btns.length; j++)
        if (btns[j].textContent.includes('确定')) btns[j].click();
    }
  }
});
```

### 设置定时发布
```javascript
await page.evaluate(() => window.scrollTo(0, 1200));
await new Promise(r => setTimeout(r, 200));
const all = document.querySelectorAll('span, div, label');
for (const el of all) if (el.textContent.trim() === '定时发布') { el.click(); break; }
await new Promise(r => setTimeout(r, 1500));
const inputs = document.querySelectorAll('input');
for (const inp of inputs) {
  if (inp.placeholder === '日期和时间') {
    const s = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    s.call(inp, '2026-06-04 19:00');
    inp.dispatchEvent(new Event('input', { bubbles: true }));
    inp.dispatchEvent(new Event('change', { bubbles: true }));
    break;
  }
}
```

### 点击发布按钮
```javascript
const btns = document.querySelectorAll('button');
for (const btn of btns) if (btn.textContent.trim() === '发布') { btn.click(); break; }
```

## 📝 文章发布流程（脚本一键，8 步）

适用：长文 ≤8000 字，含头图 + 封面 + 话题 + 配乐。

1. **写文章内容**：标题 ≤30 字；摘要 ≤30 字；正文 HTML 用 `<p>`+`<strong>`+`<p></p>` 分段；话题 3-5 个。
2. **准备图片**：下载头图 + 封面到 `/tmp/openclaw/uploads/`（见素材准备）。
3. **修改脚本配置**：编辑 [scripts/douyin-publish.cjs](scripts/douyin-publish.cjs) 的 CONFIG 区：

```javascript
const CONFIG = {
  PUBLISH: true,
  TYPE: 'article',  // article | image | video
  TITLE: '标题（≤30字）',
  SUMMARY: '摘要（≤30字）',
  BODY: '<p>正文HTML</p>',
  TOPICS: ['话题1', '话题2', '话题3'],
  MUSIC_KEYWORD: '纯音乐',
  SCHEDULED_TIME: '2026-06-04 19:00',
  PEXELS_PHOTOS: [],
};
```

4. **运行发布**：

```bash
NODE_PATH=~/.npm-global/lib/node_modules node scripts/douyin-publish.cjs --type=article --publish
```

脚本执行步骤：①准备图片 ②连接 CDP Chrome ③打开文章编辑器 `/content/post/article?type=new` ④填标题+摘要+正文 ⑤上传头图+封面（fileChooser）⑥添加话题（弹窗搜索→点选→确认）⑦添加配乐（点`选择音乐`→搜`纯音乐`→点`使用`）⑧定时/立即发布。

**关键选择器**

| 元素 | 选择器 | 操作 |
|------|--------|------|
| 标题输入 | `input[placeholder*="标题"]` | `nativeInputValueSetter` |
| 摘要输入 | `input[placeholder*="摘要"]` | `nativeInputValueSetter` |
| 正文编辑区 | `[contenteditable]` | `innerHTML` 注入 |
| 上传头图 | 文本"点击上传图片" | 先 `waitForEvent('filechooser')` 再 click |
| 上传封面 | 文本"点击上传封面图" | 同上 |
| 话题弹窗搜索 | `input[placeholder*="搜索"]` | 填关键词 |
| 话题选项 | `.topicName-Nd8EPd` | 点击选择 |
| 配乐按钮 | `.action-Q1y01k` | 点击打开侧栏 |
| 配乐搜索 | `input[placeholder="搜索音乐"]` | `nativeInputValueSetter` |
| 配乐使用 | `.apply-btn-LUPP0D` | 三设 display/visibility/opacity 后点击 |
| 配乐侧栏遮罩 | `.semi-sidesheet-mask` | 点击关闭 |

## 🖼️ 图文发布流程（浏览器分步，10 步）

适用：图片+文字 ≤1000 字，1-35 张图，含封面 + 话题 + 配乐。

1. **打开全新编辑器**（加随机参数避免草稿残留）：
```javascript
await page.evaluate(() => { window.onbeforeunload = null; });
await page.goto('https://creator.douyin.com/creator-micro/content/post/image?type=new&_=' + Date.now());
```
2. **上传图片**：
```javascript
const fc = page.waitForEvent('filechooser', { timeout: 20000 });
const screen = await page.evaluate(() => {
  const el = document.querySelector('.phone-screen-emLY2d');
  const r = el.getBoundingClientRect();
  return { x: r.x, y: r.y };
});
await page.mouse.click(screen.x + 121, screen.y + 287);
await (await fc).setFiles(imageFiles);
```
> 验证：页面出现「已添加X张图片」文本。
3. **填标题**：`nativeInputValueSetter` 填 title input（≤20 字）。
4. **填描述**（Slate.js，必须逐字输入，不能用 `innerHTML`）：
```javascript
const editable = page.locator('[contenteditable]').first();
await editable.click();
await page.keyboard.press('Meta+a');
await page.keyboard.press('Backspace');
await page.keyboard.type('描述内容...', { delay: 3 });
```
5. **添加话题**（见通用操作）。
6. **设置封面**：
```javascript
await page.evaluate(() => {
  const ec = document.querySelector('[class*=mycard-info-text]');
  if (ec && ec.textContent.includes('编辑封面')) ec.click();
});
await page.evaluate(() => { const imgs = document.querySelectorAll('img[src*="tos-cn-i"]'); if (imgs.length > 0) imgs[0].click(); });
await page.evaluate(() => { for (const b of document.querySelectorAll('button')) if (b.textContent.includes('确定')) b.click(); });
```
7. **自主声明**（见通用操作）。
8. **配乐**：点 `.action-Q1y01k` → 搜`纯音乐` → 点 `.apply-btn-LUPP0D`（三设 display/visibility/opacity 后点击）。
9. **关配乐侧栏 + 定时发布**：点 `.semi-sidesheet-mask` 或 Escape 关侧栏，再设定时发布。
10. **发布**。

**关键选择器**

| 元素 | 选择器 | 操作 |
|------|--------|------|
| 手机预览区 | `.phone-screen-emLY2d` | 点击上传 |
| 标题输入 | `input[placeholder*="标题"]` | `nativeInputValueSetter` |
| 描述编辑区 | `[contenteditable]` | `keyboard.type` |
| 话题按钮 | `.toolbar-button-spPS4r` text="添加话题" | `element.click()` |
| 话题建议项 | `.tag-dVUDkJ.tag-hash-o0tpyE` | `element.click()` |
| 封面编辑 | 文本"编辑封面" | 点击→跳转 poster 页 |
| 声明下拉 | `.selectBox-buZRzi` | 点击打开弹窗 |
| 配乐按钮 | `.action-Q1y01k` | 点击打开侧栏 |
| 配乐使用 | `.apply-btn-LUPP0D` | 三设后点击 |
| 侧栏遮罩 | `.semi-sidesheet-mask` | 点击关闭 |
| 定时发布 | 文本"定时发布" | 点击 |
| 时间输入 | `input[placeholder="日期和时间"]` | `nativeInputValueSetter` |

## 🎬 视频发布流程（浏览器分步，8 步）

适用：视频 ≤16GB/≤60min，含标题 + 话题 + 声明，**跳过封面设置，不配乐**。

1. **上传视频**：
```javascript
await page.goto('https://creator.douyin.com/creator-micro/content/upload');
await page.waitForTimeout(3000);
await page.setInputFiles('input[type="file"]', '/path/to/video.mp4');
await new Promise(r => setTimeout(r, 15000));
```
2. **等 AI 封面生成（跳过，不选封面）**。
3. **填标题**：`nativeInputValueSetter`（≤30 字）。
4. **填描述**（Slate.js，用 `execCommand('insertText')`）：
```javascript
const ed = document.querySelector('[contenteditable]');
if (ed) { ed.focus(); document.execCommand('insertText', false, '描述内容...'); }
```
5. **添加话题**（见通用操作）。
6. **跳过封面设置**（不点击横/竖封面区域）。
7. **自主声明**（见通用操作）。
8. **定时发布 + 发布**（见通用操作）。

**关键选择器**

| 元素 | 选择器 | 操作 |
|------|--------|------|
| 视频上传 | `input[type="file"]` | `setInputFiles` |
| 标题输入 | `input[placeholder*="标题"]` | `nativeInputValueSetter` |
| 描述编辑区 | `[contenteditable]` | `execCommand('insertText')` |
| 话题按钮 | `.toolbar-button-spPS4r` | `element.click()` |
| 话题建议项 | `.tag-dVUDkJ.tag-hash-o0tpyE` | `element.click()` |
| 声明下拉 | `.selectBox-buZRzi` | 点击打开弹窗 |
| 定时发布 | 文本"定时发布" | 点击 |
| 时间输入 | `input[placeholder="日期和时间"]` | `nativeInputValueSetter` |
| 横封面区域 | `.cover-Jg3T4p` | ❌ 不点击（跳过） |

## 📋 三类型对比

| 项目 | 📝 文章 | 🖼️ 图文 | 🎬 视频 |
|------|--------|--------|--------|
| 编辑页URL | `/content/post/article` | `/content/post/image` | `/content/upload`→跳转 |
| 发布方式 | 脚本一键 | 浏览器分步 | 浏览器分步 |
| 标题字数 | ≤30字 | ≤20字 | ≤30字 |
| 正文字数 | ≤8000字 | ≤1000字 | 不限 |
| 图片上传 | 头图+封面分开 | 批量 1-35 张 | 不需要 |
| 视频上传 | 不需要 | 不需要 | 1 个文件 |
| 封面设置 | 上传或 AI | 从图中选 | ❌ 跳过（默认 AI） |
| 话题添加 | 弹窗搜索选择 | 弹窗搜索选择 | 弹窗搜索选择 |
| 配乐 | ✅ 搜索纯音乐 | ✅ 搜索纯音乐 | ❌ 跳过 |
| 随机参数避草稿 | 不需要 | ✅ 需要 `&_=时间戳` | 不需要 |
| beforeunload | 不处理 | ✅ navigate 前 null | ✅ navigate 前 null |
| 预估用时 | 25-30 秒 | 30-40 秒 | 25-30 秒 |

## ❗ 常见问题

**通用**
1. 浏览器连不上（`Browser context management is not supported`）→ `openclaw browser stop && openclaw browser start`
2. CDP 端口不通 → 确保 OpenClaw browser 正在运行
3. 登录态丢失（显示扫码）→ 手动扫码一次，cookie 持久化

**文章**
4. 配乐侧栏打不开 → 先 evaluate 滚动到配乐区域，再 retry 5 次点击
5. 配乐"使用"按钮不可见 → evaluate 修改 display/visibility/opacity 三属性

**图文**
6. filechooser 超时 → 先 `waitForEvent('filechooser')` 再 click，用 `page.mouse.click(x,y)`
7. 图片上传后预览无变化 → 等 4-5 秒渲染，检查"已添加X张图片"
8. 封面编辑器不返回 → 等 2-3 秒自动回跳，或用 `page.goBack()`

**视频**
9. 视频处理超时 → 等待 15 秒以上
10. 不需要设置封面 → 默认不操作封面区域

## 🐛 踩坑记录

| # | 坑 | 症状 | 解决 |
|:--:|-----|------|------|
| 1 | 图文草稿残留 | 打开编辑页显示旧内容 | URL 加 `&_=时间戳` |
| 2 | Slate 编辑器 innerHTML | 内容消失 | 用 `keyboard.type` 或 `execCommand('insertText')` |
| 3 | 话题点不上 | 点击无反应 | 用 `element.click()` 原生方法点 `.tag-dVUDkJ` |
| 4 | 话题上限 5 个 | 超出后点不上 | 删草稿重新发布 |
| 5 | 配乐侧栏挡发布按钮 | 发布按钮点不动 | 配乐后关 mask 或 Escape |
| 6 | 定时时间写进标题 | 标题变成时间字符串 | 只改 `placeholder="日期和时间"`，不碰标题 input |
| 7 | `for...of` 变量冲突 | evaluate 报错 `m is not defined` | 用传统 `for` 循环 |
| 8 | 封面确认弹窗未处理 | 后续声明弹窗错乱 | 选封面后必须点确定 |
| 9 | Pexels 图混入猫/兔子 | 图片内容不对 | 下载后用 image 工具确认 |
| 10 | 浏览器关闭后页面丢失 | 草稿没保存 | 保持浏览器打开，或抖音会自动存草稿 |

