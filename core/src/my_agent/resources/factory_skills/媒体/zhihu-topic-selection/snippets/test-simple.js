#!/usr/bin/env node
/**
 * 简单测试脚本 - Simple Test Script
 * 测试 fallback source 是否可用
 */

const FallbackFetcher = require('./fallback');

async function main() {
  console.log('测试备用源 ...');
  console.log('');

  const fallback = new FallbackFetcher();
  const result = await fallback.fetch();

  if (result && result.data.length > 0) {
    console.log(`✅ 成功! 通过 ${result.meta.fallback_name} 获取 ${result.data.length} 条数据`);
    console.log('');
    console.log('前5条:');
    result.data.slice(0, 5).forEach(item => {
      const heat = item.heat ? `${(item.heat / 10000).toFixed(1)}W` : '-';
      console.log(`  #${item.rank}  ${heat}  ${item.title}`);
    });
  } else {
    console.log('❌ 所有备用源均失败');
    console.log('   请检查网络连接，或配置 Cookie 以使用高级认证方式');
    console.log('   编辑 config/fallback-sources.json 添加 cookie 后重试');
  }
}

main().catch(e => {
  console.error(`错误: ${e.message}`);
  process.exit(1);
});
