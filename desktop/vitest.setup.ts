/**
 * 单测的启动文件（第 92 批，H-07(A)）。
 *
 * ## 为什么需要自己造一个 `localStorage`
 *
 * 新版 Node **自带一个实验性的 webstorage 全局**：它存在，但**方法是空的**
 * （要靠 `--localstorage-file` 给路径才能用，否则只会打一句
 * `Warning: --localstorage-file was provided without a valid path`）。
 * 而它出现得比 happy-dom 早，happy-dom 没能把它换掉 —— 实测探针：
 * `window.localStorage === localStorage` 为真、但 `typeof localStorage.getItem` 是 **undefined**。
 *
 * 后果很脏：我们的 store 模块在 **import 时**就会读它（zustand 的 `create`
 * 会立刻执行初始化函数），于是整套用例在**收集阶段**就炸，报一句
 * `localStorage.getItem is not a function` —— 看起来像业务代码调用写错了，
 * 其实是环境冲突（这个坑值得写在这里，下次见到别去翻 store）。
 *
 * ⇒ 直接换上我们自己的一份内存实现。只需要 get/set/remove/clear 四个方法
 * （外加 `length` 与 `key`），不必引 jsdom 那套完整的 Storage。
 */

class MemoryStorage {
  private readonly data = new Map<string, string>()

  get length(): number {
    return this.data.size
  }

  clear(): void {
    this.data.clear()
  }

  getItem(key: string): string | null {
    return this.data.has(key) ? (this.data.get(key) as string) : null
  }

  key(index: number): string | null {
    return [...this.data.keys()][index] ?? null
  }

  removeItem(key: string): void {
    this.data.delete(key)
  }

  setItem(key: string, value: string): void {
    this.data.set(key, String(value))
  }
}

// 只在有 DOM 的环境里装（纯函数用例跑在 node 环境，不该被强塞一个 window 的替身）。
// ⚠️ vitest 的 DOM 环境里 `window` 就是 `globalThis`，所以装在 globalThis 上两边都生效。
if (typeof window !== 'undefined') {
  for (const name of ['localStorage', 'sessionStorage'] as const) {
    Object.defineProperty(globalThis, name, {
      value: new MemoryStorage(),
      configurable: true,
      writable: true,
    })
  }
}
