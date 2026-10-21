import { fileURLToPath, URL } from 'node:url'

import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig, type Plugin } from 'vite'

/**
 * 注入 CSP。生产与开发用**两套策略**。
 *
 * 生产是严格的 `script-src 'self'`（无 unsafe-eval、无 unsafe-inline）。
 *
 * 开发模式原先**完全不注入 CSP**，理由是 Vite 会注入内联脚本（React Refresh
 * 预置代码），严格策略会把它拦掉、HMR 直接失效。这个理由是成立的，但
 * "索性什么都不加"并不是唯一选择 —— 下面这套开发策略允许内联脚本/求值
 * （开发必需），同时保留三条**零成本**的硬边界：
 *
 * - `object-src 'none'`   —— 挡住把用户上传的文件当插件嵌入；
 * - `base-uri 'none'`     —— 挡住 `<base>` 劫持（改写后所有相对路径都会被带走）；
 * - `frame-ancestors 'none'` —— 挡住套壳。
 *
 * 这三条不影响任何开发流程，所以"开发环境反正是自己机器"不该成为省掉它们的理由：
 * 调试"打开用户上传的 HTML"这类功能时，被利用的恰恰是本机。
 *
 * 注意这里**不假装**开发态获得了和生产一样的 XSS 防护 —— 那需要禁掉
 * `unsafe-inline`，而它与 HMR 不可兼得。真正的防线在生产构建里。
 */
function cspPlugin(): Plugin {
  const prodPolicy = [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    // 图片放开**任意 https**：模型回答里贴的外链图（图表、示意图）要能直接显示。
    // ⚠️ 这是刻意接受的代价：图片请求会把 URL 发出去，等于给模型留了一条"把内容编进
    // 图片地址外发"的通道，也会把本机 IP 与访问记录暴露给图床。用户明确要"图能显示"，
    // 所以放开；要收紧就把 https: 删掉退回 'self' data: blob:。
    // **本机图片不走这里** —— 那条路是核心代理（/v1/media/local-image）+ blob:，
    // 所以这里也不放 file:（少一条能读本地文件的路径）。
    "img-src 'self' data: blob: https:",
    "font-src 'self' data:",
    // 只允许连接本地核心；本地服务端口是随机分配的，因此用通配端口
    "connect-src 'self' http://127.0.0.1:* http://localhost:* ws://localhost:*",
    "object-src 'none'",
    "base-uri 'none'",
    "frame-ancestors 'none'",
  ].join('; ')

  const devPolicy = [
    "default-src 'self'",
    // 开发态必须放开这两项，否则 Vite 的 HMR 客户端与 React Refresh 都跑不起来
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
    "style-src 'self' 'unsafe-inline'",
    // 与生产一致（理由见 prodPolicy 里那段注释）：外链图要能显示
    "img-src 'self' data: blob: https:",
    "font-src 'self' data:",
    "connect-src 'self' http://127.0.0.1:* http://localhost:* ws://localhost:* ws://127.0.0.1:*",
    "object-src 'none'",
    "base-uri 'none'",
    "frame-ancestors 'none'",
  ].join('; ')

  let isBuild = false

  return {
    name: 'agent-desktop-csp',
    configResolved(config) {
      // 用 Vite 给的 command 判断，而不是读 process.env.NODE_ENV ——
      // 后者的取值取决于启动方式，`vite build` 在别处被调用时并不一定是
      // "production"，判断错了就会把宽松策略打进安装包。
      isBuild = config.command === 'build'
    },
    transformIndexHtml() {
      const policy = isBuild ? prodPolicy : devPolicy
      // ⚠️ 不用 `html.replace('<head>', ...)`：哪天 `index.html` 的 `<head>` 变成
      // 带属性、带换行或大小写不同，这个替换会**静默失效** —— 产物里一条 CSP 都没有，
      // 而验收脚本只比字符串，看不出来（历史归档 F9 记的就是这一类）。
      // 用 Vite 官方的标签注入：它自己找 head，插不进去会报错而不是悄悄放过。
      return [
        {
          tag: 'meta',
          attrs: {
            'http-equiv': 'Content-Security-Policy',
            content: policy,
          },
          injectTo: 'head-prepend' as const,
        },
      ]
    },
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), cspPlugin()],
  // Electron 生产环境用 file:// 加载 index.html，必须用相对路径
  base: './',
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@shared': fileURLToPath(new URL('./shared', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    chunkSizeWarningLimit: 1500,
  },
})
