(async () => {
  const qid = process.env.QID
  if (!qid) { cliLog('ERROR: set QID env var'); return }
  const POOL = parseInt(process.env.POOL, 10) || 10
  const LIKE_MIN = parseInt(process.env.LIKE_MIN, 10) || 3
  const LIKE_MAX = parseInt(process.env.LIKE_MAX, 10) || 5
  const space = 'zhihu-like-' + qid
  const task = await useOrCreateTaskSpace(space)
  const url = 'https://www.zhihu.com/question/' + qid
  await openOrReuseTab(url, { wait: true, timeout: 20 })
  await wait(4)

  const answered = await js('(() => {'
    + ' const btns = Array.from(document.querySelectorAll("button"));'
    + ' return btns.some(function(b){ return b.innerText.indexOf("查看我的回答") >= 0; });'
    + '})()')
  cliLog('already-answered: ' + answered)
  if (answered) {
    cliLog('SKIP: question already answered, pick another')
    await completeTaskSpace(space, { keep: false })
    return
  }

  cliLog('simulating read 90s (risk control)...')
  await wait(90)

  const before = await js('(() => {'
    + ' const seen = new Set(); const arr = [];'
    + ' const nodes = document.querySelectorAll("[data-zop]");'
    + ' for (let i=0;i<nodes.length;i++){'
    + '   let zop; try { zop = JSON.parse(nodes[i].getAttribute("data-zop")); } catch(e){ continue; }'
    + '   if (!zop.itemId || seen.has(zop.itemId)) continue;'
    + '   seen.add(zop.itemId);'
    + '   if (arr.length >= ' + POOL + ') break;'
    + '   const b = nodes[i].querySelector("button[aria-label*="赞同"]");'
    + '   arr.push({ itemId: zop.itemId, active: b ? b.classList.contains("is-active") : false });'
    + ' }'
    + ' return arr;'
    + '})()')
  cliLog('CANDIDATE_POOL(' + POOL + '): ' + before.length + ' answers collected')
  const n = before.length
  const minC = Math.min(LIKE_MIN, n)
  const maxC = Math.min(LIKE_MAX, n)
  const count = n === 0 ? 0 : (minC + Math.floor(Math.random() * (maxC - minC + 1)))
  cliLog('RANDOM_LIKE_COUNT: ' + count + ' (min=' + LIKE_MIN + ' max=' + LIKE_MAX + ' avail=' + n + ')')
  const shuffled = before.slice()
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    const t = shuffled[i]; shuffled[i] = shuffled[j]; shuffled[j] = t
  }
  const picks = shuffled.slice(0, count)
  cliLog('PICKED_ITEMIDS: ' + JSON.stringify(picks.map(function(x){ return x.itemId; })))
  const results = []
  for (let i=0;i<picks.length;i++){
    const itemId = picks[i].itemId
    if (picks[i].active) { results.push({ itemId: itemId, action: 'skip_already_active' }); cliLog('skip already-active ' + itemId); continue }
    const clicked = await js('((id) => {'
      + ' const nodes = document.querySelectorAll("[data-zop]");'
      + ' for (let i=0;i<nodes.length;i++){'
      + '   let zop; try { zop = JSON.parse(nodes[i].getAttribute("data-zop")); } catch(e){ continue; }'
      + '   if (zop.itemId === id) {'
      + '     const b = nodes[i].querySelector("button[aria-label*="赞同"]");'
      + '     if (b) {'
      + '       if (b.classList.contains("is-active")) return "already_active";'
      + '       b.click(); return (b.getAttribute("aria-label")||"").trim();'
      + '     }'
      + '   }'
      + ' }'
      + ' return null;'
      + '})(' + JSON.stringify(itemId) + ')')
    results.push({ itemId: itemId, after: clicked })
    cliLog('liked ' + itemId + ' -> ' + clicked)
    if (i < picks.length - 1) { const gap = 35 + Math.floor(Math.random()*45); await wait(gap) }
  }
  cliLog('LIKE_RESULT: ' + JSON.stringify(results, null, 2))
  await completeTaskSpace(space, { keep: false })
})()
