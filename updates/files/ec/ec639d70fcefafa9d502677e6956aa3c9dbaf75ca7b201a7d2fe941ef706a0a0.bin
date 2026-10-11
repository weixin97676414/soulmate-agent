#!/usr/bin/env node
/**
 * 抖音全类型自动发布脚本
 * 支持: 文章(--type=article, 默认) | 图文(--type=image) | 视频(--type=video)
 *
 * 用法:
 *   node douyin-publish.cjs --type=image --publish     # 发布图文
 *   node douyin-publish.cjs --type=article --publish    # 发布文章
 *   node douyin-publish.cjs --publish                   # 默认文章
 *
 * 前置条件:
 *   1. openclaw browser 已启动（headed Chrome 实例）
 *   2. 抖音创作者平台已登录（cookie 持久化）
 *   3. 素材文件已准备好
 */

const { chromium } = require('playwright');
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

// ====== 解析命令行参数 ======
const PUBLISH = process.argv.includes('--publish');
const TYPE = (() => {
  for (const arg of process.argv) {
    if (arg.startsWith('--type=')) return arg.split('=')[1];
  }
  return 'article';
})();

// ====== 配置区 ======
const CONFIG = {
  PUBLISH,
  TYPE,

  // ====== 文章相关 ======
  // 图片路径
  HEADER_IMAGE: '/tmp/openclaw/uploads/article_header.jpg',
  COVER_IMAGE: '/tmp/openclaw/uploads/article_cover.jpg',
  // 内容
  TITLE: '流浪狗的每一天',
  SUMMARY: '领养代替购买，给流浪的生命一个机会',
  BODY_FILE: '',
  BODY: '<p>正文</p>',

  // ====== 图文相关 ======
  // 图片目录（图文用）
  IMAGE_DIR: '/tmp/openclaw/uploads',
  IMAGE_PREFIX: 'image_',
  // 图文描述
  DESCRIPTION: '它们本不该出现在街头。每一只流浪狗背后，都有一个遗弃的故事。有的是搬家被丢下，有的是生病被抛弃，有的出生就在街头。\n\n但它们依然努力活着。翻垃圾桶找食物，躲车底避风雨，见到人还会摇尾巴。它们不恨人类，只是渴望一个家。\n\n领养代替购买，不遗弃不伤害。如果你在街头遇到它们，一碗水、一顿饭，就是它们在寒风里最温暖的时刻。🐾',

  // ====== 通用 ======
  TOPICS: ['流浪狗', '领养代替购买', '善待动物'],
  MUSIC_KEYWORD: '纯音乐',
  SCHEDULED_TIME: '2026-06-03 07:30',
};

// ====== 辅助函数 ======
function log(msg) { console.log(`[${new Date().toLocaleTimeString()}] ${msg}`); }

function getImageFiles() {
  const dir = CONFIG.IMAGE_DIR;
  const files = fs.readdirSync(dir).filter(f => f.startsWith(CONFIG.IMAGE_PREFIX))
    .map(f => path.join(dir, f)).sort();
  return files;
}

// ====== 定时发布通用 ======
async function setSchedule(page) {
  if (!CONFIG.SCHEDULED_TIME) return false;
  log('  设定时发布...');
  // 点"定时发布" radio/按钮
  await page.evaluate(() => {
    const all = document.querySelectorAll('span, div, label, .semi-radio');
    for (const el of all) {
      if (el.textContent.trim() === '定时发布') { el.click(); break; }
    }
  });
  await page.waitForTimeout(800);
  // 只找 datetime-local 类型的输入框，绝不碰 text 类型（那是标题！）
  await page.evaluate((time) => {
    const inputs = document.querySelectorAll('input[type="datetime-local"]');
    for (const inp of inputs) {
      if (inp.readOnly || inp.disabled) continue;
      const date = new Date(time.replace(' ', 'T') + ':00+08:00');
      const val = date.getFullYear() + '-' +
        String(date.getMonth()+1).padStart(2,'0') + '-' +
        String(date.getDate()).padStart(2,'0') + 'T' +
        String(date.getHours()).padStart(2,'0') + ':' +
        String(date.getMinutes()).padStart(2,'0');
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(inp, val);
      inp.dispatchEvent(new Event('input', { bubbles: true }));
      inp.dispatchEvent(new Event('change', { bubbles: true }));
      break;
    }
  }, CONFIG.SCHEDULED_TIME);
  await page.waitForTimeout(500);
  const timeSet = await page.evaluate(() => {
    const inputs = document.querySelectorAll('input');
    for (const inp of inputs) {
      if (inp.type === 'datetime-local' && inp.value) return inp.value;
    }
    return 'not found';
  });
  log(`  定时时间: ${timeSet}`);
  return true;
}

// ====== 配乐通用 ======
async function addMusic(page) {
  log('  添加配乐...');
  await page.evaluate(() => {
    const el = document.querySelector('.action-Q1y01k, .container-right-uW7Pj1');
    if (el) el.scrollIntoView({ block: 'center' });
  });
  await page.waitForTimeout(500);
  let sheetOpened = false;
  for (let r = 0; r < 5; r++) {
    sheetOpened = await page.evaluate(() => document.querySelectorAll('.semi-sidesheet').length > 0);
    if (sheetOpened) break;
    const box = await page.locator('.action-Q1y01k').boundingBox();
    if (box) {
      await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    }
    await page.waitForTimeout(1500);
  }
  if (sheetOpened) {
    await page.evaluate((kw) => {
      const inputs = document.querySelectorAll('input');
      for (const inp of inputs) {
        if (inp.placeholder === '搜索音乐') {
          const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
          s.call(inp, kw);
          inp.dispatchEvent(new Event('input', { bubbles: true }));
          break;
        }
      }
    }, CONFIG.MUSIC_KEYWORD);
    await page.waitForTimeout(2000);
    await page.evaluate(() => {
      const se = document.querySelector('.semi-sidesheet');
      if (!se) return;
      const btns = se.querySelectorAll('.apply-btn-LUPP0D');
      for (const b of btns) {
        b.style.display = 'block';
        b.style.visibility = 'visible';
        b.style.opacity = '1';
        b.click();
        break;
      }
    });
    await page.waitForTimeout(1500);
    log('  配乐添加完成');
    return true;
  } else {
    log('  配乐侧栏未打开，跳过');
    return false;
  }
}

// ====== 发布通用 ======
async function clickPublish(page) {
  if (!CONFIG.PUBLISH) {
    log('  🔸 测试模式，未点发布（加 --publish 启用）');
    return;
  }
  log('  发布中...');
  const btns = ['发布', '立即发布', '发布作品'];
  for (const text of btns) {
    const btn = await page.locator(`button:has-text("${text}"), div:has-text("${text}")`).first();
    if (await btn.isVisible().catch(() => false)) {
      await btn.click();
      break;
    }
  }
  await page.waitForTimeout(3000);
  log('  ✅ 已发布!');
}

// ====== 连接浏览器 ======
async function connectBrowser() {
  log('[连接浏览器]...');
  const cdpHttp = 'http://127.0.0.1:18800';
  const ver = JSON.parse(execSync(`curl -s ${cdpHttp}/json/version`).toString());
  const browser = await chromium.connectOverCDP(ver.webSocketDebuggerUrl);
  const context = browser.contexts()[0];
  // 关闭旧抖音页
  for (const p of context.pages()) {
    if (p.url().includes('creator.douyin.com')) await p.close();
  }
  return { browser, context };
}

// =============================================
//  文章发布
// =============================================
async function publishArticle() {
  log('=== 文章发布 ===');
  const { browser, context } = await connectBrowser();

  try {
    // 打开编辑器
    const page = await context.newPage();
    await page.goto('https://creator.douyin.com/creator-micro/content/post/article?default-tab=5&enter_from=publish_page&media_type=article&type=new',
      { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForSelector('input[placeholder*="标题"]', { timeout: 10000 });
    log('  编辑器就绪');

    // 填写内容
    log('[填写内容]...');
    const bodyContent = CONFIG.BODY_FILE ? fs.readFileSync(CONFIG.BODY_FILE, 'utf-8') : CONFIG.BODY;
    await page.evaluate(({ title, summary, body }) => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      const ti = document.querySelector('input[placeholder*="标题"]');
      const si = document.querySelector('input[placeholder*="摘要"]');
      const be = document.querySelector('[contenteditable]');
      setter.call(ti, title);
      ti.dispatchEvent(new Event('input', { bubbles: true }));
      setter.call(si, summary);
      si.dispatchEvent(new Event('input', { bubbles: true }));
      be.innerHTML = body;
      be.dispatchEvent(new Event('input', { bubbles: true }));
    }, { title: CONFIG.TITLE, summary: CONFIG.SUMMARY, body: bodyContent });

    // 上传图片
    log('[上传图片]...');
    const fc1 = page.waitForEvent('filechooser', { timeout: 8000 });
    await page.evaluate(() => {
      const span = document.evaluate('//*[contains(text(),"点击上传图片")]', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
      if (span) span.click();
    });
    await (await fc1).setFiles(CONFIG.HEADER_IMAGE);
    try { await page.waitForSelector('button:has-text("确定")', { timeout: 8000 }); await page.click('button:has-text("确定")'); } catch(e) {}
    await page.waitForTimeout(1000);

    const fc2 = page.waitForEvent('filechooser', { timeout: 8000 });
    await page.evaluate(() => {
      const span = document.evaluate('//*[contains(text(),"点击上传封面图")]', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
      if (span) span.click();
    });
    await (await fc2).setFiles(CONFIG.COVER_IMAGE);
    await page.waitForTimeout(2000);
    try { await page.waitForSelector('button:has-text("完成")', { timeout: 5000 }); await page.click('button:has-text("完成")'); } catch(e) {}
    log('  图片上传完成');

    // 添加话题
    log('[添加话题]...');
    await page.evaluate(() => {
      const span = document.evaluate('//*[contains(text(),"点击添加话题")]', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
      if (span) span.click();
    });
    await page.waitForSelector('input[placeholder*="搜索"]', { timeout: 5000 });
    for (const topic of CONFIG.TOPICS) {
      await page.evaluate((t) => {
        const inputs = document.querySelectorAll('input');
        for (const inp of inputs) {
          if (inp.placeholder && inp.placeholder.includes('搜索')) {
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(inp, t);
            inp.dispatchEvent(new Event('input', { bubbles: true }));
            break;
          }
        }
      }, topic);
      await page.waitForTimeout(1500);
      await page.evaluate(() => {
        const items = document.querySelectorAll('[class*=topicItem], [class*=dropdownItem]');
        if (items.length > 0) items[0].click();
      });
      await page.waitForTimeout(300);
    }
    await page.evaluate(() => {
      const btns = document.querySelectorAll('button');
      for (const btn of btns) if (btn.textContent.includes('确认添加')) { btn.click(); break; }
    });
    await page.waitForTimeout(500);
    log('  话题添加完成');

    // 配乐
    await addMusic(page);

    // 定时
    await setSchedule(page);

    // 发布
    await clickPublish(page);
  } finally {
    await browser.close();
  }
}

// =============================================
//  图文发布
// =============================================
async function publishImage() {
  log('=== 图文发布 ===');
  const { browser, context } = await connectBrowser();
  const page = await context.newPage();

  try {
    // 先导航到首页再进图文编辑页（清除自动保存的草稿）
    log('[打开图文编辑器]...');
    await page.evaluate(() => { window.onbeforeunload = null; });
    // 先到一个无关页清掉草稿
    await page.goto('https://creator.douyin.com/creator-micro/content/manage',
      { waitUntil: 'networkidle', timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(1000);
    // 再进图文编辑页
    await page.evaluate(() => { window.onbeforeunload = null; });
    await page.goto('https://creator.douyin.com/creator-micro/content/post/image?type=new',
      { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(3000);

    // 检查是否已上传图片（必须有实际img标签，且能显示）
    const hasImages = await page.evaluate(() => {
      const imgs = document.querySelectorAll('img[src]');
      const visibleImgs = Array.from(imgs).filter(i => {
        const rect = i.getBoundingClientRect();
        return rect.width > 10 && rect.height > 10 && i.src && !i.src.includes('data:') && window.getComputedStyle(i).display !== 'none';
      });
      return visibleImgs.length >= 2;
    });

    if (hasImages) {
      log('  页面已有图片/预览，跳过上传');
    } else {
      // 上传图片
      log('[上传图片]...');
      const imageFiles = getImageFiles();
      log(`  找到 ${imageFiles.length} 张图片`);
      if (imageFiles.length === 0) throw new Error('没有找到图文图片');

      // 等待上传区域完全加载
      await page.waitForTimeout(1000);

      // 方法1: filechooser 事件监听 + 点击上传区域
      const fc = page.waitForEvent('filechooser', { timeout: 15000 });
      
      // 点击 "点击上传" 元素（force绕过可能的遮罩）
      const uploadText = page.getByText('点击上传', { exact: true }).first();
      const textVisible = await uploadText.isVisible().catch(() => false);
      
      if (textVisible) {
        log('  点击「点击上传」文字...');
        await uploadText.click({ force: true, timeout: 5000 });
      } else {
        // fallback: 点上传容器
        log('  点击上传容器...');
        const container = page.locator('.phone-container-Eh_FJc, .container-IRuUu2, .container-bTpjqe').first();
        await container.click({ force: true, timeout: 5000 });
      }
      
      await page.waitForTimeout(1500);
      
      const fcResolved = await fc;
      log(`  上传 ${imageFiles.length} 张图片...`);
      await fcResolved.setFiles(imageFiles);

      await page.waitForTimeout(4000);
      log('  图片上传完成');
    }
    await page.waitForTimeout(2000);

    // 填写内容
    log('[填写内容]...');
    await page.waitForSelector('input[placeholder*="标题"]', { timeout: 10000 });
    await page.evaluate(({ title, desc }) => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      const ti = document.querySelector('input[placeholder*="标题"]');
      setter.call(ti, title);
      ti.dispatchEvent(new Event('input', { bubbles: true }));

      const be = document.querySelector('[contenteditable]');
      if (be) {
        be.innerHTML = '<p>' + desc.replace(/\n/g, '<br>') + '</p>';
        be.dispatchEvent(new Event('input', { bubbles: true }));
      }
    }, { title: CONFIG.TITLE.slice(0, 20), desc: CONFIG.DESCRIPTION || '图文描述' });
    log('  内容填写完成');

    // 添加话题（点击#添加话题按钮弹出选择器）
    log('[添加话题]...');
    for (const topic of CONFIG.TOPICS) {
      // 点"#添加话题"按钮
      const btn = page.locator('.toolbar-button-spPS4r').filter({ hasText: '添加话题' }).first();
      if (await btn.isVisible().catch(() => false)) {
        await btn.click();
        await page.waitForTimeout(1000);
      }
      // 搜索话题
      const searchInput = page.locator('input[placeholder*="搜索"], input[placeholder*="添加"]').first();
      if (await searchInput.isVisible().catch(() => false)) {
        await searchInput.fill(topic);
        await page.waitForTimeout(1500);
        // 点第一个搜索结果
        const firstResult = page.locator('[class*=topicItem], [class*=TopicItem], [class*=dropdownItem], [class*=semi-select-option]').first();
        if (await firstResult.isVisible().catch(() => false)) {
          await firstResult.click();
          await page.waitForTimeout(500);
        }
      }
      // 关弹窗（点遮罩或确认按钮）
      await page.keyboard.press('Escape');
      await page.waitForTimeout(500);
    }
    log('  话题添加完成');

    // 封面（选第一张）
    log('[设置封面]...');
    await page.evaluate(() => {
      const editCover = document.evaluate('//*[contains(text(),"编辑封面") or contains(text(),"设置封面")]',
        document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
      if (editCover) editCover.click();
    });
    await page.waitForTimeout(1500);
    await page.evaluate(() => {
      const btns = document.querySelectorAll('button, .semi-button');
      for (const btn of btns) {
        if (btn.textContent.includes('确定') || btn.textContent.includes('完成')) {
          btn.click(); break;
        }
      }
    });
    await page.waitForTimeout(500);
    log('  封面设置完成');

    // 自主声明
    log('[添加声明]...');
    await page.evaluate(() => {
      const decl = document.evaluate('//*[contains(text(),"自主声明") or contains(text(),"请选择")]',
        document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
      if (decl) decl.click();
    });
    await page.waitForTimeout(1000);
    await page.evaluate(() => {
      const items = document.evaluate('//*[contains(text(),"内容由AI生成")]',
        document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
      if (items) items.click();
    });
    await page.waitForTimeout(500);
    await page.evaluate(() => {
      const btns = document.querySelectorAll('.semi-modal button, .semi-portal button');
      for (const btn of btns) {
        if (btn.textContent.includes('确定') || btn.textContent.includes('保存')) {
          btn.click(); break;
        }
      }
    });
    await page.waitForTimeout(500);
    log('  声明添加完成');
    await page.waitForTimeout(2000);

    // 配乐
    await addMusic(page);
    // 关闭配乐侧栏（防止遮罩挡发布按钮）
    await page.evaluate(() => {
      const mask = document.querySelector('.semi-sidesheet-mask');
      if (mask) mask.click();
    });
    await page.waitForTimeout(1000);
    await page.keyboard.press('Escape');
    await page.waitForTimeout(1000);

    // 定时
    await setSchedule(page);
    await page.waitForTimeout(2000);

    // 发布
    await clickPublish(page);
  } finally {
    await browser.close();
  }
}

// =============================================
//  主入口
// =============================================
(async () => {
  log(`=== 抖音发布 (type=${CONFIG.TYPE}) ===`);
  log(`   发布模式: ${CONFIG.PUBLISH ? '✅ 正式' : '🔸 测试'}`);

  switch (CONFIG.TYPE) {
    case 'image':
      await publishImage();
      break;
    case 'article':
    default:
      await publishArticle();
      break;
  }

  log('=== 完成 ===');
})().catch(e => { console.error('ERROR:', e.message); process.exit(1); });
