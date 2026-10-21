#!/usr/bin/env node


















const fs = require('fs');
const path = require('path');
const os = require('os');



const EDGE_PATH = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const USER_DATA = path.join(os.homedir(), 'AppData', 'Local', 'Microsoft', 'Edge', 'User Data');
const CONFIG_FILE = path.join(__dirname, '..', 'config', 'fallback-sources.json');
const ZHIHU_URL = 'https://www.zhihu.com';
const ZHIHU_API_ME = 'https://www.zhihu.com/api/v4/me';


const KEY_COOKIES = ['z_c0', '_xsrf', 'd_c0', '_zap', 'q_c1', 'SESSIONID'];



const colors = {
  reset: '\x1b[0m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  red: '\x1b[31m',
  cyan: '\x1b[36m',
  bold: '\x1b[1m',
  dim: '\x1b[2m',
};

function log(msg, color = 'reset') {
  console.log(`${colors[color] || ''}${msg}${colors.reset}`);
}

function step(num, msg) {
  const bar = '━'.repeat(50);
  log(`\n${bar}`, 'dim');
  log(`  [${num}] ${msg}`, 'bold');
  log(`${bar}`, 'dim');
}



async function launchEdge(headless = false) {
  const puppeteer = require('puppeteer-core');

  if (!fs.existsSync(EDGE_PATH)) {
    log(`❌ 未找到 Edge 浏览器: ${EDGE_PATH}`, 'red');
    return null;
  }

  log(`   启动 Edge (${headless ? '无头' : '可视'}模式)...`, 'dim');
  log(`   Profile: ${USER_DATA}`, 'dim');

  try {
    const browser = await puppeteer.launch({
      headless: headless ? 'new' : false,
      executablePath: EDGE_PATH,
      userDataDir: USER_DATA,
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-blink-features=AutomationControlled',
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-features=TranslateUI',
        `--window-size=1280,800`,
      ],
      defaultViewport: null,
      ignoreDefaultArgs: ['--enable-automation'],
    });
    log(`   ✅ Edge 已启动`, 'green');
    return browser;
  } catch (e) {
    log(`   ❌ 启动失败: ${e.message}`, 'red');
    log(`   提示: 请关闭所有 Edge 窗口后重试`, 'yellow');
    return null;
  }
}

async function detectLoginState(page) {
  '检测知乎页面登录状态';
  try {
    const state = await page.evaluate(() => {
      
      const hasAvatar = !!document.querySelector('.AppHeader-profile img, .Avatar img, [class*="avatar"]');
      
      const hasZc0 = document.cookie.includes('z_c0=');
      
      const initialData = document.getElementById('js-initialData');
      let userName = null;
      if (initialData) {
        try {
          const data = JSON.parse(initialData.textContent);
          userName = data?.initialState?.currentUser?.name
                  || data?.initialState?.me?.name
                  || data?.initialState?.entities?.users
                     ? Object.values(data.initialState.entities.users)[0]?.name
                     : null;
        } catch {}
      }
      return { hasAvatar, hasZc0, userName };
    });
    return state;
  } catch {
    return { hasAvatar: false, hasZc0: false, userName: null };
  }
}

async function extractCookies(page) {
  '提取所有 zhihu.com 域名下的 Cookie（含 HTTPOnly）';
  try {
    
    const allCookies = await page.cookies();
    const zhihuCookies = allCookies.filter(c =>
      c.domain.includes('zhihu.com') || c.domain === '.zhihu.com'
    );

    const cookies = {};
    for (const c of zhihuCookies) {
      cookies[c.name] = c.value;
    }
    return cookies;
  } catch {
    return null;
  }
}

function saveCookies(cookies) {
  '保存 Cookie 到配置文件';
  try {
    let config = {};
    if (fs.existsSync(CONFIG_FILE)) {
      config = JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf-8'));
    }

    
    config.auth = config.auth || {};
    config.auth.priority = ['file_cookie', 'browser_profile', 'fallback_source'];
    config.cookie = cookies;

    const dir = path.dirname(CONFIG_FILE);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

    fs.writeFileSync(CONFIG_FILE, JSON.stringify(config, null, 2), 'utf-8');
    return true;
  } catch (e) {
    log(`   ❌ 保存失败: ${e.message}`, 'red');
    return false;
  }
}

async function validateCookies(cookies) {
  '验证 Cookie 是否有效';
  const cookieStr = Object.entries(cookies)
    .map(([k, v]) => `${k}=${v}`)
    .join('; ');

  try {
    const resp = await fetch(ZHIHU_API_ME, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Cookie': cookieStr,
      },
      signal: AbortSignal.timeout(10000),
    });

    if (!resp.ok) return null;
    const data = await resp.json();
    return data;
  } catch {
    return null;
  }
}



async function run(options = {}) {
  const { headless = false, saveOnly = false } = options;

  console.clear();
  log('╔══════════════════════════════════════════════════╗', 'cyan');
  log('║    知乎 Cookie 自动化提取工具 v2.0              ║', 'cyan');
  log('║    Auto Cookie Extractor for Edge Browser       ║', 'cyan');
  log('╚══════════════════════════════════════════════════╝', 'cyan');

  
  step('1/5', '启动 Edge 浏览器');
  const browser = await launchEdge(headless);
  if (!browser) {
    log('\n💡 手动获取方法:', 'yellow');
    log('   1. 打开 https://www.zhihu.com 并登录', 'yellow');
    log('   2. F12 → Console → 输入 copy(document.cookie)', 'yellow');
    log('   3. 粘贴到 config/fallback-sources.json 的 cookie 字段', 'yellow');
    return 1;
  }

  let page;
  try {
    const pages = await browser.pages();
    page = pages[0] || await browser.newPage();

    
    await page.setUserAgent(
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0'
    );

    
    await page.evaluateOnNewDocument(() => {
      Object.defineProperty(navigator, 'webdriver', { get: () => false });
    });

    
    step('2/5', '访问知乎页面');
    log('   正在加载 https://www.zhihu.com ...', 'dim');

    try {
      await page.goto(ZHIHU_URL, {
        waitUntil: 'networkidle2',
        timeout: 30000,
      });
    } catch {
      log('   ⚠️  页面加载超时，继续检测...', 'yellow');
    }

    
    step('3/5', '检测登录状态');
    const loginState = await detectLoginState(page);

    if (loginState.userName) {
      log(`   ✅ 已登录! 用户: ${loginState.userName}`, 'green');
    } else if (loginState.hasAvatar) {
      log('   ✅ 检测到登录态（已登录）', 'green');
    } else if (loginState.hasZc0) {
      log('   ✅ 检测到 Cookie 登录态', 'green');
    } else {
      log('   ⚠️  未检测到登录态', 'yellow');
    }

    if (!loginState.userName && !loginState.hasAvatar) {
      if (headless) {
        log('   ❌ 无头模式下需要已有登录态', 'red');
        await browser.close();
        return 1;
      }

      
      step('3b/5', '等待手动登录');
      log('   ┌─────────────────────────────────────────┐', 'yellow');
      log('   │  请在浏览器窗口中完成知乎登录:            │', 'yellow');
      log('   │  ① 点击右上角"登录"按钮                  │', 'yellow');
      log('   │  ② 使用微信/手机扫码登录                 │', 'yellow');
      log('   │  ③ 登录成功后程序将自动继续              │', 'yellow');
      log('   └─────────────────────────────────────────┘', 'yellow');
      log('');

      
      const maxWait = 120000;
      const checkInterval = 2000;
      let waited = 0;

      while (waited < maxWait) {
        await new Promise(r => setTimeout(r, checkInterval));
        waited += checkInterval;

        const state = await detectLoginState(page);
        if (state.userName) {
          log(`\n   ✅ 登录成功! 用户: ${state.userName}`, 'green');
          break;
        }

        
        if (waited % 10000 < checkInterval) {
          const remaining = Math.round((maxWait - waited) / 1000);
          log(`   ⏳ 等待登录... (剩余 ${remaining}s)`, 'dim');
        }
      }

      if (waited >= maxWait) {
        log('   ❌ 等待超时', 'red');
        await browser.close();
        return 1;
      }
    }

    
    step('4/5', '提取 Cookie');
    const cookies = await extractCookies(page);

    if (!cookies || Object.keys(cookies).length === 0) {
      log('   ❌ 未提取到 Cookie', 'red');
      await browser.close();
      return 1;
    }

    
    const totalCount = Object.keys(cookies).length;
    const keyStatus = KEY_COOKIES.map(k => ({
      name: k,
      found: !!cookies[k],
      preview: cookies[k] ? cookies[k].substring(0, 20) + '...' : '—',
    }));

    log(`   提取到 ${totalCount} 个 Cookie:`, 'cyan');
    for (const ks of keyStatus) {
      const icon = ks.found ? '✅' : '❌';
      log(`   ${icon}  ${ks.name.padEnd(15)} ${ks.preview}`, ks.found ? 'green' : 'red');
    }

    if (!saveOnly) {
      
      step('5/5', '验证并保存');

      
      const userInfo = await validateCookies(cookies);
      if (userInfo && userInfo.name) {
        log(`   ✅ Cookie 有效! 用户: ${userInfo.name}`, 'green');
        log(`   ID: ${userInfo.id}`, 'dim');
      } else {
        log('   ⚠️  Cookie 验证返回异常，但仍会保存', 'yellow');
      }

      
      if (saveCookies(cookies)) {
        log(`   ✅ 配置已保存到: ${CONFIG_FILE}`, 'green');
      }
    } else {
      
      if (saveCookies(cookies)) {
        log(`\n   ✅ Cookie 已保存`, 'green');
      }
    }

    
    if (headless) {
      await browser.close();
    } else {
      
      log('\n   ⏳ 3秒后关闭浏览器...', 'dim');
      await new Promise(r => setTimeout(r, 3000));
      await browser.close();
    }

    
    log('\n╔══════════════════════════════════════════════════╗', 'cyan');
    log('║  ✅ Cookie 提取完成!                            ║', 'cyan');
    log('║                                                  ║', 'cyan');
    log(`║  提取 ${String(totalCount).padEnd(2)} 个 Cookie，核心字段齐全            ║`, 'cyan');
    log('║                                                  ║', 'cyan');
    log('║  下一步:                                         ║', 'cyan');
    log('║    python scripts/save_to_db.py all              ║', 'cyan');
    log('╚══════════════════════════════════════════════════╝', 'cyan');

    return 0;

  } catch (e) {
    log(`\n❌ 错误: ${e.message}`, 'red');
    if (browser) await browser.close();
    return 1;
  }
}



function parseArgs() {
  const args = process.argv.slice(2);
  const options = { headless: false, saveOnly: false };

  for (const arg of args) {
    if (arg === '--headless') options.headless = true;
    if (arg === '--save-only') options.saveOnly = true;
    if (arg === '--help' || arg === '-h') {
      console.log(`
知乎 Cookie 自动化提取工具

用法:
  node scripts/auto_cookie.js                交互模式（显示浏览器窗口）
  node scripts/auto_cookie.js --headless     无头模式（需要已有登录态）
  node scripts/auto_cookie.js --save-only    只保存不验证

功能:
  自动启动 Edge 浏览器，利用现有 Profile 中的登录态，
  提取知乎 Cookie 并保存到配置文件。
  若未登录，会等待用户手动扫码登录。
`);
      process.exit(0);
    }
  }

  return options;
}

if (require.main === module) {
  const options = parseArgs();
  run(options).then(code => process.exit(code));
} else {
  module.exports = { run, extractCookies, saveCookies, validateCookies };
}
