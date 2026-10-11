import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vitest/config'

/**
 * 前端单测（第 92 批引入，H-07(A)）。
 *
 * ## 为什么现在才有
 *
 * 渲染层此前**没有任何自动化测试**：改一个 store 或一个格式化函数，
 * 只能靠打包闸的结构断言（"源码里还有没有那句话"）+ 手工点一遍。
 * 结构断言守不住行为 —— 它不知道"带按钮的通知会不会自己消失"。
 *
 * ## 默认 node，需要 DOM 的文件自己声明
 *
 * 多数被测对象是纯函数（格式化、预算判定），在 node 环境里跑最快。
 * 而 store 模块在 **import 时**就会读 `localStorage`（zustand 的 `create`
 * 会立刻执行初始化函数），那种文件在测试顶部加一行
 * `// @vitest-environment happy-dom` 即可 —— 比全局套一个 DOM 环境更快，
 * 也让"这个测试为什么需要 DOM"写在需要它的那个文件里。
 *
 * ## 别名必须与 `vite.config.mts` 一致
 *
 * 源码里到处是 `@/lib/format` 这种导入；两边不一致的表现是"构建能过、
 * 测试报找不到模块"，而排查时会先怀疑测试配置本身。
 */
export default defineConfig({
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@shared': fileURLToPath(new URL('./shared', import.meta.url)),
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts', 'electron/**/*.test.ts'],
    // 启动文件里只做一件事：把 Node 22+ 自带的那个残缺 `localStorage` 换成 DOM 的
    //（不换的话，凡是在 import 时读它的 store 都会在收集阶段就炸，见该文件注释）
    setupFiles: ['./vitest.setup.ts'],
    // 单测不该依赖执行顺序：每个文件独立环境，互不污染（store 是模块级单例）
    isolate: true,
  },
})
