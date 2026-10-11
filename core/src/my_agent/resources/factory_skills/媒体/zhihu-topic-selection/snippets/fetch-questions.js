#!/usr/bin/env node
/**
 * 知乎"等你来答"问题列表获取 - Questions Waiting to Answer Fetcher
 * 三级认证降级机制: Browser Profile → File Cookie → Fallback Source
 *
 * 用法:
 *   node fetch-questions.js [limit] [--json] [--output file.json]
 */

const fs = require('fs');
const path = require('path');
const RateLimiter = require('./rate-limiter');
const CookieManager = require('./cookie-manager');

// ---------- 配置 ----------

// 知乎"等你来答"相关API
const ZHIHU_WAITING_API = 'https://www.zhihu.com/api/v3/feed/topstory/answer-question?limit=20';
const ZHIHU_QUESTIONS_API = 'https://www.zhihu.com/api/v4/questions?limit=20';
const ZHIHU_NOTIFICATIONS_API = 'https://www.zhihu.com/api/v3/notifications/v3/timeline?limit=20';
const ZHIHU_MESSAGE_PAGE = 'https://www.zhihu.com/notifications';
const ZHIHU_WAITING_PAGE = 'https://www.zhihu.com/question/waiting';

const RATE_LIMIT_MS = parseInt(process.env.RATE_LIMIT || '2000', 10);
const DEFAULT_LIMIT = 30;

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
    }
  }

  return { limit, outputFile, jsonMode };
}

// ---------- Level 1: Browser Profile ----------

async function fetchQuestionsViaBrowser(limit) {
  let puppeteer;
  try {
    puppeteer = require('puppeteer');
  } catch {
    return null;
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

    // 先访问消息页面检查登录状态
    await page.goto(ZHIHU_MESSAGE_PAGE, { waitUntil: 'networkidle2', timeout: 30000 });

    const isLoggedIn = await page.evaluate(() => {
      return !!document.querySelector('.AppHeader-profile, [data-za-detail-view-path-module="UserItem"]');
    });

    if (!isLoggedIn) {
      await browser.close();
      return null;
    }

    // 提取问题数据 - 从多个可能的来源
    const questions = await page.evaluate(async (limit) => {
      const results = [];

      // 尝试通过API获取"等你来答"列表
      try {
        const response = await fetch(
          'https://www.zhihu.com/api/v3/feed/topstory/answer-question?limit=20',
          { credentials: 'include' }
        );
        const json = await response.json();
        const data = json.data || [];
        for (const item of data) {
          const target = item.target || {};
          const question = target.question || target;
          results.push({
            title: question.title || '',
            url: question.url || `https://www.zhihu.com/question/${question.id}`,
            qid: String(question.id || ''),
            answer_count: question.answer_count || 0,
            follower_count: question.follower_count || 0,
            tags: (question.topics || []).map(t => t.name).join(', '),
            source: 'waiting'
          });
        }
      } catch {}

      // 也尝试从通知中提取邀请回答
      if (results.length < limit) {
        try {
          const resp = await fetch(
            'https://www.zhihu.com/api/v3/notifications/v3/timeline?limit=20',
            { credentials: 'include' }
          );
          const json = await resp.json();
          const notifications = json.data || [];
          const invites = [];
          for (const notif of notifications) {
            const target = notif.target || {};
            const notifType = notif.notification_type || '';
            // 邀请回答类型的通知
            if (notifType.includes('invite') || notifType.includes('question')) {
              const q = target.question || target;
              if (q && q.title) {
                invites.push({
                  title: q.title || '',
                  url: q.url || `https://www.zhihu.com/question/${q.id}`,
                  qid: String(q.id || ''),
                  answer_count: q.answer_count || 0,
                  follower_count: q.follower_count || 0,
                  tags: (q.topics || []).map(t => t.name).join(', '),
                  source: 'invited'
                });
              }
            }
          }
          for (const inv of invites) {
            if (results.length < limit) results.push(inv);
          }
        } catch {}
      }

      return results.slice(0, limit);
    }, limit);

    await browser.close();

    if (questions.length > 0) {
      return {
        meta: {
          source: 'zhihu',
          mode: 'questions',
          auth_method: 'browser_profile',
          fetch_time: new Date().toISOString(),
          rate_limited: true,
          count: questions.length
        },
        data: questions
      };
    }
    return null;
  } catch {
    return null;
  }
}

// ---------- Level 2: File Cookie ----------

async function fetchQuestionsViaCookie(limit) {
  const cookieManager = new CookieManager();
  const cookieHeader = cookieManager.toHeader();

  if (!cookieHeader) return null;

  const rateLimiter = new RateLimiter(RATE_LIMIT_MS);

  const sources = [
    {
      name: 'waiting',
      url: ZHIHU_WAITING_API
    },
    {
      name: 'notifications',
      url: ZHIHU_NOTIFICATIONS_API
    }
  ];

  const questions = [];

  for (const source of sources) {
    if (questions.length >= limit) break;

    try {
      await rateLimiter.wait();
      const response = await fetch(source.url, {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
          'Cookie': cookieHeader,
          'Accept': 'application/json',
          'Referer': 'https://www.zhihu.com/'
        },
        signal: AbortSignal.timeout(15000)
      });

      if (!response.ok) continue;

      const json = await response.json();
      const data = json.data || [];

      for (const item of data) {
        if (questions.length >= limit) break;

        const target = item.target || {};
        const question = target.question || target;

        const q = {
          title: question.title || '',
          url: question.url || `https://www.zhihu.com/question/${question.id}`,
          qid: String(question.id || ''),
          answer_count: question.answer_count || 0,
          follower_count: question.follower_count || 0,
          tags: (question.topics || []).map(t => t.name).join(', '),
          source: source.name === 'notifications' ? 'invited' : 'waiting'
        };

        if (q.title) questions.push(q);
      }
    } catch {
      continue;
    }
  }

  if (questions.length > 0) {
    return {
      meta: {
        source: 'zhihu',
        mode: 'questions',
        auth_method: 'file_cookie',
        fetch_time: new Date().toISOString(),
        rate_limited: true,
        count: questions.length
      },
      data: questions
    };
  }
  return null;
}

// ---------- Level 3: Fallback (questions无可靠备用源) ----------

async function fetchQuestionsViaFallback() {
  // "等你来答"问题列表没有可靠的公开备用源
  // 但我们可以尝试从知乎公开API获取一些热门问题作为参考
  try {
    const response = await fetch(
      'https://www.zhihu.com/api/v4/creator/questions/recommend?limit=20',
      {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
          'Accept': 'application/json'
        },
        signal: AbortSignal.timeout(10000)
      }
    );

    if (!response.ok) return null;

    const json = await response.json();
    const data = json.data || [];

    const questions = data.map(item => {
      const q = item.question || item;
      return {
        title: q.title || '',
        url: q.url || `https://www.zhihu.com/question/${q.id}`,
        qid: String(q.id || ''),
        answer_count: q.answer_count || 0,
        follower_count: q.follower_count || 0,
        tags: (q.topics || []).map(t => t.name).join(', '),
        source: 'recommend'
      };
    });

    if (questions.length > 0) {
      return {
        meta: {
          source: 'zhihu',
          mode: 'questions',
          auth_method: 'fallback_source',
          fetch_time: new Date().toISOString(),
          rate_limited: true,
          count: questions.length,
          note: '备用源仅提供推荐问题，非个性化"等你来答"列表'
        },
        data: questions
      };
    }
    return null;
  } catch {
    return null;
  }
}

// ---------- 主入口 ----------

async function fetchQuestionsWithFallback(options = {}) {
  const { limit = DEFAULT_LIMIT, authPriority = null } = options;

  const cookieManager = new CookieManager();
  const priority = authPriority || cookieManager.getAuthPriority() ||
    ['browser_profile', 'file_cookie', 'fallback_source'];

  for (const method of priority) {
    let result = null;

    if (method === 'browser_profile') {
      console.error('[AUTH] 尝试 Browser Profile: 从 Edge 自动获取 Cookie...');
      const fresh = await cookieManager.refreshFromBrowser();
      if (fresh) {
        console.error('[AUTH] Cookie 已刷新，使用 file_cookie 模式');
        result = await fetchQuestionsViaCookie(limit);
        if (result && result.data.length > 0) {
          result.meta.auth_method = 'browser_profile';
        }
      } else {
        console.error('[AUTH] 无法从浏览器获取 Cookie，降级...');
        continue;
      }
    } else if (method === 'file_cookie') {
      console.error('[AUTH] 尝试 File Cookie...');
      result = await fetchQuestionsViaCookie(limit);
    } else if (method === 'fallback_source') {
      console.error('[AUTH] 尝试 Fallback Source...');
      result = await fetchQuestionsViaFallback();
    }

    if (result && result.data.length > 0) {
      console.error(`[AUTH] 成功! 认证方式: ${result.meta.auth_method}, 获取 ${result.data.length} 条问题`);
      return result;
    }
    console.error(`[AUTH] ${method} 失败，降级...`);
  }

  console.error('[AUTH] 所有认证方式均失败 (问题列表需要登录态)');
  return {
    meta: {
      source: 'zhihu',
      mode: 'questions',
      auth_method: 'none',
      fetch_time: new Date().toISOString(),
      rate_limited: true,
      count: 0,
      error: '问题列表需要登录态，请先配置Cookie或使用Browser Profile'
    },
    data: []
  };
}

// ---------- CLI ----------

async function main() {
  const { limit, outputFile, jsonMode } = parseArgs();

  if (!jsonMode && !outputFile) {
    console.error(`知乎"等你来答"问题抓取 v1.0`);
    console.error(`目标: ${limit} 条 | 频率限制: ${RATE_LIMIT_MS}ms/次`);
    console.error('');
    console.error('💡 提示: 问题列表需要登录态，推荐使用 Browser Profile 或 File Cookie');
    console.error('');
  }

  const result = await fetchQuestionsWithFallback({ limit });
  const output = JSON.stringify(result, null, 2);

  if (outputFile) {
    fs.mkdirSync(path.dirname(path.resolve(outputFile)), { recursive: true });
    fs.writeFileSync(path.resolve(outputFile), output, 'utf-8');
    console.error(`已保存到: ${path.resolve(outputFile)}`);
    console.log(output);
    return;
  }

  if (jsonMode) {
    console.log(output);
    return;
  }

  console.log(output);
}

if (require.main === module) {
  main().catch(e => {
    console.error(`错误: ${e.message}`);
    process.exit(1);
  });
} else {
  module.exports = { fetchQuestionsWithFallback };
}
