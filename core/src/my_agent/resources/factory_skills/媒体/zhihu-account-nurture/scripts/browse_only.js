// browse_only.js — 禁言期只读浏览（不点赞/不收藏/不关注/不评论/不发布）
// 用途：账号被限流或禁言期间维持真实活跃度，只做「看」的动作。
// 用法：ego-browser nodejs < scripts/browse_only.js
// 可选参数文件 /tmp/zhihu_browse_params.json：
//   { "minutes": 6, "pages": 4, "keywords": ["历史","心理"] }
//   默认：6 分钟、读 4 个问题页、关键词取趣味历史/人文心理常用词
// 安全约束（写死）：全程零点击互动——只 openOrReuseTab / 滚动 / 停留。
(async () => {
  const fs = require('fs')
  let P = {}
  try { P = JSON.parse(fs.readFileSync('/tmp/zhihu_browse_params.json', 'utf8')) } catch (e) {}
  const minutes = Number(P.minutes) > 0 ? Number(P.minutes) : 6
  const maxPages = Number(P.pages) > 0 ? Number(P.pages) : 4
  const keywords = Array.isArray(P.keywords) && P.keywords.length
    ? P.keywords
    : ['历史', '朝代', '古人', '典故', '心理', '人性', '关系', '代际']
  const deadline = Date.now() + minutes * 60 * 1000

  const space = 'zhihu-browse-only'
  const task = await useOrCreateTaskSpace(space)
  cliLog('BROWSE_START minutes=' + minutes + ' pages=' + maxPages + ' mode=READ_ONLY')

  // 1) 热榜：滚动浏览 + 停留
  await openOrReuseTab('https://www.zhihu.com/hot', { wait: true, timeout: 25 })
  await wait(6)
  for (let i = 0; i < 3; i++) {
    await js('window.scrollBy(0, ' + (300 + Math.floor(Math.random() * 400)) + ')')
    await wait(6 + Math.floor(Math.random() * 8))
  }
  cliLog('BROWSE_STEP hot-list done, url=' + (await js('location.href')))

  // 2) 选与垂直领域相关的问题（只看标题，不点任何互动按钮）
  const picks = await js('((kws) => {'
    + ' const items = Array.from(document.querySelectorAll(".HotItem"));'
    + ' const out = [];'
    + ' for (const it of items) {'
    + '   const t = (it.innerText || "");'
    + '   if (kws.some(function (k) { return t.indexOf(k) >= 0; })) {'
    + '     const a = it.querySelector("a");'
    + '     if (a && a.getAttribute("href")) out.push(a.getAttribute("href"));'
    + '   }'
    + ' }'
    + ' return out.slice(0, 3);'
    + '})(' + JSON.stringify(keywords) + ')')
  cliLog('BROWSE_PICKED: ' + JSON.stringify(picks))

  const urls = Array.isArray(picks) ? picks.slice(0, Math.max(0, maxPages - 1)) : []
  if (!urls.length) cliLog('BROWSE_NOTE: 热榜无垂直领域命中，退化为首页推荐流浏览')
  if (!urls.length) urls.push('https://www.zhihu.com/')

  for (let i = 0; i < urls.length; i++) {
    if (Date.now() > deadline) { cliLog('BROWSE_DEADLINE hit, stop early'); break }
    const u = urls[i].indexOf('http') === 0 ? urls[i] : ('https://www.zhihu.com' + urls[i])
    await openOrReuseTab(u, { wait: true, timeout: 25 })
    await wait(7)
    const dwell = 35 + Math.floor(Math.random() * 45)
    const steps = Math.max(2, Math.floor(dwell / 12))
    for (let s = 0; s < steps; s++) {
      if (Date.now() > deadline) break
      await js('window.scrollBy(0, ' + (250 + Math.floor(Math.random() * 350)) + ')')
      await wait(8 + Math.floor(Math.random() * 6))
    }
    cliLog('BROWSE_PAGE ' + (i + 1) + '/' + urls.length + ' dwell≈' + dwell + 's url=' + u)
  }

  // 3) 回首页信息流再看一会儿
  if (Date.now() < deadline) {
    await openOrReuseTab('https://www.zhihu.com/', { wait: true, timeout: 25 })
    await wait(8)
    const rest = Math.min(90, Math.max(20, Math.floor((deadline - Date.now()) / 1000)))
    for (let s = 0; s < Math.max(2, Math.floor(rest / 15)); s++) {
      await js('window.scrollBy(0, ' + (300 + Math.floor(Math.random() * 400)) + ')')
      await wait(9 + Math.floor(Math.random() * 6))
    }
    cliLog('BROWSE_STEP home-feed done')
  }

  cliLog('BROWSE_DONE mode=READ_ONLY interactions=0 pages=' + urls.length)
  await completeTaskSpace(space, { keep: false })
})().catch(function (e) { cliLog('BROWSE_ERROR: ' + (e && e.message)) })
