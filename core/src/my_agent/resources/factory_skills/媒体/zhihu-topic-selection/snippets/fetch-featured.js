#!/usr/bin/env node
















const fs = require('fs');
const path = require('path');
const RateLimiter = require('./rate-limiter');
const CookieManager = require('./cookie-manager');




const FEATURED_API = 'https://www.zhihu.com/api/v4/creators/question_route/author_related/recommend';
const PAGE_SOURCE_MAP = {
  recommend: 'web_author_recommend',
  invited: 'web_author_invite'
};

const RATE_LIMIT_MS = parseInt(process.env.RATE_LIMIT || '2000', 10);
const DEFAULT_LIMIT = 100;

function parseArgs() {
  const args = process.argv.slice(2);
  let mode = 'recommend';
  let limit = DEFAULT_LIMIT;
  let outputFile = null;
  let jsonMode = false;

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === 'recommend' || arg === 'invited') {
      mode = arg;
    } else if (arg === '--json') {
      jsonMode = true;
    } else if (arg === '--output' && args[i + 1]) {
      outputFile = args[i + 1];
      i++;
    } else if (/^\d+$/.test(arg)) {
      limit = parseInt(arg, 10);
    }
  }

  return { mode, limit, outputFile, jsonMode };
}




function formatQuestionTime(raw) {
  if (!raw) return '';
  
  const ts = Number(raw);
  if (ts < 10000000000) {
    return new Date(ts * 1000).toISOString();
  }
  
  if (ts < 100000000000) {
    return new Date(ts * 1000).toISOString();
  }
  return new Date(ts).toISOString();
}



async function fetchViaBrowser(mode, limit) {
  
  const cookieManager = new CookieManager();
  console.error('[AUTH] 从 Edge 浏览器自动获取 Cookie...');
  const fresh = await cookieManager.refreshFromBrowser();
  if (!fresh) return null;

  
  return await fetchViaCookie(mode, limit);
}



async function fetchViaCookie(mode, limit) {
  const cookieManager = new CookieManager();
  const cookieHeader = cookieManager.toHeader();
  const cookies = cookieManager.load();

  if (!cookieHeader) return null;

  const pageSource = PAGE_SOURCE_MAP[mode] || 'web_author_recommend';
  const rateLimiter = new RateLimiter(RATE_LIMIT_MS);
  const questions = [];
  let offset = 0;
  const batchSize = 20;

  while (questions.length < limit) {
    try {
      await rateLimiter.wait();

      const apiUrl = `${FEATURED_API}?limit=${batchSize}&offset=${offset}&page_source=${pageSource}&recom_domain_score_ab=1`;
      const response = await fetch(apiUrl, {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
          'Cookie': cookieHeader,
          'Accept': 'application/json',
          'Referer': `https://www.zhihu.com/creator/featured-question/${mode}`,
          'x-requested-with': 'fetch',
          'x-xsrf-token': cookies._xsrf || ''
        },
        signal: AbortSignal.timeout(15000)
      });

      if (!response.ok) {
        if (response.status === 401 || response.status === 403) {
          console.error('[AUTH] Cookie已失效');
          return null;
        }
        break;
      }

      const json = await response.json();
      const data = json.data || [];
      if (data.length === 0) break;

      for (const item of data) {
        const target = item.question || item;
        questions.push({
          qid: String(target.id || ''),
          title: target.title || '',
          url: target.url || `https://www.zhihu.com/question/${target.id}`,
          view_count: parseInt(target.view_count || target.visit_count || 0, 10),
          answer_count: parseInt(target.answer_count || 0, 10),
          follower_count: parseInt(target.follower_count || 0, 10),
          question_time: formatQuestionTime(target.created || target.created_time || target.publish_time),
          recommend_reason: item.reason || '',
          tags: (target.topics || target.tags || []).map(t => t.name || t).join(', '),
          source: mode === 'recommend' ? 'recommend' : 'invited'
        });
      }

      offset += batchSize;
      if (json.paging && json.paging.is_end) break;

    } catch (e) {
      console.error('[FETCH] 请求失败: ' + e.message);
      break;
    }
  }

  if (questions.length > 0) {
    return buildResult(mode, 'file_cookie', questions);
  }
  return null;
}



async function fetchViaFallback(mode) {
  
  return null;
}



function buildResult(mode, authMethod, questions) {
  return {
    meta: {
      source: 'zhihu',
      mode: mode,
      auth_method: authMethod,
      fetch_time: new Date().toISOString(),
      rate_limited: true,
      count: questions.length
    },
    data: questions
  };
}



async function fetchFeaturedWithFallback(options = {}) {
  const { mode = 'recommend', limit = DEFAULT_LIMIT, authPriority = null } = options;

  const cookieManager = new CookieManager();
  const priority = authPriority || cookieManager.getAuthPriority() ||
    ['browser_profile', 'file_cookie', 'fallback_source'];

  for (const method of priority) {
    let result = null;

    if (method === 'browser_profile') {
      console.error(`[AUTH] 尝试 Browser Profile (${mode})...`);
      result = await fetchViaBrowser(mode, limit);
    } else if (method === 'file_cookie') {
      console.error(`[AUTH] 尝试 File Cookie (${mode})...`);
      result = await fetchViaCookie(mode, limit);
    } else if (method === 'fallback_source') {
      console.error(`[AUTH] 尝试 Fallback Source (${mode})...`);
      result = await fetchViaFallback(mode);
    }

    if (result && result.data.length > 0) {
      console.error(`[AUTH] 成功! 认证方式: ${result.meta.auth_method}, 获取 ${result.data.length} 条问题`);
      return result;
    }
    console.error(`[AUTH] ${method} 失败，降级...`);
  }

  console.error('[AUTH] 所有认证方式均失败 (推荐/邀请问题需要登录态)');
  return {
    meta: {
      source: 'zhihu',
      mode: mode,
      auth_method: 'none',
      fetch_time: new Date().toISOString(),
      rate_limited: true,
      count: 0,
      error: '推荐/邀请问题需要登录态，请先配置Cookie或使用Browser Profile'
    },
    data: []
  };
}



async function main() {
  const { mode, limit, outputFile, jsonMode } = parseArgs();

  if (!jsonMode && !outputFile) {
    console.error(`知乎创作中心${mode === 'recommend' ? '推荐' : '邀请'}问题抓取 v1.0`);
    console.error(`模式: ${mode} | 目标: ${limit} 条 | 频率限制: ${RATE_LIMIT_MS}ms/次`);
    console.error('');
    console.error('💡 提示: 推荐/邀请问题需要登录态，推荐使用 Browser Profile 或 File Cookie');
    console.error('');
  }

  const result = await fetchFeaturedWithFallback({ mode, limit });
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
  module.exports = { fetchFeaturedWithFallback };
}
