#!/bin/bash
# 跨境多语种商品文案生成器 部署/自检脚本
# 功能：检查运行环境、设置运行权限、测试运行
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
PY_FILE="$DIR/cross_border_copywriter.py"
TXT_FILE="$DIR/requirements.txt"

echo "============================================="
echo "检查 Python 版本..."
command -v python3 >/dev/null 2>&1 || { echo "错误：未检测到 python3，请安装 Python 3.7+"; exit 1; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 7) else 1)' \
  || { echo "错误：需要 Python 3.7 及以上版本"; exit 1; }

for f in "$PY_FILE" "$TXT_FILE"; do
  [ -f "$f" ] || { echo "错误：缺少文件 $f"; exit 1; }
done

chmod +x "$PY_FILE"
echo "测试运行生成器..."
python3 "$PY_FILE" >/dev/null && echo "部署完成，可直接运行：python3 $PY_FILE" \
  || { echo "测试运行失败，请检查运行环境"; exit 1; }
