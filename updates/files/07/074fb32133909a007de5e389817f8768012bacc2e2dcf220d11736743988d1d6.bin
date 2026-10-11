/**
 * 备用源获取 - Fallback Source Fetcher
 * 从无需认证的备用数据源获取知乎热榜
 */

const fs = require('fs');
const path = require('path');

class FallbackFetcher {
  constructor(configPath) {
    this.configPath = configPath || path.join(__dirname, '..', 'config', 'fallback-sources.json');
    this.sources = [];
    this.loadConfig();
  }

  loadConfig() {
    try {
      if (!fs.existsSync(this.configPath)) {
        this.sources = this.getDefaultSources();
        return;
      }
      const config = JSON.parse(fs.readFileSync(this.configPath, 'utf-8'));
      this.sources = (config.fallbacks && config.fallbacks.length > 0)
        ? config.fallbacks
        : this.getDefaultSources();
    } catch {
      this.sources = this.getDefaultSources();
    }
  }

  getDefaultSources() {
    return [
      {
        name: 'zhihu-hot-hub',
        url: 'https://raw.githubusercontent.com/snaildev/zhihu-hot-hub/master/data/zhihu-hot.json',
        type: 'json',
        priority: 1
      },
      {
        name: 'zhihu-trending',
        url: 'https://api.zhihu.com/topstory/hot-lists/total?limit=50&reverse_order=0',
        type: 'json_api',
        priority: 2
      }
    ];
  }

  /**
   * 解析 zhihu-hot-hub 格式
   */
  parseHotHubData(raw) {
    const items = [];
    if (Array.isArray(raw)) {
      raw.forEach((item, index) => {
        items.push({
          rank: index + 1,
          title: item.title || item.name || '',
          url: item.url || item.link || '',
          heat: item.heat || item.hot || 0,
          author: item.author || '',
          summary: item.excerpt || item.summary || ''
        });
      });
    }
    return items;
  }

  /**
   * 解析知乎官方API格式
   */
  parseZhihuApiData(raw) {
    const items = [];
    const dataList = raw.data || [];
    dataList.forEach((item, index) => {
      const target = item.target || {};
      items.push({
        rank: index + 1,
        title: target.title || target.title_area?.text || '',
        url: `https://www.zhihu.com/question/${target.id}`,
        heat: parseInt(item.detail_text?.replace(/[^0-9]/g, '') || '0', 10) || 0,
        author: '',
        summary: target.excerpt || ''
      });
    });
    return items;
  }

  async fetch() {
    // 按优先级排序
    const sorted = [...this.sources].sort((a, b) => (a.priority || 99) - (b.priority || 99));

    for (const source of sorted) {
      try {
        const response = await fetch(source.url, {
          headers: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
          },
          signal: AbortSignal.timeout(15000)
        });

        if (!response.ok) continue;

        const raw = await response.json();
        let items;

        if (source.type === 'json_api' || source.url.includes('api.zhihu.com')) {
          items = this.parseZhihuApiData(raw);
        } else {
          items = this.parseHotHubData(raw);
        }

        if (items.length > 0) {
          return {
            meta: {
              source: 'zhihu',
              mode: 'hot',
              auth_method: 'fallback_source',
              fallback_name: source.name,
              fetch_time: new Date().toISOString(),
              rate_limited: true,
              count: items.length
            },
            data: items
          };
        }
      } catch {
        // 尝试下一个备用源
        continue;
      }
    }

    return null;
  }
}

module.exports = FallbackFetcher;
