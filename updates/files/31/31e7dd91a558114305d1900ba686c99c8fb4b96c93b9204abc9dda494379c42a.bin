/**
 * 频率限制器 - Rate Limiter
 * 默认2秒/次，避免触发知乎反爬机制
 */
class RateLimiter {
  constructor(minIntervalMs = 2000) {
    this.minIntervalMs = minIntervalMs;
    this.lastCallTime = 0;
  }

  async wait() {
    const now = Date.now();
    const elapsed = now - this.lastCallTime;
    if (elapsed < this.minIntervalMs) {
      const delay = this.minIntervalMs - elapsed;
      await new Promise(resolve => setTimeout(resolve, delay));
    }
    this.lastCallTime = Date.now();
  }

  async execute(fn) {
    await this.wait();
    return fn();
  }
}

module.exports = RateLimiter;
