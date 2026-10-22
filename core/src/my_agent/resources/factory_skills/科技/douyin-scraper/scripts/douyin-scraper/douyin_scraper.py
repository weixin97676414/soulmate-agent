# -*- coding: utf-8 -*-
















import csv
import logging
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager





OUTPUT_DIR = Path(__file__).parent / "reports"
OUTPUT_DIR.mkdir(exist_ok=True)

TODAY = datetime.now().strftime("%Y%m%d")
NOW_TIME = datetime.now().strftime("%H%M%S")
CSV_FILENAME = f"douyin_hot_videos_{TODAY}_{NOW_TIME}.csv"
REPORT_FILENAME = f"douyin_report_{TODAY}_{NOW_TIME}.txt"


TARGET_URLS = {
    "chanmama": "https://chanmama.com/awemeRank/hotAweme",
}


ECOMMERCE_URLS = {
    "chanmama_ecommerce": "https://www.chanmama.com/awemeRank/promotionAweme/",
}


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


PAGE_LOAD_TIMEOUT = 30
ELEMENT_WAIT_TIMEOUT = 20


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)






def create_driver() -> webdriver.Chrome:

    options = Options()
    
    options.add_argument("--headless=new")
    
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(f"--user-agent={HEADERS['User-Agent']}")
    
    
    

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
            window.chrome = {runtime: {}};
        """
    })

    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    log.info("Chrome WebDriver 初始化完成")
    return driver







def fetch_page_selenium(driver: webdriver.Chrome, url: str) -> str:




    log.info(f"正在打开: {url}")
    try:
        driver.get(url)
        
        WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table, .rank-list, .rank-item, "
                                            ".video-card, .hot-item, [class*='rank'], "
                                            "[class*='video'], [class*='item']"))
        )
        
        time.sleep(random.uniform(2, 3))

        
        scroll_attempts = 3
        prev_html_len = 0
        for i in range(scroll_attempts):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(random.uniform(2, 3))
            current_len = len(driver.page_source)
            log.info(f"  滚动第{i+1}次，HTML长度: {current_len}")
            if current_len == prev_html_len:
                log.info(f"  页面不再增长，停止滚动")
                break
            prev_html_len = current_len

        
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)

        page_source = driver.page_source
        log.info(f"页面加载成功，HTML 长度: {len(page_source)} 字符")
        return page_source
    except Exception as e:
        log.warning(f"Selenium 加载超时或异常: {e}，尝试直接获取当前页面源码...")
        try:
            return driver.page_source
        except Exception:
            raise RuntimeError(f"无法获取页面 {url} 的内容: {e}")


def fetch_page_requests(url: str) -> str:




    log.info(f"[requests备用] 正在请求: {url}")
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.encoding = resp.apparent_encoding or "utf-8"
    log.info(f"[requests备用] 状态码: {resp.status_code}, 内容长度: {len(resp.text)}")
    return resp.text







def parse_chanmama(html: str) -> list[dict]:




    soup = BeautifulSoup(html, "lxml")
    results = []

    
    
    douyin_raw_links = _extract_douyin_share_links(soup)
    log.info(f"发现 {len(douyin_raw_links)} 条抖音原始分享链接")

    
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 3:  
            continue
        for idx, row in enumerate(rows[1:]):  
            cells = row.find_all(["td", "th"])
            if len(cells) >= 3:
                record = _extract_from_cells(cells)
                
                if idx < len(douyin_raw_links):
                    record["video_url"] = convert_ies_to_douyin(douyin_raw_links[idx])
                elif not record.get("video_url"):
                    record["video_url"] = ""
                results.append(record)

    if results:
        log.info(f"[策略1-表格] 提取到 {len(results)} 条记录（含抖音直链）")
        matched_links = sum(1 for r in results if r.get("video_url", "").startswith("https://www.douyin.com"))
        log.info(f"  其中 {matched_links}/{len(results)} 条有抖音原地址")
        return _deduplicate_and_rank(results)

    
    selectors = [
        ".rank-item", ".video-card", ".hot-item", "[class*='RankItem']",
        "[class*='VideoCard']", "[class*='HotItem']",
        ".ranking-list li", ".video-list li", ".list-item",
        "[class*='rankItem']", "[class*='rank-item']",
        "[data-index]", "[class*='aweme']",
    ]
    for sel in selectors:
        items = soup.select(sel)
        if items and len(items) >= 3:
            for item in items:
                data = _extract_from_card(item)
                if data and data.get("title"):
                    results.append(data)
            if results:
                log.info(f"[策略2-列表:{sel}] 提取到 {len(results)} 条记录")
                return _deduplicate_and_rank(results)

    
    log.info("[策略3-宽泛匹配] 尝试从全页文本中提取结构化数据...")
    results = _fallback_extract(soup)
    if results:
        log.info(f"[策略3-宽泛] 提取到 {len(results)} 条记录")
        return _deduplicate_and_rank(results)

    log.warning("所有解析策略均未提取到有效数据")
    return []


def _extract_from_cells(cells) -> dict:

    texts = [cell.get_text(strip=True) for cell in cells]

    
    all_links = []
    for cell in cells:
        for a in cell.find_all("a", href=True):
            href = a["href"]
            if href.startswith("/") and not href.startswith("//"):
                href = "https://chanmama.com" + href
            if "douyin.com" in href or "chanmama.com" in href:
                all_links.append(href)
    video_url = all_links[0] if all_links else ""

    
    raw_author = texts[2] if len(texts) > 2 else ""
    author = clean_author_name(raw_author)

    return {
        "raw_rank": _safe_int(texts[0]) if texts else 0,
        "title": clean_title(texts[1] if len(texts) > 1 else ""),
        "author": author,
        "likes": _parse_number(texts[3] if len(texts) > 3 else ""),
        "views": _parse_number(texts[4] if len(texts) > 4 else ""),
        "comments": _parse_number(texts[5] if len(texts) > 5 else ""),
        "shares": _parse_number(texts[6] if len(texts) > 6 else ""),
        "category": "",
        "video_url": video_url,
        "comment": "",
    }


def clean_author_name(raw: str) -> str:





    if not raw:
        return ""
    
    name = re.sub(r'\s*\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}\s*$', '', raw)
    
    name = re.sub(r'\s*粉丝[\d,]+\s*', '', name)
    
    name = re.sub(r'\s+\d{2}:\d{2}\s*$', '', name).strip()
    
    return name if len(name) >= 2 else raw.strip()


def clean_title(raw: str) -> str:

    if not raw:
        return ""
    
    title = " ".join(raw.split())
    return title.strip()


def _extract_douyin_share_links(soup: BeautifulSoup) -> list[str]:






    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        
        if "iesdouyin.com/share/" in href and ("/video/" in href or "/note/" in href):
            links.append(href)
    return links


def convert_ies_to_douyin(ies_url: str) -> str:









    if not ies_url or "iesdouyin.com/share/" not in ies_url:
        return ies_url

    
    m_video = re.search(r'/share/video/(\d+)', ies_url)
    m_note = re.search(r'/share/note/(\d+)', ies_url)

    if m_video:
        video_id = m_video.group(1)
        return f"https://www.douyin.com/video/{video_id}"
    elif m_note:
        note_id = m_note.group(1)
        return f"https://www.douyin.com/note/{note_id}"

    return ies_url


def _extract_from_card(card) -> dict:

    
    title_el = card.select_one(".title, .name, .video-title, h3, h4, [class*='title'], [class*='name']")
    title = title_el.get_text(strip=True) if title_el else ""

    
    author_el = card.select_one(".author, .creator, .nickname, .user-name, [class*='author'], [class*='user']")
    author = author_el.get_text(strip=True) if author_el else ""

    
    likes_el = card.select_one(".like-count, .likes, .count, [class*='like'], [class*='heart'], [class*='count']")
    likes_str = likes_el.get_text(strip=True) if likes_el else ""
    likes = _parse_number(likes_str)

    
    views_el = card.select_one(".view-count, .play-count, .views, [class*='view'], [class*='play']")
    views_str = views_el.get_text(strip=True) if views_el else ""
    views = _parse_number(views_str)

    
    link_el = card.select_one("a[href*='/video/'], a[href*='/note/'], a[href*='douyin.com']")
    video_url = link_el.get("href", "") if link_el else ""

    
    full_text = card.get_text(separator="|", strip=True)

    return {
        "raw_rank": 0,
        "title": title,
        "author": author,
        "likes": likes,
        "views": views,
        "comments": 0,
        "shares": 0,
        "category": "",
        "video_url": video_url,
        "comment": "",
        "_full_text": full_text[:200],  
    }


def _fallback_extract(soup: BeautifulSoup) -> list[dict]:




    text = soup.get_text(separator="\n", strip=True)
    results = []

    
    patterns = [
        
        r"^(\d{1,2})[.\s、\t]+(.{2,50})\t?(.{2,20})\t?([\d.]+[万kwb]?)\t?([\d.]+[万kw]?)",
        r"(\d{1,2})\s+(.+?)\s+(\d[\d.,]*[万w]?)\s+(.+?)\s+(\d[\d.,]*[万w]?)",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.MULTILINE):
            groups = m.groups()
            results.append({
                "raw_rank": _safe_int(groups[0]),
                "title": groups[1].strip(),
                "author": groups[2].strip() if len(groups) > 2 else "",
                "likes": _parse_number(groups[3]) if len(groups) > 3 else 0,
                "views": _parse_number(groups[4]) if len(groups) > 4 else 0,
                "comments": 0,
                "shares": 0,
                "category": "",
                "video_url": "",
                "comment": "",
            })
        if results:
            break

    return results







def _parse_number(s: str) -> int:




    if not s:
        return 0
    s = s.strip().replace(",", "").replace(" ", "")
    try:
        if "亿" in s:
            return int(float(s.replace("亿", "")) * 100_000_000)
        elif "万" in s or "w" in s.lower():
            return int(float(s.replace("万", "").replace("w", "").replace("W", "")) * 10_000)
        elif "k" in s.lower():
            return int(float(s.lower().replace("k", "")) * 1_000)
        elif "b" in s.lower():
            return int(float(s.lower().replace("b", "")) * 1_000_000_000)
        else:
            return int(float(s))
    except (ValueError, TypeError):
        return 0


def _safe_int(s) -> int:

    try:
        return int(str(s).strip())
    except (ValueError, TypeError):
        return 0


def _deduplicate_and_rank(records: list[dict]) -> list[dict]:

    seen = set()
    unique = []
    for r in records:
        key = (r.get("title", ""), r.get("author", ""))
        if key != ("", "") and key not in seen:
            seen.add(key)
            unique.append(r)

    
    unique.sort(key=lambda x: x.get("likes", 0), reverse=True)

    
    for i, r in enumerate(unique, 1):
        r["rank"] = i

    return unique


def categorize_video(title: str, comment: str = "") -> str:

    keywords = {
        "剧情": ["剧情", "短剧", "演绎", "段子", "搞笑段子"],
        "搞笑": ["搞笑", "沙雕", "整蛊", "爆笑", "笑死", "哈哈哈哈", "梗"],
        "体育": ["篮球", "足球", "NBA", "CBA", "世界杯", "奥运", "比赛", "运动", "健身", "梅西", "C罗"],
        "音乐": ["唱歌", "翻唱", "音乐", "歌曲", "演奏", "吉他", "钢琴", "DJ", "说唱", "rap"],
        "游戏": ["游戏", "王者", "和平精英", "原神", "LOL", "lol", "手游", "通关", "排位"],
        "美食": ["美食", "做饭", "烹饪", "吃播", "料理", "零食", "蛋糕", "烧烤", "火锅"],
        "情感": ["情感", "恋爱", "分手", "结婚", "前任", "表白", "催泪", "感动", "治愈"],
        "社会热点": ["新闻", "事件", "热点", "爆料", "官方", "通报", "社会", "民生"],
        "二次元": ["动漫", "cos", "Cosplay", "二次元", "番剧", "漫画", "国漫", "日漫"],
        "创意": ["特效", "剪辑", "AI", "动画", "手工", "DIY", "黑科技"],
        "美妆时尚": ["化妆", "护肤", "穿搭", "变装", "时尚", "口红", "发型", "美甲"],
        "汽车": ["汽车", "开车", "跑车", "特斯拉", "比亚迪", "驾照", "车展"],
        "萌宠": ["猫", "狗", "宠物", "萌宠", "猫咪", "狗狗", "动物"],
        "教育科普": ["科普", "知识", "学习", "考试", "历史", "地理", "科学"],
        "舞蹈": ["跳舞", "舞蹈", "街舞", "古典舞", "韩舞", "编舞"],
        "旅行": ["旅游", "旅行", "景点", "打卡", "民宿", "风景"],
    }
    combined = f"{title} {comment}".lower()
    for category, kws in keywords.items():
        for kw in kws:
            if kw.lower() in combined:
                return category
    return "其他"


def _categorize_ecommerce(title: str) -> str:

    keywords = {
        "美妆护肤": ["口红", "粉底", "面膜", "精华", "防晒", "卸妆", "眉笔", "眼影", "化妆", "护肤品",
                      "雅诗兰黛", "兰蔻", "SK-II", "欧莱雅", "珀莱雅", "薇诺娜", "韩束"],
        "服装鞋包": ["连衣裙", "T恤", "卫衣", "外套", "牛仔裤", "短裤", "裙子", "衬衫",
                     "鞋子", "包包", "运动鞋", "凉鞋", "穿搭", "女装", "男装", "童装"],
        "食品饮料": ["零食", "坚果", "奶茶", "咖啡", "螺蛳粉", "方便面", "巧克力", "饼干",
                     "饮料", "水果", "特产", "代餐", "蛋白棒"],
        "家居日用": ["纸巾", "洗衣液", "收纳", "垃圾袋", "清洁剂", "厨房用品", "床品", "窗帘",
                     "四件套", "枕头", "被子", "台灯", "插座"],
        "数码家电": ["手机壳", "充电宝", "数据线", "耳机", "蓝牙音箱", "手机支架", "平板",
                     "键盘", "鼠标", "显示器", "小家电", "电饭煲", "空气炸锅"],
        "母婴亲子": ["尿不湿", "奶粉", "玩具", "童装", "辅食", "婴儿车", "安全座椅", "绘本"],
        "运动户外": ["瑜伽垫", "跑步鞋", "哑铃", "帐篷", "登山杖", "泳衣", "骑行", "健身器材"],
    }
    for category, kws in keywords.items():
        for kw in kws:
            if kw.lower() in title:
                return category
    return "其他"







def save_to_csv(records: list[dict], filepath: Path) -> Path:




    fieldnames = [
        "排名", "视频标题", "达人", "点赞数", "转发数", "评论数",
        "播放量", "赛道分类", "视频链接", "一句话点评",
    ]

    
    for r in records:
        r["category"] = categorize_video(r.get("title", ""), r.get("comment", ""))

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in records:
            writer.writerow({
                "排名": r.get("rank", ""),
                "视频标题": r.get("title", ""),
                "达人": r.get("author", ""),
                "点赞数": _format_num(r.get("likes", 0)),
                "转发数": _format_num(r.get("shares", 0)),
                "评论数": _format_num(r.get("comments", 0)),
                "播放量": _format_num(r.get("views", 0)),
                "赛道分类": r.get("category", ""),
                "视频链接": r.get("video_url", ""),
                "一句话点评": r.get("comment", ""),
            })

    log.info(f"CSV 已保存: {filepath} ({len(records)} 条记录)")
    return filepath


def _format_num(n) -> str:

    if not n or n == 0:
        return ""
    n = int(n)
    if n >= 100_000_000:
        return f"{n / 100_000_000:.1f}亿"
    elif n >= 10_000:
        return f"{n / 10_000:.1f}万"
    return str(n)







HOT_SEARCH_URLS = [
    
    "https://top.baidu.com/board?tab=realtime",
]


def fetch_hot_search_top10(driver: webdriver.Chrome = None) -> list[dict]:









    results = []

    
    try:
        results = _fetch_baidu_realtime()
        if len(results) >= 5:
            
            results = [r for r in results if len(r["title"]) >= 4 and not any(
                kw in r["title"] for kw in ["登录", "注册", "夜间模式", "关于我们", "App下载", "使用指南", "赞助商", "API开放平台"]
            )]
            log.info(f"[热搜-百度] 成功获取 {len(results)} 条热搜")
            return results[:10]
    except Exception as e:
        log.warning(f"[热搜-百度] 失败: {e}")

    
    if driver:
        try:
            results = _fetch_hot_selenium(driver)
            if results:
                log.info(f"[热搜-selenium] 成功获取 {len(results)} 条")
                return results[:10]
        except Exception as e:
            log.warning(f"[热搜-selenium] 失败: {e}")

    return []


def _fetch_tophub_douyin() -> list[dict]:

    url = "https://tophub.today/n/KqndgxeLl9"
    headers = {
        **HEADERS,
        "Referer": "https://tophub.today/",
        "Accept": "text/html,application/xhtml+xml",
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "lxml")

    results = []
    
    items = soup.select(".cc-cd .item, tr.item, .table tbody tr, [class*='list'] [class*='item']")
    if not items:
        
        for row in soup.select("td, .lc, .rc"):
            text = row.get_text(strip=True)
            if re.search(r'[\d.]+[万亿wW]', text):
                parent = row.parent
                if parent and parent not in [i for i in items]:
                    items.append(parent)

    for idx, item in enumerate(items[:15], 1):
        if idx > 10:
            break
        
        title_el = item.select_one(".al a, a.t, h2 a, .title a, td a, [class*='title'] a")
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            title = item.get_text(strip=True).split("\n")[0][:50]

        
        hot_text = item.get_text(strip=True)
        m_hot = re.search(r'([\d,.]+)(?:万|亿)?', hot_text)
        hot_val = m_hot.group(0) if m_hot else ""

        
        href = ""
        if title_el and title_el.has_attr("href"):
            href = title_el["href"]
            if href.startswith("//"):
                href = "https:" + href
        else:
            
            href = f"https://www.douyin.com/search/{requests.utils.quote(title)}"

        if title and len(title) >= 2:
            results.append({
                "rank": idx,
                "title": title,
                "hot_value": hot_val,
                "url": href,
            })

    return results


def _fetch_hot_selenium(driver: webdriver.Chrome) -> list[dict]:

    for url in HOT_SEARCH_URLS:
        try:
            html = fetch_page_selenium(driver, url)
            soup = BeautifulSoup(html, "lxml")

            results = []
            
            selectors = [
                ".cc-cd .item", "tr.item", ".rank-item",
                "[class*='HotItem']", "[class*='hot-item']",
                "tbody tr", "[class*='list-item']",
            ]
            for sel in selectors:
                items = soup.select(sel)
                if len(items) < 3:
                    continue
                for idx, item in enumerate(items[:12], 1):
                    if idx > 10:
                        break
                    link = item.select_one("a[href]")
                    title = link.get_text(strip=True) if link else item.get_text(strip=True)[:50]
                    full_text = item.get_text(strip=True)
                    m = re.search(r'([\d,.]+[万亿wk]?)', full_text)

                    if title and len(title) >= 2:
                        href = link.get("href", "") if link else ""
                        if not href or href.startswith("/"):
                            href = f"https://www.douyin.com/search/{requests.utils.quote(title)}"
                        results.append({
                            "rank": idx,
                            "title": title,
                            "hot_value": m.group(1) if m else "",
                            "url": href,
                        })
                if results:
                    break

            if results:
                return results
        except Exception:
            continue
    return []


def _fetch_baidu_realtime() -> list[dict]:

    url = "https://top.baidu.com/board?tab=realtime"
    headers = {**HEADERS}
    resp = requests.get(url, headers=headers, timeout=10)
    html = resp.text
    import urllib.parse

    results = []

    
    
    
    
    

    words = re.findall(r'"word"\s*:\s*"([^"]+)"', html)
    hot_scores = re.findall(r'"hotScore"\s*:\s*"(\d+)"', html)

    log.info(f"[百度热搜原始] word={len(words)}, hotScore={len(hot_scores)}")

    seen_titles = set()
    for i, title in enumerate(words):
        if not title or len(title) < 4:
            continue
        if title in seen_titles:
            continue
        
        skip_kw = ["登录", "注册", "夜间模式", "关于我们", "App下载", "使用指南",
                    "赞助商广告", "API开放平台", "首页", "更多", "类型", "全部类型"]
        if any(kw in title for kw in skip_kw):
            continue

        seen_titles.add(title)
        hot_score = hot_scores[i] if i < len(hot_scores) else ""
        try:
            hot_str = f"{int(hot_score) / 10000:.1f}万" if hot_score else ""
        except (ValueError, TypeError):
            hot_str = ""

        results.append({
            "rank": len(results) + 1,
            "title": title,
            "hot_value": hot_str,
            "url": f"https://www.douyin.com/search/{urllib.parse.quote(title)}",
        })

    log.info(f"[百度热搜] 有效数据 {len(results)} 条")
    return results[:12]







RANK_EMOJIS = ["\U0001F3C6", "\U0001F948", "\U0001F949"]  


def generate_trend_insights(video_records: list[dict], hot_search_records: list[dict],
                            ecommerce_records: list[dict] = None) -> str:









    insights = []

    
    category_count = {}
    for r in video_records:
        cat = categorize_video(r.get("title", ""))
        category_count[cat] = category_count.get(cat, 0) + 1

    if category_count:
        sorted_cats = sorted(category_count.items(), key=lambda x: x[1], reverse=True)
        cat_line = "、".join([f"{cat}({cnt}条)" for cat, cnt in sorted_cats[:5]])
        insights.append(f"赛道分布：{cat_line}")

    
    if hot_search_records:
        topics = [r["title"] for r in hot_search_records]
        topic_categories = _classify_topics(topics)
        lines = [f"{label}" for label in topic_categories]
        insights.append("热搜特征：" + "；".join(lines))

    
    super_viral = [r for r in video_records if r.get("likes", 0) >= 300_000]
    if super_viral:
        titles = [r["title"][:15] for r in super_viral[:3]]
        insight = f"超级爆款：{', '.join(titles)} 等{len(super_viral)}条视频突破30万点赞"
        insights.append(insight)

    
    if ecommerce_records and len(ecommerce_records) > 0:
        
        ec_categories = {}
        for r in ecommerce_records:
            ec_cat = _categorize_ecommerce(r.get("title", ""))
            ec_categories[ec_cat] = ec_categories.get(ec_cat, 0) + 1
        if ec_categories:
            ec_sorted = sorted(ec_categories.items(), key=lambda x: x[1], reverse=True)
            ec_line = "、".join([f"{cat}({cnt}条)" for cat, cnt in ec_sorted[:5]])
            insights.append(f"电商热品：{ec_line}")
        
        ec_top = ecommerce_records[0]
        if ec_top.get("likes", 0) >= 100_000:
            insights.append(f"带货王：{ec_top['title'][:20]}(@{ec_top.get('author','')}) 以 {_format_num(ec_top['likes'])} 点赞领跑")

    
    all_titles = [r.get("title", "") for r in video_records] + [r.get("title", "") for r in hot_search_records]
    combined = " ".join(all_titles)

    event_keywords = {
        "节日效应": ["520", "情人节", "七夕", "圣诞", "元旦", "春节", "中秋", "国庆", "双11", "618"],
        "体育赛事": ["NBA", "CBA", "世界杯", "奥运", "欧冠", "英超", "科比", "梅西", "C罗", "奥沙利文", "网球", "F1"],
        "影视娱乐": ["电影", "剧集", "综艺", "首映", "上映", "票房", "明星"],
        "教育考试": ["高考", "中考", "期末", "开学", "毕业", "考研", "试卷", "考试"],
        "社会时政": ["通报", "官方", "发布会", "政策", "法规", "调查"],
        "天气气候": ["高温", "暴雨", "台风", "降温", "寒潮", "地震"],
        "科技热点": ["AI", "苹果", "华为", "小米", "特斯拉", "发布", "新品"],
    }
    detected_events = []
    for event_type, kws in event_keywords.items():
        for kw in kws:
            if kw.lower() in combined.lower():
                detected_events.append(event_type)
                break

    if detected_events:
        unique_events = list(dict.fromkeys(detected_events))  
        insights.append(f"今日节点：{'、'.join(unique_events)} 相关内容占据主导")

    
    dark_horse_candidates = [
        r for r in video_records
        if r.get("likes", 0) >= 50_000 and categorize_video(r.get("title", "")) in ("萌宠", "创意", "教育科普")
    ]
    if dark_horse_candidates:
        names = [(r["title"][:12], r.get("author", "")) for r in dark_horse_candidates[:2]]
        insights.append(f"黑马观察：{names[0][0]}(@{names[0][1]})等冷门赛道内容异军突起")

    
    if not insights:
        insights.append("整体趋势稳定，各赛道内容百花齐放")

    return "\n".join(insights)


def _classify_topics(topic_titles: list[str]) -> list[str]:

    categories = {
        "时政类": ["政府", "政策", "官员", "通报", "调查", "会议", "法规", "外交", "军事"],
        "社会民生": ["事故", "案件", "安全", "交通", "医疗", "房价", "就业", "工资", "社保"],
        "娱乐明星": ["明星", "演员", "歌手", "偶像", "综艺", "剧", "电影", "演唱会", "绯闻"],
        "体育竞技": ["球赛", "NBA", "足球", "篮球", "奥运", "冠军", "比赛", "训练"],
        "财经商业": ["股市", "股价", "公司", "上市", "融资", "财报", "经济", "银行"],
        "科技数码": ["手机", "芯片", "AI", "汽车", "电脑", "App", "互联网", "发布"],
        "生活消费": ["美食", "旅游", "购物", "优惠", "打折", "穿搭", "美妆"],
        "节气节日": ["春节", "清明", "五一", "端午", "中秋", "国庆", "节气", "假期"],
    }
    detected = set()
    for topic in topic_titles:
        for cat, kws in categories.items():
            for kw in kws:
                if kw in topic:
                    detected.add(cat)
                    break
    return sorted(detected) if detected else ["综合热点多元分布"]







MEDALS = ["\u1f3c6", "\u1f948", "\u1f949"]  


def save_report(video_records: list[dict], hot_search_records: list[dict],
                ecommerce_records: list[dict], filepath: Path) -> Path:








    now_str = datetime.now().strftime("%Y年%m月%d日 %H:%M")
    lines = []

    
    lines.append("=" * 60)
    lines.append("抖音热门视频 TOP 10")
    lines.append("=" * 60)
    lines.append("")

    for i, r in enumerate(video_records[:10], 1):
        medal = MEDALS[i - 1] if i <= 3 else ""
        rank_label = f"Top {i}"
        likes_str = _format_num(r.get("likes", 0)) or "N/A"
        author = r.get("author", "未知")
        title = r.get("title", "").replace("\n", " ")
        url = r.get("video_url", "")

        lines.append(f"{medal} {rank_label} - {title}")
        lines.append(f"达人：{author}")
        lines.append(f"热度：{likes_str}")
        if url:
            lines.append(f"详情链接：{url}")
        lines.append("")

    
    lines.append("")
    lines.append("=" * 60)
    lines.append("抖音热榜 TOP 10")
    lines.append("=" * 60)
    lines.append("")

    if hot_search_records:
        for i, item in enumerate(hot_search_records[:10], 1):
            medal = MEDALS[i - 1] if i <= 3 else ""
            rank_label = f"Top {i}"
            title = item.get("title", "")
            hot_val = item.get("hot_value", "N/A")
            url = item.get("url", "")

            lines.append(f"{medal} {rank_label} - {title}")
            lines.append(f"热度：{hot_val}")
            lines.append(f"详情链接：{url}")
            lines.append("")
    else:
        lines.append("（本次未获取到热搜数据）")
        lines.append("")

    
    lines.append("")
    lines.append("=" * 60)
    lines.append("电商带货热榜视频 TOP 10")
    lines.append("=" * 60)
    lines.append("")

    if ecommerce_records:
        for i, r in enumerate(ecommerce_records[:10], 1):
            medal = MEDALS[i - 1] if i <= 3 else ""
            rank_label = f"Top {i}"
            likes_str = _format_num(r.get("likes", 0)) or "N/A"
            author = r.get("author", "未知")
            title = r.get("title", "").replace("\n", " ")
            url = r.get("video_url", "")

            lines.append(f"{medal} {rank_label} - {title}")
            lines.append(f"达人：{author}")
            lines.append(f"热度：{likes_str}")
            if url:
                lines.append(f"详情链接：{url}")
            lines.append("")
    else:
        lines.append("（本次未获取到电商带货数据）")
        lines.append("")

    
    lines.append("")
    lines.append("=" * 60)
    lines.append("趋势洞察")
    lines.append("=" * 60)
    lines.append("")

    trend_text = generate_trend_insights(video_records, hot_search_records, ecommerce_records)
    lines.append(trend_text)
    lines.append("")

    
    lines.append(f"数据更新时间：{now_str}")
    lines.append("")

    
    report_text = "\n".join(lines)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report_text)

    log.info(f"报告已保存: {filepath}")
    return filepath







def main():

    start_time = time.time()
    log.info("=" * 50)
    log.info("抖音热门数据爬虫 v2 启动")
    log.info("=" * 50)

    driver = None
    all_video_records = []
    hot_search_records = []
    ecommerce_records = []

    try:
        
        driver = create_driver()

        
        for source_name, url in TARGET_URLS.items():
            log.info(f"\n--- 数据源: {source_name} ---")
            try:
                html = fetch_page_selenium(driver, url)
                records = parse_chanmama(html)
                if records:
                    all_video_records.extend(records)
                    log.info(f"✅ {source_name}: 成功提取 {len(records)} 条")
                else:
                    log.warning(f"{source_name}: 未提取到有效数据，尝试 requests 备用...")
                    html_req = fetch_page_requests(url)
                    records = parse_chanmama(html_req)
                    if records:
                        all_video_records.extend(records)
                        log.info(f"✅ {source_name}[requests备用]: 成功提取 {len(records)} 条")
                    else:
                        log.error(f"❌ {source_name}: 所有方式均失败")
            except Exception as e:
                log.error(f"❌ {source_name} 异常: {e}", exc_info=True)

        
        log.info(f"\n--- 数据源: 电商带货热榜 ---")
        for source_name, url in ECOMMERCE_URLS.items():
            try:
                html_ec = fetch_page_selenium(driver, url)
                ec_records = parse_chanmama(html_ec)  
                if ec_records:
                    ecommerce_records = _deduplicate_and_rank(ec_records)
                    log.info(f"✅ {source_name}: 成功提取 {len(ecommerce_records)} 条电商带货视频")
                else:
                    log.warning(f"{source_name}: 未提取到有效数据")
            except Exception as e:
                log.warning(f"⚠️ 电商榜单获取失败: {e}")

        
        log.info(f"\n--- 数据源: 热搜榜 ---")
        try:
            hot_search_records = fetch_hot_search_top10(driver)
            log.info(f"✅ 热搜榜: 获取到 {len(hot_search_records)} 条")
        except Exception as e:
            log.warning(f"⚠️ 热搜榜获取失败: {e}")

        
        if all_video_records:
            all_video_records = _deduplicate_and_rank(all_video_records)
            log.info(f"\n总计视频去重后: {len(all_video_records)} 条")

        
        csv_path = OUTPUT_DIR / CSV_FILENAME
        save_to_csv(all_video_records, csv_path)

        
        if ecommerce_records:
            ec_csv_filename = f"douyin_ecommerce_{TODAY}_{NOW_TIME}.csv"
            ec_csv_path = OUTPUT_DIR / ec_csv_filename
            
            for r in ecommerce_records:
                r["category"] = _categorize_ecommerce(r.get("title", ""))
            save_to_csv(ecommerce_records, ec_csv_path)

        
        report_path = OUTPUT_DIR / REPORT_FILENAME
        save_report(all_video_records, hot_search_records, ecommerce_records, report_path)

        
        print(f"\n{'='*60}")
        print(f"📊 抓取完成！报告预览：")
        print(f"{'='*60}")
        
        with open(report_path, "r", encoding="utf-8") as f:
            print(f.read())

        print(f"📁 报告文件: {report_path}")
        print(f"📁 CSV文件: {csv_path}")

    except Exception as e:
        log.critical(f"爬虫运行致命错误: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if driver:
            driver.quit()
            log.info("浏览器已关闭")

    elapsed = time.time() - start_time
    log.info(f"总耗时: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
