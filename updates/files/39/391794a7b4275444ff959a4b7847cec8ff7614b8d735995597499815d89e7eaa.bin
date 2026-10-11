#!/bin/bash
# 短剧爆款预演器 v2.1.5 - 零配置安装脚本
# 运行方式: chmod +x setup.sh && ./setup.sh

set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
BUNDLE="$DIR/bundle-2.1.5.js"
SCRIPT="$DIR/run-hit-preview.sh"

echo "🎬 短剧爆款预演器 v2.1.5 - 安装中..."

# 1. 检查 Node.js
if ! command -v node &> /dev/null; then
  echo "❌ 需要 Node.js >= 22，请先安装: https://nodejs.org"
  exit 1
fi

echo "✅ Node.js $(node -v)"

# 2. 检查 bundle 文件
if [ ! -f "$BUNDLE" ]; then
  echo "❌ 未找到 bundle-2.1.5.js"
  exit 1
fi

# 3. 设置运行脚本可执行权限
chmod +x "$SCRIPT" 2>/dev/null || true

echo ""
echo "🎉 安装完成！立即使用："
echo ""
echo "  # 测试连接"
echo "  $SCRIPT test"
echo ""
echo "  # 分析剧本"
echo "  $SCRIPT analyze -f 剧本.txt -p 抖音"
echo ""
echo "  # 生成弹幕"
echo "  $SCRIPT danmaku -f 剧本.txt -p B站"
echo ""
echo "📖 详细说明请查看 SKILL.md"
