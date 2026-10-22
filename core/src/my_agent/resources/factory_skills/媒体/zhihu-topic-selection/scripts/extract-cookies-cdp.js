#!/usr/bin/env node







const { execSync, spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const EDGE_PATH = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const USER_DATA = process.env.LOCALAPPDATA + '\\Microsoft\\Edge\\User Data';
const DEBUG_PORT = 9223;
const CONFIG_PATH = path.join(__dirname, '..', 'config', 'fallback-sources.json');

async function main() {
  console.log('知乎 Cookie 提取 (CDP 方式)');
  console.log('=' .repeat(50));

  
  console.log('[1/4] 启动 Edge (调试模式)...');
  const browser = spawn(EDGE_PATH, [
    `--remote-debugging-port=${DEBUG_PORT}`,
    `--user-data-dir=${USER_DATA}`,
    '--headless=new',
    '--no-first-run',
    '--no-default-browser-check',
    'about:blank'
  ], {
    stdio: 'ignore',
    detached: false
  });

  
  console.log('[2/4] 等待 CDP 就绪...');
  await sleep(3000);

  
  console.log('[3/4] 提取 Cookie...');

  try {
    
    const httpResp = await fetch(`http://127.0.0.1:${DEBUG_PORT}/json/version`);
    const versionInfo = await httpResp.json();
    const wsUrl = versionInfo.webSocketDebuggerUrl;
    console.log(`  CDP endpoint: ${wsUrl.substring(0, 50)}...`);

    
    const WebSocket = require('ws');
    const ws = new WebSocket(wsUrl);

    const cookies = await new Promise((resolve, reject) => {
      ws.on('open', () => {
        
        ws.send(JSON.stringify({
          id: 1,
          method: 'Network.getCookies',
          params: { urls: ['https://www.zhihu.com', 'https://zhihu.com'] }
        }));
      });

      ws.on('message', (data) => {
        const msg = JSON.parse(data.toString());
        if (msg.id === 1) {
          resolve(msg.result?.cookies || []);
          ws.close();
        }
      });

      ws.on('error', reject);
      setTimeout(() => reject(new Error('timeout')), 10000);
    });

    
    console.log(`  获取到 ${cookies.length} 个 cookie`);

    const cookieObj = {};
    for (const c of cookies) {
      cookieObj[c.name] = c.value;
      const shortVal = c.value.length > 40 ? c.value.substring(0, 40) + '...' : c.value;
      console.log(`  ${c.name} = ${shortVal}`);
    }

    console.log(`\n[4/4] 写入配置文件...`);
    const config = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf-8'));
    config.cookie = cookieObj;
    fs.writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2), 'utf-8');
    console.log(`  ✅ 已保存到 ${CONFIG_PATH}`);

    
    const keyCookies = ['z_c0', '_xsrf', 'd_c0'];
    const hasKeyCookies = keyCookies.every(k => cookieObj[k]);
    if (hasKeyCookies) {
      console.log(`\n✅ Cookie 配置完成! z_c0, _xsrf, d_c0 均已获取`);
      console.log(`   现在可以运行: python3 scripts/save_to_db.py 100 recommend`);
    } else {
      console.log(`\n⚠️  缺少部分关键 cookie`);
      console.log(`   z_c0: ${cookieObj.z_c0 ? '✅' : '❌'}`);
      console.log(`   _xsrf: ${cookieObj._xsrf ? '✅' : '❌'}`);
      console.log(`   d_c0: ${cookieObj.d_c0 ? '✅' : '❌'}`);
    }

  } catch (e) {
    console.error(`\n❌ CDP 连接失败: ${e.message}`);
    console.error('   可能原因:');
    console.error('   1. Edge 启动失败');
    console.error('   2. 端口被占用');
    console.error('   3. ws 模块未安装 (npm install ws)');
  } finally {
    
    browser.kill();
  }
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

main().catch(e => {
  console.error('错误:', e.message);
  process.exit(1);
});
