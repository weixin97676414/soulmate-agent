/**
 * select_item.cjs —— 通用小程序每日推广
 * 读取任意内容文档(content.js / .json) → 按去重+穿插策略选当日 1 条 → 输出结构化事实
 *
 * 用法:
 *   node select_item.cjs [contentPath] [statePath] [--dry]
 *   --dry : 只预览选取结果，不写状态文件
 *
 * 文档约定(标准格式，同时兼容任意结构):
 *   module.exports = {
 *     APP: { name, slogan, audience, platforms },          // 小程序元信息（缺则运行时询问）
 *     ITEMS: [                                             // 内容数组（兼容 CAMPSITES/items/list/data 等键名）
 *       { id, title, content, images:[], cover, tags:[], category, ...任意扩展字段 }
 *     ]
 *   }
 *   字段自动探测: title/name、content/description、images/gallery/pics、cover、tags、category。
 */
const fs = require("fs");
const path = require("path");

const DEFAULT_CONTENT = path.join(process.cwd(), "content.js");
const DEFAULT_STATE = path.join(process.cwd(), ".covered.json");

const args = process.argv.slice(2);
const dry = args.includes("--dry");
const positional = args.filter(a => !a.startsWith("--"));
const contentPath = positional[0] || DEFAULT_CONTENT;
const statePath = positional[1] || DEFAULT_STATE;

// ---------- 加载文档 ----------
let mod;
try {
  mod = require(contentPath);
} catch (e) {
  console.error("LOAD_FAIL:" + e.message);
  process.exit(2);
}
// 支持直接导出数组的情况
if (Array.isArray(mod)) mod = { ITEMS: mod };

// ---------- 探测 APP 元信息 ----------
const appRaw = mod.APP || mod.app || mod.meta || mod.META || null;
const app = appRaw ? {
  name: appRaw.name || appRaw.名称 || "",
  slogan: appRaw.slogan || appRaw.定位 || appRaw.tagline || "",
  audience: appRaw.audience || appRaw.人群 || "",
  platforms: appRaw.platforms || appRaw.平台 || []
} : null;

// ---------- 探测 ITEMS 数组 ----------
const itemsArr =
  mod.ITEMS || mod.items || mod.CAMPSITES || mod.campsites ||
  mod.list || mod.LIST || mod.data || mod.DATA || mod.posts || mod.articles || null;
if (!itemsArr || !Array.isArray(itemsArr) || !itemsArr.length) {
  console.error("NO_ITEMS");
  process.exit(2);
}

// ---------- 字段自动探测 ----------
function normImg(x) {
  if (!x) return "";
  if (typeof x === "string") return x;
  if (x.src) return x.src;
  if (x.url) return x.url;
  if (x.image) return x.image;
  return "";
}
function detectTitle(it) {
  return it.title || it.name || it.名称 || it.subject || it.标题 || "";
}
function detectContent(it) {
  return it.content || it.description || it.desc || it.summary || it.简介 || it.body || it.正文 || "";
}
function detectImages(it) {
  let imgs = [];
  const arrFields = ["images", "gallery", "pics", "photos", "photosList", "图集", "图"];
  for (const f of arrFields) {
    if (Array.isArray(it[f])) imgs = imgs.concat(it[f].map(normImg));
  }
  // 兜底1：扫描所有数组字段，找 http(s) 图片串
  if (!imgs.length) {
    for (const k in it) {
      if (Array.isArray(it[k])) {
        const u = it[k].map(normImg).filter(s => /^https?:\/\//.test(s));
        if (u.length) imgs = imgs.concat(u);
      }
    }
  }
  // 兜底2：扫描所有字符串字段，找图片后缀 url
  if (!imgs.length) {
    for (const k in it) {
      if (typeof it[k] === "string" && /^https?:\/\/.+\.(jpg|jpeg|png|webp|gif)/i.test(it[k])) imgs.push(it[k]);
    }
  }
  return [...new Set(imgs.filter(Boolean))];
}
function detectCover(it) { return it.cover || it.封面 || detectImages(it)[0] || ""; }
function detectTags(it) {
  const t = it.tags || it.labels || it.keywords || it.标签 || it.关键词 || [];
  return Array.isArray(t) ? t.map(String) : (t ? [String(t)] : []);
}
function detectCategory(it) { return it.category || it.type || it.cat || it.分类 || ""; }
function isPitfall(it) {
  const cat = String(detectCategory(it)).toLowerCase();
  if (/(pit|fall|warn|坑|避坑|warning|fake|假|勿|排雷)/.test(cat)) return true;
  const blob = JSON.stringify(it).toLowerCase();
  if (/(不适合|勿驻留|仅交通|中转|谨慎|危险|排雷|避坑|假)/.test(blob)) return true;
  return false;
}
function itemId(it, idx) { return it.id || it._id || it.ID || detectTitle(it) || ("item-" + idx); }

// ---------- 状态 / 去重 ----------
let state = { runCount: 0, covered: [], realIndex: 0, pitIndex: 0 };
if (fs.existsSync(statePath)) {
  try {
    const raw = fs.readFileSync(statePath, "utf8");
    if (raw) {
      const loaded = JSON.parse(raw);
      // 兼容旧版状态键名（fakeIndex → pitIndex）
      if (loaded.fakeIndex != null && loaded.pitIndex == null) loaded.pitIndex = loaded.fakeIndex;
      state = Object.assign(state, loaded);
    }
  } catch (e) {}
}
const coveredSet = new Set(state.covered);

const reals = itemsArr.map((c, i) => ({ c, i })).filter(x => !isPitfall(x.c));
const pits = itemsArr.map((c, i) => ({ c, i })).filter(x => isPitfall(x.c));

function nextReals() {
  while (state.realIndex < reals.length) {
    const x = reals[state.realIndex];
    if (!coveredSet.has(itemId(x.c, x.i))) return x;
    state.realIndex++;
  }
  return null;
}
function nextPits() {
  while (state.pitIndex < pits.length) {
    const x = pits[state.pitIndex];
    if (!coveredSet.has(itemId(x.c, x.i))) return x;
    state.pitIndex++;
  }
  return null;
}

// 每 3 次运行穿插 1 篇避坑（runCount 从 0 起，第 2/5/8... 次选避坑）
let chosen = null, chosenIsPit = false, chosenIdx = -1;
if (pits.length && state.pitIndex < pits.length && state.runCount % 3 === 2) {
  const p = nextPits(); chosen = p ? p.c : null; chosenIsPit = !!p; chosenIdx = p ? p.i : -1;
  if (!chosen) { const r = nextReals(); chosen = r ? r.c : null; chosenIsPit = false; chosenIdx = r ? r.i : -1; }
} else {
  const r = nextReals(); chosen = r ? r.c : null; chosenIsPit = false; chosenIdx = r ? r.i : -1;
  if (!chosen) { const p = nextPits(); chosen = p ? p.c : null; chosenIsPit = true; chosenIdx = p ? p.i : -1; }
}

if (!chosen) {
  console.log(JSON.stringify({ status: "NONE", total: itemsArr.length, covered: state.covered.length }));
  process.exit(0);
}

if (chosenIsPit) state.pitIndex++; else state.realIndex++;
state.covered.push(itemId(chosen, chosenIdx));
state.runCount++;

// ---------- 渲染通用事实 ----------
const images = detectImages(chosen);
const facts = {
  app,
  needsAppInfo: !app,
  item: {
    id: itemId(chosen, chosenIdx),
    title: detectTitle(chosen),
    summary: chosen.summary || chosen.简介 || "",
    content: detectContent(chosen),
    images,
    cover: detectCover(chosen),
    tags: detectTags(chosen),
    category: detectCategory(chosen),
    isPitfall: chosenIsPit
  },
  raw: chosen
};

const isCoveredReal = id => reals.some(r => itemId(r.c, r.i) === id);
const out = {
  status: "OK",
  isPitfall: chosenIsPit,
  id: facts.item.id,
  runCount: state.runCount,
  remainingReal: reals.length - state.covered.filter(isCoveredReal).length,
  remainingPit: pits.length - state.covered.filter(id => pits.some(p => itemId(p.c, p.i) === id)).length,
  facts
};

if (!dry) {
  fs.writeFileSync(statePath, JSON.stringify(state, null, 2), "utf8");
}
console.log(JSON.stringify(out, null, 2));
