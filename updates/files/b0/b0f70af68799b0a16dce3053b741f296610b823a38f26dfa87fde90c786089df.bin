#!/usr/bin/env node
/**
 * 知乎热榜获取 - Zhihu Hot List Fetcher
 * 三级认证降级机制: Browser Profile → File Cookie → Fallback Source
 *
 * 用法:
 *   node fetch-hot.js [limit] [--json] [--output file.json]
 *   RATE_LIMIT=5000 node fetch-hot.js 50
 */

const fs = require('fs');
const path = require('path');
const RateLimiter = require('./rate-limiter');
const CookieManager = require('./cookie-manager');
const FallbackFetcher = require('./fallback');

// ---------- 配置 ----------

const ZHIHU_HOT_API = 'https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total?limit=50&desktop=true';
const ZHIHU_HOT_PAGE = 'https://www.zhihu.com/hot';
const RATE_LIMIT_MS = parseInt(process.env.RATE_LIMIT || '2000', 10);
const DEFAULT_LIMIT = 50;

// ---------- 工具函数 ----------

function parseArgs() {
  const args = process.argv.slice(2);
  let limit = DEFAULT_LIMIT;
  let outputFile = null;
  let jsonMode = false;

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--json') {
      jsonMode = true;
    } else if (arg === '--output' && args[i + 1]) {
      outputFile = args[i + 1];
      i++;
    } else if (/^\d+$/.test(arg)) {
      limit = parseInt(arg, 10);
    } else if (!arg.startsWith('--') && arg.endsWith('.json')) {
      outputFile = arg;
    }
  }

  return { limit, outputFile, jsonMode };
}

// ---------- Level 1: Browser Profile (Puppeteer) ----------

async function fetchViaBrowserProfile(limit) {
  let puppeteer;
  try {
    puppeteer = require('puppeteer');
  } catch {
    return null; // puppeteer 未安装
  }

  try {
    const browser = await puppeteer.launch({
      headless: 'new',
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    const page = await browser.newPage();
    await page.setUserAgent(
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    );

    // 尝试加载保存的浏览器状态
    const userDataDir = path.join(__dirname, '..', 'data', 'browser-profile');
    if (fs.existsSync(userDataDir)) {
      // 已有登录态
    }

    await page.goto(ZHIHU_HOT_PAGE, { waitUntil: 'networkidle2', timeout: 30000 });

    // 检查是否已登录
    const isLoggedIn = await page.evaluate(() => {
      return !!document.querySelector('.AppHeader-profile, [data-za-detail-view-path-module="UserItem"]');
    });

    if (!isLoggedIn) {
      await browser.close();
      return null; // 未登录，降级
    }

    // 通过页面API获取热榜数据
    const hotData = await page.evaluate(async (limit) => {
      try {
        const response = await fetch(
          'https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total?limit=50&desktop=true',
          { credentials: 'include' }
        );
        const json = await response.json();
        const data = json.data || [];
        return data.slice(0, limit).map((item, idx) => {
          const target = item.target || {};
          return {
            rank: idx + 1,
            title: target.title || target.title_area?.text || '',
            url: target.url || `https://www.zhihu.com/question/${target.id}`,
            heat: parseInt((item.detail_text || '').replace(/[^0-9]/g, '') || '0', 10) || 0,
            author: target.author?.name || '',
            summary: target.excerpt || ''
          };
        });
      } catch {
        return [];
      }
    }, limit);

    await browser.close();

    if (hotData.length > 0) {
      return {
        meta: {
          source: 'zhihu',
          mode: 'hot',
          auth_method: 'browser_profile',
          fetch_time: new Date().toISOString(),
          rate_limited: true,
          count: hotData.length
        },
        data: hotData
      };
    }
    return null;
  } catch {
    return null;
  }
}

// ---------- Level 2: File Cookie ----------

async function fetchViaFileCookie(limit) {
  const cookieManager = new CookieManager();
  const cookieHeader = cookieManager.toHeader();

  if (!cookieHeader) return null;

  const rateLimiter = new RateLimiter(RATE_LIMIT_MS);

  try {
    await rateLimiter.wait();
    const response = await fetch(ZHIHU_HOT_API, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Cookie': cookieHeader,
        'Accept': 'application/json',
        'Referer': 'https://www.zhihu.com/hot'
      },
      signal: AbortSignal.timeout(15000)
    });

    if (!response.ok) return null;

    const json = await response.json();
    const dataList = json.data || [];

    const items = dataList.slice(0, limit).map((item, idx) => {
      const target = item.target || {};
      return {
        rank: idx + 1,
        title: target.title || target.title_area?.text || '',
        url: target.url || `https://www.zhihu.com/question/${target.id}`,
        heat: parseInt((item.detail_text || '').replace(/[^0-9]/g, '') || '0', 10) || 0,
        author: target.author?.name || '',
        summary: target.excerpt || ''
      };
    });

    if (items.length > 0) {
      return {
        meta: {
          source: 'zhihu',
          mode: 'hot',
          auth_method: 'file_cookie',
          fetch_time: new Date().toISOString(),
          rate_limited: true,
          count: items.length
        },
        data: items
      };
    }
    return null;
  } catch {
    return null;
  }
}

// ---------- Level 3: Fallback Source ----------

async function fetchViaFallback() {
  const fallback = new FallbackFetcher();
  return fallback.fetch();
}

// ---------- 主入口: 三级认证降级 ----------

async function fetchWithFallback(options = {}) {
  const { limit = DEFAULT_LIMIT, authPriority = null } = options;

  // 确定认证优先级
  const cookieManager = new CookieManager();
  const priority = authPriority || cookieManager.getAuthPriority() ||
    ['browser_profile', 'file_cookie', 'fallback_source'];

  for (const method of priority) {
    let result = null;

    if (method === 'browser_profile') {
      console.error('[AUTH] 尝试 Browser Profile: 从 Edge 自动获取 Cookie...');
      // 尝试从 Edge 浏览器刷新 Cookie
      const fresh = await cookieManager.refreshFromBrowser();
      if (fresh) {
        console.error('[AUTH] Cookie 已从浏览器刷新，使用 file_cookie 模式');
        result = await fetchViaFileCookie(limit);
        if (result && result.data.length > 0) {
          result.meta.auth_method = 'browser_profile';
        }
      } else {
        console.error('[AUTH] 无法从浏览器获取 Cookie，降级...');
        continue;
      }
    } else if (method === 'file_cookie') {
      console.error('[AUTH] 尝试 File Cookie...');
      result = await fetchViaFileCookie(limit);
    } else if (method === 'fallback_source') {
      console.error('[AUTH] 尝试 Fallback Source...');
      result = await fetchViaFallback();
    }

    if (result && result.data.length > 0) {
      console.error(`[AUTH] 成功! 认证方式: ${result.meta.auth_method}, 获取 ${result.data.length} 条`);
      return result;
    }
    console.error(`[AUTH] ${method} 失败，降级...`);
  }

  // 所有方式都失败
  console.error('[AUTH] 所有认证方式均失败');
  return {
    meta: {
      source: 'zhihu',
      mode: 'hot',
      auth_method: 'none',
      fetch_time: new Date().toISOString(),
      rate_limited: true,
      count: 0,
      error: '所有认证方式均失败'
    },
    data: []
  };
}

// ---------- CLI ----------

async function main() {
  const { limit, outputFile, jsonMode } = parseArgs();

  if (!jsonMode && !outputFile) {
    console.error(`知乎热榜抓取工具 v1.0`);
    console.error(`目标: ${limit} 条 | 频率限制: ${RATE_LIMIT_MS}ms/次`);
    console.error('');
  }

  const result = await fetchWithFallback({ limit });

  const output = JSON.stringify(result, null, 2);

  if (outputFile) {
    const outPath = path.resolve(outputFile);
    fs.mkdirSync(path.dirname(outPath), { recursive: true });
    fs.writeFileSync(outPath, output, 'utf-8');
    console.error(`已保存到: ${outPath}`);
    // 只输出JSON（供 save_to_db.py 解析）
    console.log(output);
    return;
  }

  if (jsonMode) {
    console.log(output);
    return;
  }

  // 人性化输出
  console.log(output);
}

// 导出供模块使用
fetchWithFallback.fetchViaBrowserProfile = fetchViaBrowserProfile;
fetchWithFallback.fetchViaFileCookie = fetchViaFileCookie;
fetchWithFallback.fetchViaFallback = fetchViaFallback;

if (require.main === module) {
  main().catch(e => {
    console.error(`错误: ${e.message}`);
    process.exit(1);
  });
} else {
  module.exports = { fetchWithFallback, fetchViaBrowserProfile, fetchViaFileCookie, fetchViaFallback };
}
