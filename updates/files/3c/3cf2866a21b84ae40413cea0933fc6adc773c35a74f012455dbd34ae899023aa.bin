#!/usr/bin/env python3
"""
小红书笔记预览生成器

生成拟真手机端 HTML 预览页，含：
- 标题/正文/标签/作者信息
- 6 张配图轮播（支持真实图片路径）
- 字数校验（标题 ≤20、正文 ≤1000）
- 违禁词扫描（内置 100+ 高频词）
- 中英兼容：内容中文，文案中文

用法：
  python scripts/preview_generator.py \
    --title "..." --content "..." --tags "..." \
    --author "..." --images "img1.png,img2.png,..." \
    --output ./preview.html
"""
from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import sys
from datetime import datetime


# ============================================================
# 平台硬规则
# ============================================================

TITLE_MAX = 20          # 小红书标题上限
CONTENT_MAX = 1000      # 小红书正文上限（普通图文）
TAG_MIN, TAG_MAX = 2, 10


# ============================================================
# 内置违禁词扫描（核心高频词；完整清单见 references/compliance-checklist.md）
# 用正则模式而不是字面量，避免"最近""最终""最好"这类合法上下文被误判。
# 命中不阻断，仅打印告警，由人或上游 Agent 决定是否替换。
# ============================================================

import re  # 顶部已 import

# (pattern, label) — label 是打印时用的关键词
BANNED_PATTERNS: list[tuple[str, str]] = [
    # 极限词
    (r"最(?!近|终|多|新|高|低|少|差|爱|好|后|终|开始|起码|小|大|初|后|难|终)", "极限词「最X」"),
    (r"最佳|最高级|最优|最强|最便宜|最有效|最快|最火|最受欢迎|最显瘦|最百搭|最划算|最耐用|最温和|最滋润", "极限词"),
    (r"全网第一|销量第一|全网最低|行业第一|全网最优|史上最强", "极限词（排名）"),
    (r"100%|百分百|万能|永久|永不复发|终身有效|根治|全部消除|彻底解决|零风险|零差评|零失败", "极限词（承诺）"),
    (r"yyds|天花板|封神|绝绝子|无敌|神级|宇宙级|完美(?!主义|的)", "极限词（网络流行）"),
    (r"独家|唯一(?!的)|仅此一家|首款|首发(?!于)|首个(?!于)", "极限词（独家/首发）"),
    (r"NO\.1|TOP1", "极限词（排名缩写）"),

    # 医疗功效
    (r"治疗|治愈|根治|痊愈|消炎|杀菌|防癌|抗癌|干细胞|胎盘素|激素", "医疗功效（疾病/成分）"),
    (r"降血糖|降血压|降血脂|排毒|细胞再生|修复激素脸", "医疗功效（调理）"),
    (r"美白|祛斑|淡斑|祛痘|除皱|抗衰老|瘦身|燃脂|丰胸", "医疗功效（美妆，命中提示品类相关）"),

    # 站外导流
    # 中文场景下不能用 \b（word boundary），中文字符不在 \w 集合里，\b 几乎不触发。
    # 这里宁可放过"我用微信"这种轻微误报，也要把"加微信""加我"这种典型违规命中。
    (r"微信|vx|加微|加我|QQ|私聊|扫码|进群|看主页|主页留", "站外导流（联系方式）"),
    (r"微商|代购|代购私单|dy\b|dy号|站外链接|包裹放", "站外导流（联系方式）"),
    (r"抖音|淘宝|天猫|京东|拼多多|闲鱼|转转|1688|唯品会", "站外导流（竞品平台名）"),

    # 虚假权威
    (r"国家级|世界级|国宴|特供|免检|三甲医院|三甲同款|专家推荐|医生推荐|诺贝尔|驰名商标", "虚假权威"),

    # 金融
    (r"保本|稳赚|高收益|保底收益|躺赚|日入几百|月入过万|虚拟货币|区块链投资|比特币", "金融诱导"),

    # 焦虑营销
    (r"再不买就没|抢疯了|万人疯抢|再不护肤就烂脸|错过再无|手慢无", "焦虑营销"),
]

# BANNED_PATTERNS 各 index → 分类
_PATTERN_CATEGORY: list[str] = (
    ["极限词"] * 7
    + ["医疗功效"] * 3
    + ["站外导流"] * 3
    + ["虚假权威", "金融诱导", "焦虑营销"]
)

# 编译为带分类信息的扫描器列表：[(分类, compiled_regex, label), ...]
BANNED_COMPILED: list[tuple[str, "re.Pattern[str]", str]] = [
    (_PATTERN_CATEGORY[i], re.compile(pat), label)
    for i, (pat, label) in enumerate(BANNED_PATTERNS)
]


def scan_banned_words(text: str) -> list[tuple[str, str, str]]:
    """返回 [(分类, 命中关键词标签, 上下文片段), ...]，每分类最多前 3 条命中。"""
    # 占位符 [待填：…] / [待填:…] 不参与合规扫描——它们的字符是模板/示例，不进入最终发布稿。
    # 跳过占位符可以避免用户在反幻觉占位文案里反复看到假阳性告警。
    text = re.sub(r"\[待填[：:][^\]]*\]", "", text)
    hits: list[tuple[str, str, str]] = []
    seen_per_category: dict[str, set[str]] = {}
    for category, regex, label in BANNED_COMPILED:
        seen_per_category.setdefault(category, set())
        if len(seen_per_category[category]) >= 3:
            continue
        m = regex.search(text)
        if not m:
            continue
        word = m.group(0)
        if word in seen_per_category[category]:
            continue
        seen_per_category[category].add(word)
        idx = m.start()
        start = max(0, idx - 8)
        end = min(len(text), idx + len(word) + 8)
        snippet = text[start:end].replace("\n", " ")
        hits.append((category, f"{label}「{word}」", f"…{snippet}…"))
    return hits


# ============================================================
# 字数与标签校验
# ============================================================

def count_text_units(text: str) -> int:
    """中文字符按 1 计，英文/数字按 1 计，emoji 按 1 计（近似字符数）。"""
    # 去除 markdown 加粗标记
    cleaned = re.sub(r"\*\*", "", text)
    return len(cleaned)


def count_chars_zh(text: str) -> int:
    """小红书后台按字符数限制（含标点）。这里返回近似字符数。"""
    return count_text_units(text)


def validate(title: str, content: str, tags: list[str]) -> list[str]:
    """返回告警列表（不阻断）。"""
    warnings: list[str] = []
    if not title:
        warnings.append("[错误] 标题为空")
    else:
        t_len = count_chars_zh(title)
        if t_len > TITLE_MAX:
            warnings.append(
                f"[字数] 标题 {t_len} 字，超过平台上限 {TITLE_MAX} 字——发布时会被截断，建议改短"
            )
        elif t_len < 12:
            warnings.append(
                f"[建议] 标题仅 {t_len} 字，建议用满 14–20 字（搜索权重更高）"
            )

    if not content:
        warnings.append("[错误] 正文为空")
    else:
        c_len = count_chars_zh(content)
        if c_len > CONTENT_MAX:
            warnings.append(
                f"[字数] 正文 {c_len} 字，超过平台上限 {CONTENT_MAX} 字——必须砍到 {CONTENT_MAX} 字以内"
            )
        elif c_len < 150:
            warnings.append(
                f"[建议] 正文仅 {c_len} 字，过短会限流；干货型建议 600–900 字"
            )

    if tags:
        if len(tags) < TAG_MIN:
            warnings.append(f"[标签] 仅 {len(tags)} 个标签，建议至少 2 个")
        elif len(tags) > TAG_MAX:
            warnings.append(
                f"[标签] {len(tags)} 个标签过多，建议控制在 {TAG_MAX} 个以内（防堆砌判垃圾）"
            )
        # 检测是否含英文标签（小红书英文标签几乎无搜索量）
        # 品牌专有名词豁免：iPhone/MacBook/ThinkPad/PS5 等本身就是搜索词，不是通用英文。
        _BRAND_TAG_WHITELIST = {
            # 3C 数码
            "ThinkPad", "iPhone", "iPad", "MacBook", "Mac", "Apple", "AppleWatch",
            "iMac", "iPod", "AirPods", "PlayStation", "PS5", "PS4", "Xbox",
            "Nintendo", "Switch", "SteamDeck", "NVIDIA", "RTX", "GTX", "AMD",
            "Intel", "Core", "Xiaomi", "Huawei", "HONOR", "OPPO", "vivo",
            "OnePlus", "realme", "iQOO", "Redmi", "Mi", "Galaxy", "Pixel",
            "Surface", "ROG", "Alienware", "ThinkBook", "Yoga", "IdeaPad",
            # 二次元/亚文化
            "ACG", "VOCALOID", "Vtuber",
            # 设计/创作工具
            "Procreate", "Figma", "Notion", "ChatGPT", "GPT", "Claude",
            "Midjourney", "StableDiffusion",
            # 车
            "BMW", "Mercedes", "Audi", "Porsche", "Tesla", "BYD", "NIO",
            "LiAuto", "XPeng", "Xiaopeng", "Rivian",
        }
        en_tags = [t for t in tags if re.fullmatch(r"[A-Za-z0-9]+", t) and t not in _BRAND_TAG_WHITELIST]
        if en_tags:
            warnings.append(
                f"[标签] 检测到英文标签 {en_tags}——小红书英文标签搜索量极低，建议换成中文"
            )
        # 检测是否含竞品平台名
        competitor = [t for t in tags if t in {"抖音", "淘宝", "天猫", "京东", "拼多多"}]
        if competitor:
            warnings.append(
                f"[合规] 标签含竞品平台名 {competitor}——会触发跨平台导流违规，请删除"
            )
    return warnings


# ============================================================
# 配图处理
# ============================================================

def process_images(images: list[str], output_path: str) -> list[str]:
    """将配图复制到输出目录同级的 preview_images/ 下，返回相对路径列表。

    - 文件不存在：跳过并告警
    - 复制失败：跳过并告警
    - 输出目录与图片父目录相同时不重复复制
    """
    if not images:
        return []

    output_dir = os.path.dirname(os.path.abspath(output_path))
    images_dir = os.path.join(output_dir, "preview_images")
    os.makedirs(images_dir, exist_ok=True)

    copied: list[str] = []
    for img in images:
        img = img.strip()
        if not img:
            continue
        if not os.path.isfile(img):
            print(f"[警告] 配图不存在，已跳过: {img}")
            continue
        dest_name = os.path.basename(img)
        dest_path = os.path.join(images_dir, dest_name)
        try:
            if os.path.abspath(img) != os.path.abspath(dest_path):
                shutil.copy2(img, dest_path)
            copied.append(f"preview_images/{dest_name}")
        except Exception as e:
            print(f"[警告] 复制失败 {img}: {e}")
    return copied


# ============================================================
# HTML 构建
# ============================================================

def build_tags_html(tags: list[str]) -> str:
    if not tags:
        return ""
    items = "".join(f'<span class="tag">#{html.escape(t)}</span>' for t in tags)
    return items


def build_content_html(content: str) -> str:
    """转义后：**xxx** → <strong>xxx</strong>，换行 → <br>。"""
    escaped = html.escape(content)
    result = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    result = result.replace("\n", "<br>")
    return result


def build_images_html(images: list[str]) -> str:
    """构建轮播 HTML。第一张 active，其余 hidden。"""
    if not images:
        return '''
            <div class="image-item active">
                <div class="carousel-placeholder">
                    <div class="carousel-icon">
                        <div class="carousel-icon-inner"></div>
                    </div>
                    <span class="carousel-text">封面图</span>
                </div>
            </div>
            <span class="image-counter">1 / 1</span>
            <div class="carousel-arrow left" style="display:none"></div>
            <div class="carousel-arrow right" style="display:none"></div>
        '''

    total = len(images)
    items = []
    for i, src in enumerate(images):
        active_class = "active" if i == 0 else ""
        items.append(
            f'<div class="image-item {active_class}" data-index="{i}">'
            f'<img src="{html.escape(src)}" alt="配图 {i+1}" loading="lazy">'
            f'</div>'
        )
    counter = f'<span class="image-counter">1 / {total}</span>'
    arrows = (
        f'<div class="carousel-arrow left" onclick="prevImage()"></div>'
        f'<div class="carousel-arrow right" onclick="nextImage()"></div>'
    ) if total > 1 else (
        '<div class="carousel-arrow left" style="display:none"></div>'
        '<div class="carousel-arrow right" style="display:none"></div>'
    )
    return "\n            ".join(items) + f"\n            {counter}\n            {arrows}"


def inject_carousel_js(template: str) -> str:
    """在 </body> 之前注入轮播 JS。"""
    js = '''
    <script>
    (function() {
        var items = document.querySelectorAll('.image-item');
        var counter = document.querySelector('.image-counter');
        var total = items.length;
        var current = 0;
        if (total <= 1) return;

        function show(idx) {
            items.forEach(function(el, i) {
                el.classList.toggle('active', i === idx);
            });
            if (counter) counter.textContent = (idx + 1) + ' / ' + total;
            current = idx;
        }

        window.nextImage = function() {
            show((current + 1) % total);
        };
        window.prevImage = function() {
            show((current - 1 + total) % total);
        };

        // 触摸滑动支持
        var carousel = document.querySelector('.image-carousel');
        if (carousel) {
            var startX = 0;
            carousel.addEventListener('touchstart', function(e) {
                startX = e.touches[0].clientX;
            }, { passive: true });
            carousel.addEventListener('touchend', function(e) {
                var endX = e.changedTouches[0].clientX;
                var diff = startX - endX;
                if (Math.abs(diff) > 40) {
                    if (diff > 0) window.nextImage();
                    else window.prevImage();
                }
            }, { passive: true });
        }
    })();
    </script>
    '''
    if "</body>" in template:
        return template.replace("</body>", js + "\n</body>")
    return template + js


# ============================================================
# 主流程
# ============================================================

def generate_preview(
    title: str,
    content: str,
    tags: list[str],
    author: str,
    output: str,
    images: list[str] | None = None,
    date: str | None = None,
) -> bool:
    template_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "assets",
        "preview-template.html",
    )
    if not os.path.exists(template_path):
        print(f"[错误] 模板不存在: {template_path}", file=sys.stderr)
        return False

    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    # 校验
    warnings = validate(title, content, tags)
    for w in warnings:
        print(w)

    # 违禁词扫描
    full_text = f"{title}\n{content}"
    hits = scan_banned_words(full_text)
    if hits:
        print("\n[合规] 违禁词命中（详见 references/compliance-checklist.md）：")
        for category, word, snippet in hits:
            print(f"  - [{category}] 「{word}」上下文: {snippet}")
    else:
        print("[合规] 未命中内置违禁词 ✓")

    # 处理配图
    image_paths = process_images(images or [], output)
    if images and not image_paths:
        print("[提示] 配图全部不可用，已用占位图替代")

    # 日期
    if not date:
        now = datetime.now()
        date = f"{now.month:02d}-{now.day:02d} 发布"
    date = html.escape(date)

    # 替换占位符
    tags_html = build_tags_html(tags)
    content_html = build_content_html(content)
    author_name = html.escape(author) if author else "小红书博主"
    note_title = html.escape(title) if title else "未命名笔记"
    images_html = build_images_html(image_paths)

    result = template.replace("{{IMAGES}}", images_html)
    result = result.replace("{{NOTE_TITLE}}", note_title)
    result = result.replace("{{NOTE_CONTENT}}", content_html)
    result = result.replace("{{NOTE_TAGS}}", tags_html)
    result = result.replace("{{AUTHOR_NAME}}", author_name)
    result = result.replace("12-30 发布", date)

    # 注入轮播 JS
    result = inject_carousel_js(result)

    # 写入
    output_dir = os.path.dirname(os.path.abspath(output))
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    with open(output, "w", encoding="utf-8") as f:
        f.write(result)

    print(f"\n[完成] 预览已生成: {os.path.abspath(output)}")
    if image_paths:
        print(f"       配图已复制: {os.path.join(output_dir, 'preview_images')}")
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="生成小红书笔记拟真预览页（含字数校验与违禁词扫描）"
    )
    parser.add_argument("--title", required=True, help="笔记标题（≤20 字）")
    parser.add_argument("--content", required=True, help="笔记正文（≤1000 字）")
    parser.add_argument(
        "--tags",
        default="",
        help="逗号分隔的话题标签（不带 #，如：职场成长,新人入职）",
    )
    parser.add_argument("--author", default="", help="作者昵称（默认「小红书博主」）")
    parser.add_argument(
        "--images",
        default="",
        help="逗号分隔的配图路径（自动复制到输出目录的 preview_images/）",
    )
    parser.add_argument(
        "--date",
        default="",
        help="发布日期，格式 MM-DD（如 09-05）；默认今天",
    )
    parser.add_argument(
        "--output",
        default="./note-preview.html",
        help="输出 HTML 路径（默认 ./note-preview.html）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    images = [i.strip() for i in args.images.split(",") if i.strip()]

    success = generate_preview(
        title=args.title,
        content=args.content,
        tags=tags,
        author=args.author,
        output=args.output,
        images=images,
        date=args.date,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
