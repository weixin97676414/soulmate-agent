/**
 * Cookie 管理器 - Cookie Manager
 * 从配置文件加载 Cookie，管理过期状态
 */

const fs = require('fs');
const path = require('path');

class CookieManager {
  constructor(configPath) {
    this.configPath = configPath || path.join(__dirname, '..', 'config', 'fallback-sources.json');
    this.cookies = null;
  }

  load() {
    try {
      if (!fs.existsSync(this.configPath)) return null;
      const config = JSON.parse(fs.readFileSync(this.configPath, 'utf-8'));
      this.cookies = config.cookie || null;
      return this.cookies;
    } catch (e) {
      return null;
    }
  }

  /**
   * 将 cookie 对象转换为 HTTP Cookie 头字符串
   */
  toHeader() {
    if (!this.cookies) this.load();
    if (!this.cookies) return null;

    const entries = [];
    for (const [key, value] of Object.entries(this.cookies)) {
      if (value) entries.push(`${key}=${value}`);
    }
    return entries.join('; ');
  }

  /**
   * 检查 Cookie 是否可用（至少有关键字段）
   */
  isAvailable() {
    if (!this.cookies) this.load();
    if (!this.cookies) return false;
    // 至少需要 z_c0 或 zhihu_session
    return !!(this.cookies.z_c0 || this.cookies.zhihu_session);
  }

  /**
   * 获取配置的认证优先级
   */
  getAuthPriority() {
    try {
      if (!fs.existsSync(this.configPath)) return null;
      const config = JSON.parse(fs.readFileSync(this.configPath, 'utf-8'));
      return (config.auth && config.auth.priority) || null;
    } catch {
      return null;
    }
  }

  /**
   * 从 Edge 浏览器自动刷新 Cookie（Browser Profile 模式）
   * 启动 Edge，利用已有登录态提取 Cookie，保存到配置文件
   * @returns {object|null} 刷新后的 cookies
   */
  async refreshFromBrowser() {
    const os = require('os');
    const EDGE_PATH = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
    const USER_DATA = path.join(os.homedir(), 'AppData', 'Local', 'Microsoft', 'Edge', 'User Data');

    let puppeteer;
    try {
      puppeteer = require('puppeteer-core');
    } catch {
      // 尝试 puppeteer
      try { puppeteer = require('puppeteer'); } catch { return null; }
    }

    if (!fs.existsSync(EDGE_PATH)) return null;

    let browser;
    try {
      browser = await puppeteer.launch({
        headless: 'new',
        executablePath: EDGE_PATH,
        userDataDir: USER_DATA,
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--no-first-run', '--no-default-browser-check'],
        defaultViewport: { width: 1280, height: 800 },
      });

      const page = await browser.newPage();
      await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0');

      // 导航到知乎
      await page.goto('https://www.zhihu.com', { waitUntil: 'networkidle2', timeout: 20000 });

      // 检测登录状态
      const loggedIn = await page.evaluate(() => {
        try {
          const el = document.getElementById('js-initialData');
          if (!el) return false;
          const data = JSON.parse(el.textContent);
          return !!(data?.initialState?.me?.name || data?.initialState?.currentUser?.name);
        } catch { return false; }
      });

      if (!loggedIn) {
        await browser.close();
        return null;
      }

      // 提取 Cookie
      const allCookies = await page.cookies();
      const zhihuCookies = {};
      for (const c of allCookies) {
        if (c.domain && c.domain.includes('zhihu.com')) {
          zhihuCookies[c.name] = c.value;
        }
      }

      await browser.close();

      if (Object.keys(zhihuCookies).length === 0) return null;

      // 保存到配置文件
      this.cookies = zhihuCookies;
      try {
        let config = {};
        if (fs.existsSync(this.configPath)) {
          config = JSON.parse(fs.readFileSync(this.configPath, 'utf-8'));
        }
        config.cookie = zhihuCookies;
        const dir = path.dirname(this.configPath);
        if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
        fs.writeFileSync(this.configPath, JSON.stringify(config, null, 2), 'utf-8');
      } catch {}

      return zhihuCookies;
    } catch {
      if (browser) try { await browser.close(); } catch {}
      return null;
    }
  }
}

module.exports = CookieManager;
