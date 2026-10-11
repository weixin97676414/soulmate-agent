/**
 * Query a specific hot topic from DailyHot API
 * Usage: node scripts/query-hot.mjs <platform> [--limit N]
 * Example: node scripts/query-hot.mjs zhihu --limit 20
 */

const args = process.argv.slice(2);

// Parse arguments
let platform = args[0] || "all";
let limit = 10;
let showAll = false;

if (platform === "--all" || platform === "all") {
  showAll = true;
}

for (let i = 1; i < args.length; i++) {
  if (args[i] === "--limit" && args[i + 1]) {
    limit = parseInt(args[i + 1]);
    i++;
  }
}

// Remove leading / if present
platform = platform.replace(/^\//, "");

const BASE_URL = process.env.DAILYHOT_URL || `http://localhost:6688`;

async function fetchJSON(url) {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(15000) });
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    if (err.name === "TypeError" || err.message.includes("fetch failed")) {
      console.error(
        `❌ 无法连接到 DailyHot 服务 (${BASE_URL})\n` +
        `💡 请先运行: node scripts/start-server.mjs`
      );
      process.exit(1);
    }
    throw err;
  }
}

function formatList(data) {
  const lines = [];
  lines.push(`\n📋 ${data.title} · ${data.type}`);
  lines.push(`🔗 ${data.link}`);
  lines.push(`📊 共 ${data.total} 条 | 更新: ${new Date(data.updateTime).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}`);
  lines.push("─".repeat(60));

  data.data.slice(0, limit).forEach((item, i) => {
    const num = String(i + 1).padStart(2, " ");
    lines.push(`${num}. ${item.title}`);
    if (item.desc) {
      const short = item.desc.length > 120 ? item.desc.slice(0, 120) + "..." : item.desc;
      lines.push(`   ${short}`);
    }
    if (item.hot) {
      lines.push(`   🔥 ${formatHot(item.hot)}`);
    }
    if (item.author) {
      lines.push(`   👤 ${item.author}`);
    }
    lines.push("");
  });

  if (data.data.length > limit) {
    lines.push(`... 还有 ${data.data.length - limit} 条未显示`);
  }

  return lines.join("\n");
}

function formatHot(hot) {
  if (hot >= 100000000) return `${(hot / 100000000).toFixed(1)} 亿`;
  if (hot >= 10000) return `${(hot / 10000).toFixed(1)} 万`;
  return hot.toLocaleString();
}

function formatAll(data) {
  const lines = [];
  lines.push(`\n📡 DailyHot API 数据源 (${data.count} 个)`);
  lines.push("─".repeat(60));
  data.routes.forEach((r) => {
    if (r.path) {
      lines.push(`  ${r.name.padEnd(18)} ${r.path}`);
    } else {
      lines.push(`  ${r.name.padEnd(18)} ⚠️ ${r.message || "暂不可用"}`);
    }
  });
  lines.push("─".repeat(60));
  lines.push("\n用法: node scripts/query-hot.mjs <platform> [--limit N]");
  lines.push("示例: node scripts/query-hot.mjs zhihu");
  lines.push("      node scripts/query-hot.mjs bilibili --limit 20");
  return lines.join("\n");
}

// Main
if (showAll) {
  const data = await fetchJSON(`${BASE_URL}/all`);
  console.log(formatAll(data));
} else {
  const data = await fetchJSON(`${BASE_URL}/${platform}`);
  if (!data) {
    console.log(`\n❌ 平台 "${platform}" 不存在，请检查名称`);
    console.log("\n可用平台:\n");
    const allData = await fetchJSON(`${BASE_URL}/all`);
    if (allData?.routes) {
      allData.routes
        .filter((r) => r.path)
        .forEach((r) => console.log(`  ${r.name.padEnd(18)} ${r.path}`));
    }
  } else if (data.code === 200 && data.data && data.data.length > 0) {
    console.log(formatList(data));
  } else if (data.code === 200 && (!data.data || data.data.length === 0)) {
    console.log(`\n⚠️ ${platform} 暂无数据`);
  }
}
