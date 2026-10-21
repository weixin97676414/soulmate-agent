#!/usr/bin/env node



















const fs = require('fs');
const path = require('path');
const os = require('os');
const puppeteer = require('puppeteer-core');



const EDGE_PATH = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const USER_DATA = path.join(os.homedir(), 'AppData', 'Local', 'Microsoft', 'Edge', 'User Data');
const CONFIG_FILE = path.join(__dirname, '..', 'config', 'fallback-sources.json');
const DRAFTS_DIR = path.join(__dirname, '..', 'data', 'drafts');

const ZHIHU_URL = 'https://www.zhihu.com';
const ARTICLE_PAGE = 'https://zhuanlan.zhihu.com/write';
const LOGIN_URL = 'https://www.zhihu.com/signin';


const TYPING_SPEED = { min: 60, max: 180 };  
const MOUSE_STEPS = { min: 20, max: 40 };      
const SCROLL_PAUSE = { min: 500, max: 2000 };  
const CLICK_DELAY = { min: 300, max: 1500 };   
const ACTION_DELAY = { min: 800, max: 3000 };  



const log = {
  _t: () => new Date().toLocaleTimeString('zh-CN'),
  info: (m) => console.log(`  \x1b[36m[${log._t()}]\x1b[0m ${m}`),
  ok: (m) => console.log(`  \x1b[32m[${log._t()}]\x1b[0m ✅ ${m}`),
  warn: (m) => console.log(`  \x1b[33m[${log._t()}]\x1b[0m ⚠️  ${m}`),
  step: (n, m) => console.log(`\n\x1b[1m[${n}] ${m}\x1b[0m`),
};

function rand(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

function randomSleep(min, max) {
  return sleep(rand(min, max));
}



async function humanMouseMove(page, toX, toY, steps = null) {
  const start = await page.evaluate(() => ({ x: window.mouseX || 400, y: window.mouseY || 300 }));

  steps = steps || rand(MOUSE_STEPS.min, MOUSE_STEPS.max);

  
  const cp1x = start.x + (toX - start.x) * (0.2 + Math.random() * 0.3);
  const cp1y = start.y + (toY - start.y) * (0.1 + Math.random() * 0.2);
  const cp2x = start.x + (toX - start.x) * (0.6 + Math.random() * 0.2);
  const cp2y = start.y + (toY - start.y) * (0.7 + Math.random() * 0.2);

  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const x = Math.pow(1 - t, 3) * start.x + 3 * Math.pow(1 - t, 2) * t * cp1x
            + 3 * (1 - t) * t * t * cp2x + t * t * t * toX;
    const y = Math.pow(1 - t, 3) * start.y + 3 * Math.pow(1 - t, 2) * t * cp1y
            + 3 * (1 - t) * t * t * cp2y + t * t * t * toY;

    await page.mouse.move(Math.round(x), Math.round(y));
    await sleep(rand(5, 15));
  }

  
  await page.evaluate((x, y) => { window.mouseX = x; window.mouseY = y; }, toX, toY);
}

async function humanClick(page, selector, options = {}) {
  const { delay = true, moveDelay = 0 } = options;

  try {
    await page.waitForSelector(selector, { visible: true, timeout: 10000 });
    const el = await page.$(selector);
    if (!el) return false;

    const box = await el.boundingBox();
    if (!box) return false;

    const targetX = box.x + box.width / 2 + rand(-5, 5);
    const targetY = box.y + box.height / 2 + rand(-3, 3);

    await humanMouseMove(page, targetX, targetY);
    if (moveDelay) await sleep(moveDelay);
    await page.mouse.click(targetX, targetY);

    if (delay) await randomSleep(CLICK_DELAY.min, CLICK_DELAY.max);
    return true;
  } catch {
    return false;
  }
}



async function humanType(page, selector, text, options = {}) {
  const { clear = true, clickFirst = true } = options;

  try {
    if (clickFirst) {
      await page.waitForSelector(selector, { visible: true, timeout: 10000 });
      await page.click(selector);
      await randomSleep(CLICK_DELAY.min, CLICK_DELAY.max);
    }

    if (clear) {
      await page.click(selector, { clickCount: 3 }); 
      await sleep(100);
      await page.keyboard.press('Backspace');
      await sleep(200);
    }

    const chars = text.split('');
    let i = 0;

    while (i < chars.length) {
      const ch = chars[i];

      
      if (Math.random() < 0.03) {
        await sleep(rand(500, 2000));
      }

      
      if (ch === '\n') {
        await sleep(rand(200, 600));
        await page.keyboard.press('Enter');
        i++;
        continue;
      }

      
      const speed = rand(TYPING_SPEED.min, TYPING_SPEED.max);

      
      if (Math.random() < 0.01 && i > 5) {
        const wrongChar = String.fromCharCode(ch.charCodeAt(0) + rand(-2, 2));
        await page.keyboard.type(wrongChar, { delay: speed });
        await sleep(rand(100, 300));
        await page.keyboard.press('Backspace');
        await sleep(rand(50, 150));
      }

      await page.keyboard.type(ch, { delay: speed });
      i++;

      
      if (i % 100 === 0) {
        log.info(`输入中... ${i}/${chars.length}`);
      }
    }

    return true;
  } catch (e) {
    log.warn(`输入失败: ${e.message}`);
    return false;
  }
}

async function humanPaste(page, selector, text) {
  
  try {
    await page.waitForSelector(selector, { visible: true, timeout: 10000 });
    await page.click(selector);
    await randomSleep(CLICK_DELAY.min, CLICK_DELAY.max);

    
    await page.evaluate((sel) => {
      const el = document.querySelector(sel);
      if (el) {
        el.focus();
        
        if (el.innerHTML || el.value) {
          el.innerHTML = '';
          el.value = '';
        }
        
        el.dispatchEvent(new Event('input', { bubbles: true }));
      }
    }, selector);

    await sleep(300);

    
    await page.evaluate((text) => {
      navigator.clipboard.writeText(text);
    }, text);
    await sleep(200);

    await page.keyboard.down('Control');
    await page.keyboard.press('v');
    await page.keyboard.up('Control');
    await sleep(500);

    return true;
  } catch (e) {
    log.warn(`粘贴失败: ${e.message}`);
    
    return await humanType(page, selector, text, { clickFirst: false });
  }
}



async function humanScroll(page, distance = null) {
  const d = distance || rand(200, 600);
  const steps = rand(5, 15);
  const perStep = Math.round(d / steps);

  for (let i = 0; i < steps; i++) {
    await page.evaluate((dy) => window.scrollBy(0, dy), perStep);
    await sleep(rand(30, 80));
  }

  await randomSleep(SCROLL_PAUSE.min, SCROLL_PAUSE.max);
}



function loadCookie() {
  try {
    if (!fs.existsSync(CONFIG_FILE)) return null;
    const config = JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf-8'));
    return config.cookie || null;
  } catch { return null; }
}

function loadDraft(draftPath) {
  try {
    const raw = fs.readFileSync(path.resolve(draftPath), 'utf-8');
    return JSON.parse(raw);
  } catch (e) {
    log.warn(`无法加载草稿: ${draftPath}`);
    return null;
  }
}



async function publishArticle(page, draft) {
  log.step('A1', '导航到知乎写文章页面');
  await page.goto(ARTICLE_PAGE, { waitUntil: 'networkidle2', timeout: 30000 });
  await randomSleep(2000, 4000);
  await humanScroll(page, 100);

  
  const currentUrl = page.url();
  if (currentUrl.includes('signin') || currentUrl.includes('login')) {
    log.warn('未登录！请先运行 auto_cookie.js 获取 Cookie');
    return false;
  }

  log.step('A2', '输入标题');
  
  const titleSelectors = [
    '.WriteIndex-titleInput',           
    '.Editable-title input',             
    '[data-testid="article-title"]',     
    '[placeholder*="标题"]',             
    'textarea[placeholder*="文章"]',
    'input[placeholder*="标题"]',
  ];

  let titleDone = false;
  for (const sel of titleSelectors) {
    try {
      await page.waitForSelector(sel, { timeout: 3000 });
      await humanType(page, sel, draft.title, { clickFirst: true });
      titleDone = true;
      log.ok('标题已输入');
      break;
    } catch {}
  }

  if (!titleDone) {
    log.warn('未找到标题输入框，尝试手动...');
  }

  await randomSleep(ACTION_DELAY.min, ACTION_DELAY.max);

  log.step('A3', '输入正文');
  
  const bodySelectors = [
    '.public-DraftEditor-content',       
    '.ql-editor',                         
    '[data-testid="article-content"]',
    '[contenteditable="true"]',
    '.WriteIndex-richText',
  ];

  let bodyDone = false;
  for (const sel of bodySelectors) {
    try {
      await page.waitForSelector(sel, { timeout: 3000 });
      const box = await page.$(sel);
      if (box) {
        await box.click();
        await sleep(500);
      }
      
      await humanPaste(page, sel, draft.body);
      bodyDone = true;
      log.ok('正文已输入');
      break;
    } catch {}
  }

  if (!bodyDone) {
    log.warn('未找到正文编辑器，尝试通用 contenteditable');
    await humanType(page, '[contenteditable="true"]', draft.body, { clickFirst: true });
  }

  await randomSleep(2000, 4000);
  await humanScroll(page, 300);

  log.step('A4', '点击发布');
  const publishSelectors = [
    'button:has-text("发布")',
    'button:has-text("发布文章")',
    '[data-testid="publish-button"]',
    '.PublishPanel-button',
    'button.PublishButton',
    'button[class*="publish"]',
  ];

  let published = false;
  for (const sel of publishSelectors) {
    if (await humanClick(page, sel)) {
      log.ok('已点击发布按钮');
      published = true;
      break;
    }
  }

  if (!published) {
    log.warn('未找到发布按钮，可能需要手动操作');
  }

  await randomSleep(3000, 5000);

  
  log.ok('文章发布流程完成!');
  return true;
}



async function publishAnswer(page, draft, questionUrls) {
  log.step('B1', `准备回答 ${questionUrls.length} 个问题`);

  for (let qi = 0; qi < questionUrls.length; qi++) {
    const qUrl = questionUrls[qi];
    log.step(`B${qi + 2}`, `回答问题 ${qi + 1}/${questionUrls.length}`);

    
    log.info(`导航: ${qUrl}`);
    await page.goto(qUrl, { waitUntil: 'networkidle2', timeout: 30000 });
    await randomSleep(2000, 4000);

    
    await humanScroll(page, 200);

    
    const answerBtnSelectors = [
      'button:has-text("写回答")',
      'a:has-text("写回答")',
      '[data-testid="answer-button"]',
      '.QuestionHeader button:has-text("回答")',
      'button[class*="answer"]',
    ];

    let btnClicked = false;
    for (const sel of answerBtnSelectors) {
      try {
        if (await humanClick(page, sel)) {
          btnClicked = true;
          log.ok('已点击"写回答"');
          break;
        }
      } catch {}
    }

    if (!btnClicked) {
      
      log.info('尝试直接使用编辑器...');
    }

    await randomSleep(2000, 3000);

    
    log.info('输入回答内容...');
    const editorSelectors = [
      '.public-DraftEditor-content',
      '.ql-editor',
      '[contenteditable="true"]',
      '[data-testid="answer-content"]',
      '.RichText',
    ];

    let contentDone = false;
    for (const sel of editorSelectors) {
      try {
        const el = await page.$(sel);
        if (el) {
          await el.click();
          await sleep(500);
          await humanPaste(page, sel, draft.body);
          contentDone = true;
          log.ok('回答内容已输入');
          break;
        }
      } catch {}
    }

    if (!contentDone) {
      log.warn('未找到编辑器');
      continue;
    }

    await randomSleep(1000, 2000);

    
    const submitSelectors = [
      'button:has-text("发布")',
      'button:has-text("提交回答")',
      'button:has-text("发布回答")',
      '.AnswerForm-footer button.SubmitButton',
      'button[class*="submit"]',
      'button[class*="publish"]',
    ];

    let submitted = false;
    for (const sel of submitSelectors) {
      try {
        if (await humanClick(page, sel)) {
          submitted = true;
          log.ok(`问题 ${qi + 1} 回答已发布`);
          break;
        }
      } catch {}
    }

    if (!submitted) {
      log.warn(`问题 ${qi + 1} 未找到提交按钮`);
    }

    
    if (qi < questionUrls.length - 1) {
      const wait = rand(5000, 15000);
      log.info(`等待 ${Math.round(wait/1000)}s 后回答下一个问题...`);
      await sleep(wait);
    }
  }

  log.step('完成', `全部 ${questionUrls.length} 个问题回答完毕`);
  return true;
}



async function searchAndSelectQuestion(page, questionTitle, maxResults = 5) {
  
  log.info(`搜索: ${questionTitle.substring(0, 40)}...`);

  
  const searchUrl = `https://www.zhihu.com/search?type=content&q=${encodeURIComponent(questionTitle)}`;
  await page.goto(searchUrl, { waitUntil: 'networkidle2', timeout: 20000 });
  await randomSleep(2000, 3000);

  
  const results = await page.evaluate(() => {
    const items = [];
    const links = document.querySelectorAll('a[href*="/question/"]');
    links.forEach(a => {
      const href = a.getAttribute('href');
      const text = a.textContent.trim();
      if (href && text && text.length > 5 && !items.find(i => i.url === href)) {
        items.push({ url: 'https://www.zhihu.com' + href.split('?')[0], title: text });
      }
    });
    return items.slice(0, 10);
  });

  return results.slice(0, maxResults);
}



async function run(options = {}) {
  const {
    mode = 'article',
    draftPath = null,
    questionUrls = [],
    questionCount = 1,
    headless = false,
  } = options;

  console.log('\n╔══════════════════════════════════════════════════╗');
  console.log('║    知乎自动化发布工具 v2.0                        ║');
  console.log('║    Human-like Publisher for Edge Browser          ║');
  console.log('╚══════════════════════════════════════════════════╝\n');

  
  if (!draftPath) {
    
    const drafts = fs.readdirSync(DRAFTS_DIR).filter(f => f.endsWith('.json')).sort().reverse();
    if (drafts.length > 0) {
      draftPath = path.join(DRAFTS_DIR, drafts[0]);
      log.info(`自动加载最新草稿: ${drafts[0]}`);
    } else {
      log.warn('无可用草稿，请先运行 content_writer.py');
      return 1;
    }
  }

  const draft = loadDraft(draftPath);
  if (!draft) {
    log.warn('草稿加载失败');
    return 1;
  }

  log.ok(`草稿已加载: ${(draft.title || draft.topic?.title || '无标题').substring(0, 50)}`);
  log.info(`类型: ${draft.content_type || mode} | 长度: ${(draft.body || '').length} 字`);

  
  const cookies = loadCookie();
  if (!cookies) {
    log.warn('未找到 Cookie 配置，请先运行 auto_cookie.js');
    return 1;
  }

  
  log.step('1', '启动 Edge 浏览器');
  let browser;
  try {
    browser = await puppeteer.launch({
      headless: headless ? 'new' : false,
      executablePath: EDGE_PATH,
      userDataDir: USER_DATA,
      args: [
        '--no-sandbox',
        '--disable-blink-features=AutomationControlled',
        '--no-first-run',
        '--no-default-browser-check',
        '--window-size=1280,900',
      ],
      defaultViewport: null,
    });
    log.ok('浏览器已启动');
  } catch (e) {
    log.warn(`浏览器启动失败: ${e.message}`);
    log.warn('请关闭所有 Edge 窗口后重试');
    return 1;
  }

  let page;
  try {
    const pages = await browser.pages();
    page = pages[0] || await browser.newPage();

    await page.setUserAgent(
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0'
    );

    
    const cookieList = Object.entries(cookies).map(([name, value]) => ({
      name, value, domain: '.zhihu.com', path: '/'
    }));
    await page.setCookie(...cookieList);

    
    await page.evaluate(() => { window.mouseX = 400; window.mouseY = 300; });

    
    if (mode === 'article') {
      await publishArticle(page, draft);
    } else if (mode === 'answer') {
      
      let urls = questionUrls;
      if (urls.length === 0) {
        const questions = loadQuestions(questionCount);
        if (questions.length > 0) {
          
          for (const q of questions) {
            const results = await searchAndSelectQuestion(page, q.title);
            if (results.length > 0) {
              urls.push(results[0].url);
              log.info(`匹配到问题: ${results[0].title.substring(0, 40)}`);
            }
          }
        }
      }

      if (urls.length > 0) {
        await publishAnswer(page, draft, urls);
      } else {
        log.warn('没有需要回答的问题');
      }
    }

    
    log.info('操作完成，5秒后关闭浏览器...');
    await sleep(5000);
    await browser.close();

    console.log('\n╔══════════════════════════════════════════════════╗');
    console.log('║  ✅ 发布流程完成!                                ║');
    console.log('╚══════════════════════════════════════════════════╝\n');

    return 0;

  } catch (e) {
    log.warn(`错误: ${e.message}`);
    if (browser) await browser.close();
    return 1;
  }
}

function loadQuestions(count) {
  
  try {
    const db = require('better-sqlite3'); 
  } catch {
    
    const qFile = path.join(DRAFTS_DIR, 'questions_for_answer.json');
    if (fs.existsSync(qFile)) {
      return JSON.parse(fs.readFileSync(qFile, 'utf-8')).slice(0, count);
    }
  }
  return [];
}



function parseArgs() {
  const args = process.argv.slice(2);
  const options = { mode: 'article', draftPath: null, questionUrls: [], questionCount: 1, headless: false };

  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === 'article' || a === 'answer') options.mode = a;
    else if (a === '--draft' && args[i+1]) { options.draftPath = args[i+1]; i++; }
    else if (a === '--questions' && args[i+1]) { options.questionCount = parseInt(args[i+1]) || 1; i++; }
    else if (a === '--urls' && args[i+1]) { options.questionUrls = args[i+1].split(',').map(u => u.trim()); i++; }
    else if (a === '--headless') options.headless = true;
    else if (a === '--help' || a === '-h') { showHelp(); process.exit(0); }
  }

  return options;
}

function showHelp() {
  console.log(`
知乎自动化发布工具

用法:
  node publisher.js article --draft data/drafts/xxx.json   发布文章
  node publisher.js answer --draft data/drafts/xxx.json     回答问题
  node publisher.js answer --urls url1,url2                指定问题URL
  node publisher.js answer --questions 5                    自动匹配5个问题

选项:
  --draft <path>      草稿文件路径
  --questions <n>     回答问题数量
  --urls <urls>       问题URL列表（逗号分隔）
  --headless          无头模式
`);
}

if (require.main === module) {
  const options = parseArgs();
  run(options).then(code => process.exit(code));
} else {
  module.exports = { run, humanType, humanClick, humanMouseMove, humanPaste };
}
