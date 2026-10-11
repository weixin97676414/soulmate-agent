#!/bin/bash
# Chrome headless 高清截图封装。
# 用法: render_html.sh <html_path> <out_png> <width> <height> [scale=2]
#
# 要点（踩坑记录）:
#   - 必须用本机 Chrome headless，不要用 omp browser / cmux（视口被锁成 777x1223 竖屏）
#   - force-device-scale-factor=2 输出 2x 高清（进 Word 不糊）
#   - window-size 必须与 HTML 页面 .page 的显式宽高一致，否则出现白边/裁剪
#   - HTML 页面的容器必须显式 width/height（子元素全 absolute 时高度坍缩→截出空白图）
#   - HTML 路径必须转绝对路径：file:// 相对路径会被浏览器解析成非法 URL → 整页白屏
#   - virtual-time-budget=2500 足够（页面无动画，LABEL_JS 立即执行），省 ~5s/图
set -e
HTML="$1"; OUT="$2"; W="$3"; H="$4"; SCALE="${5:-2}"
HTML="$(cd "$(dirname "$HTML")" && pwd)/$(basename "$HTML")"   # 强制绝对路径
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if [ ! -x "$CHROME" ]; then
  CHROME="$(command -v chromium || command -v google-chrome || command -v chrome)"
fi
"$CHROME" --headless --disable-gpu --hide-scrollbars \
  --force-device-scale-factor="$SCALE" \
  --window-size="$W,$H" \
  --screenshot="$OUT" \
  --virtual-time-budget=2500 \
  "file://$HTML" 2>/dev/null >/dev/null
echo "saved $OUT"
