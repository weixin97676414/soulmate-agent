# -*- coding: utf-8 -*-
"""报告渲染：把 analysis.json 变成可交付的 Markdown / HTML 报告。

    python xhs_report.py --analysis <dir>/analysis.json --dataset <dir>/dataset.json \
        [--narrative 叙事.md] --format md|html|both --out <dir>

产物：
    report.md    数据完整 + 需要 Agent 补写的段落用 ✍️ 标记
    report.html  自包含单页报告（内联 SVG 图表，无外网依赖）

叙事段落（商业定位诊断 / 算法推演 / 爆款拆解 / SOP）由 Agent 撰写后写入 narrative.md，
再执行一次本脚本即可合成完整报告。
"""
from __future__ import annotations

import argparse
import html
import re
import time
from pathlib import Path

from xhs_common import fmt_num, log, read_json, write_json

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "report_template.html"

TODO = ("<div class='todo'>✍️ 本节需结合上面的数据与素材清单中的可用素材（封面、关键帧拼版、视频原片）由分析者补写。"
        "补写时按叙事稿模板的「素材使用纪律」执行；"
        "把填好的叙事稿交给本脚本（指定叙事稿参数）即可自动合成本节。</div>")


# --------------------------------------------------------------------------- #
# Markdown 迷你渲染器
# --------------------------------------------------------------------------- #
def md_to_html(text: str) -> str:
    if not text:
        return ""
    lines = text.split("\n")
    out, in_list, in_table, in_code = [], False, False, False
    for raw in lines:
        line = raw.rstrip()
        if line.strip().startswith("```"):
            if in_code:
                out.append("</code></pre>")
                in_code = False
            else:
                out.append("<pre><code>")
                in_code = True
            continue
        if in_code:
            out.append(html.escape(raw))
            continue
        if in_list and not re.match(r"^\s*[-*]\s+", line):
            out.append("</ul>")
            in_list = False
        if in_table and not line.strip().startswith("|"):
            out.append("</tbody></table>")
            in_table = False

        if re.match(r"^\s*[-*]\s+", line):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append("<li>" + inline(re.sub(r"^\s*[-*]\s+", "", line)) + "</li>")
            continue
        if line.strip().startswith("|") and line.strip().endswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not in_table:
                out.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in cells) + "</tr></thead><tbody>")
                in_table = True
            elif set("".join(cells)) <= set("-: "):
                continue
            else:
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells) + "</tr>")
            continue
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            level = min(6, len(m.group(1)) + 2)
            out.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
            continue
        if line.strip() == "":
            continue
        if line.strip().startswith(">"):
            out.append(f"<blockquote>{inline(line.lstrip('> '))}</blockquote>")
            continue
        out.append(f"<p>{inline(line)}</p>")
    if in_list:
        out.append("</ul>")
    if in_table:
        out.append("</tbody></table>")
    if in_code:
        out.append("</code></pre>")
    return "\n".join(out)


def inline(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


# --------------------------------------------------------------------------- #
# SVG 图表
# --------------------------------------------------------------------------- #
def svg_bars(values: list[float], labels: list[str], width: int = 1100, height: int = 240,
             median: float = 0.0) -> str:
    if not values:
        return "<p>无数据</p>"
    pad_l, pad_b, pad_t = 46, 34, 14
    n = len(values)
    slot = (width - pad_l - 12) / max(n, 1)
    bar_w = max(4, min(26, slot * 0.62))
    peak = max(values) or 1
    scale = (height - pad_b - pad_t) / peak

    parts = [f'<svg class="chart" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">']
    parts.append(f'<line x1="{pad_l}" y1="{height - pad_b}" x2="{width - 6}" y2="{height - pad_b}" '
                 f'stroke="var(--line)" stroke-width="1"/>')
    for frac in (0.25, 0.5, 0.75, 1.0):
        y = height - pad_b - (height - pad_b - pad_t) * frac
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width - 6}" y2="{y:.1f}" '
                     f'stroke="var(--line)" stroke-width="1" stroke-dasharray="3 4" opacity="0.5"/>')
        parts.append(f'<text x="{pad_l - 8}" y="{y + 4:.1f}" fill="var(--muted)" font-size="10" '
                     f'text-anchor="end">{fmt_num(int(peak * frac))}</text>')
    for i, v in enumerate(values):
        x = pad_l + slot * i + (slot - bar_w) / 2
        h = max(2, v * scale)
        y = height - pad_b - h
        color = "var(--accent)" if median and v >= median * 3 else "var(--accent-2)"
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" '
                     f'rx="3" fill="{color}" opacity="0.9"><title>{html.escape(labels[i])} · '
                     f'点赞 {fmt_num(int(v))}</title></rect>')
    if median:
        y = height - pad_b - median * scale
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width - 6}" y2="{y:.1f}" '
                     f'stroke="var(--ok)" stroke-width="1.5" stroke-dasharray="6 3"/>')
        parts.append(f'<text x="{width - 10}" y="{y - 5:.1f}" fill="var(--ok)" font-size="10" '
                     f'text-anchor="end">中位数 {fmt_num(int(median))}</text>')
    step = max(1, n // 12)
    for i in range(0, n, step):
        x = pad_l + slot * i + slot / 2
        parts.append(f'<text x="{x:.1f}" y="{height - pad_b + 16}" fill="var(--muted)" '
                     f'font-size="10" text-anchor="middle">{(labels[i] or "")[:5]}</text>')
    parts.append("</svg>")
    return "".join(parts)


def svg_ratio_bar(items: list[tuple[str, float]], width: int = 1100, height: int = 150) -> str:
    total = sum(v for _, v in items) or 1
    parts = [f'<svg class="chart" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">']
    colors = ["var(--accent)", "var(--accent-2)", "var(--ok)", "#5b8def"]
    x = 0.0
    for i, (name, value) in enumerate(items):
        w = width * value / total
        parts.append(f'<rect x="{x:.1f}" y="30" width="{w:.1f}" height="34" fill="{colors[i % 4]}" opacity="0.9"/>')
        if w > 60:
            parts.append(f'<text x="{x + w / 2:.1f}" y="52" fill="#fff" font-size="13" '
                         f'text-anchor="middle">{name} {value / total:.0%}</text>')
        parts.append(f'<text x="{x:.1f}" y="92" fill="var(--muted)" font-size="11">{name}：{fmt_num(int(value))}</text>')
        x += w
    parts.append("</svg>")
    return "".join(parts)


# --------------------------------------------------------------------------- #
# 片段构造
# --------------------------------------------------------------------------- #
def ratio_text(rate: float, available: bool, nd: int = 0) -> str:
    """缺失指标显示「未采集」，不要用 0% 冒充——0% 会被读成"这个账号很差"。"""
    return f"{rate:.{nd}%}" if available else "未采集"


def card(label: str, value: str, desc: str = "", bar: float | None = None) -> str:
    bar_html = f'<div class="bar"><i style="width:{max(0, min(100, bar)):.0f}%"></i></div>' if bar is not None else ""
    return (f'<div class="card"><div class="k">{label}</div><div class="v">{value}</div>'
            f'{f"<div class=d>{desc}</div>" if desc else ""}{bar_html}</div>')


def build_slots(analysis: dict, dataset: dict, narrative: str, media_index: dict | None) -> dict:
    profile = analysis["profile"]
    eng, cad, content = analysis["engagement"], analysis["cadence"], analysis["content"]
    tier, health, monet = analysis["tier"], analysis["health"], analysis["monetization"]
    scores, formats, comments = analysis["scores"], analysis["formats"], analysis["comments"]
    notes = sorted(dataset.get("notes", []), key=lambda n: n.get("timestamp") or 0)

    nickname = profile.get("nickname") or profile.get("user_id") or "未知账号"
    title = f"小红书账号深度拆解 · {nickname}"

    score_cards = "".join([
        card("综合得分", str(scores["overall"]), "", scores["overall"]),
        card("商业价值", str(scores["business_value"]), "", scores["business_value"]),
        card("内容力", str(scores["content_strength"]), "", scores["content_strength"]),
        card("爆款确定性", str(scores["viral_certainty"]), "", scores["viral_certainty"]),
        card("可复制性", str(scores["replicability"]), "", scores["replicability"]),
    ])

    kpi_grid = "".join([
        card("粉丝", fmt_num(profile.get("fans", 0)), profile.get("ip_location") or "—"),
        card("采集笔记", str(analysis["notes_count"]), f"{cad.get('span_days', 0)} 天窗口"),
        card("峰值点赞", fmt_num(tier["peak_liked"]), tier["ceiling"]),
        card("点赞水位", fmt_num(tier["water_level"]), f"层级 {tier['level']} · {tier['shape']}"),
    ])

    verdict = (
        f"<p><strong>一句话判断：</strong>{nickname} 目前处于 "
        f"<span class='badge b-accent'>{tier['level']} 级 · {tier['shape']}</span>，"
        f"{tier['shape_desc']}。</p>"
        f"<p><strong>核心矛盾：</strong>峰值 {fmt_num(tier['peak_liked'])} 赞 vs 日常水位 "
        f"{fmt_num(tier['water_level'])} 赞，浓度系数 {tier['concentration']}×；"
        f"收藏/点赞 {eng['collect_like_ratio']:.0%}，评论/点赞 {eng['comment_like_ratio']:.2%}，"
        f"篇均互动/粉丝 {eng['engage_per_fan']:.2%}。</p>"
        f"<p><strong>下一步门槛：</strong>{tier['next_gate']}</p>"
    )

    concentration = tier.get("concentration", 0)
    tier_block = (
        "<div class='grid g3'>"
        + card("流量层级", tier["level"] + " 级", tier["ceiling"])
        + card("账号形态", tier["shape"], tier["shape_desc"])
        + card("浓度系数", f"{concentration:.1f}×", "P90 / 中位数，越高越依赖单条爆款")
        + "</div><p style='margin-top:12px;color:var(--muted)'>" + tier["next_gate"] + "</p>"
    )

    labels = [time.strftime("%m-%d", time.localtime(n["timestamp"] / 1000)) if n.get("timestamp") else ""
              for n in notes]
    values = [float(n.get("liked") or 0) for n in notes]
    totals = {
        "点赞": sum(n.get("liked", 0) for n in notes),
        "收藏": sum(n.get("collected", 0) for n in notes),
        "评论": sum(n.get("commented", 0) for n in notes),
        "分享": sum(n.get("shared", 0) for n in notes),
    }
    chart = svg_ratio_bar(list(totals.items()), height=110) + \
        svg_bars(values, labels, median=eng["liked"]["median"])

    complete = eng.get("data_completeness", {})
    engage_grid = "".join([
        card("收藏 / 点赞", ratio_text(eng["collect_like_ratio"], complete.get("collected")),
             "高于 30% 说明有工具属性" if complete.get("collected") else "需登录后采集",
             min(100, eng["collect_like_ratio"] * 200) if complete.get("collected") else None),
        card("评论 / 点赞", ratio_text(eng["comment_like_ratio"], complete.get("commented"), 2),
             "低于 1% 说明缺少讨论钩子" if complete.get("commented") else "需登录后采集",
             min(100, eng["comment_like_ratio"] * 1000) if complete.get("commented") else None),
        card("爆款率", f"{eng['viral_rate']:.0%}", f"{eng['viral_count']} 条 ≥ 3×水位",
             eng["viral_rate"] * 100),
        card("篇均互动/粉丝", f"{eng['engage_per_fan']:.2%}",
             "低于 0.5% 需警惕僵尸粉", min(100, eng["engage_per_fan"] * 500)),
    ])

    if health["flags"]:
        rows = "".join(
            f"<tr><td><span class='badge b-{ 'bad' if f['level']=='high' else ('mid' if f['level']=='mid' else 'ok')}'>"
            f"{ {'high':'高风险','mid':'中风险','ok':'正向'}[f['level']] }</span></td>"
            f"<td>{html.escape(f['item'])}</td><td>{html.escape(f['meaning'])}</td></tr>"
            for f in health["flags"])
        health_block = f"<table><thead><tr><th>级别</th><th>信号</th><th>解读</th></tr></thead><tbody>{rows}</tbody></table>"
    else:
        health_block = "<p>未发现明显的数据异常信号。</p>"
    health_block += f"<p style='margin-top:10px;color:var(--muted)'>整体风险等级：<strong>{health['risk_level']}</strong></p>"

    content_grid = "".join([
        card("标题均长", f"{content['title_len']['mean']}", f"中位数 {content['title_len']['median']}"),
        card("人群词命中", f"{content['audience_rate']:.0%}", "标题/正文出现明确人群锚点的比例"),
        card("痛点词命中", f"{content['pain_rate']:.0%}", "出现失败/焦虑场景的比例"),
        card("结构化词命中", f"{content['format_rate']:.0%}", "清单/教程/测评等可预期形式"),
    ]) + "".join([
        card("数字型标题", f"{content['number_title_rate']:.0%}"),
        card("疑问式标题", f"{content['question_title_rate']:.0%}"),
        card("命令式开头", f"{content['command_title_rate']:.0%}"),
        card("CTA 覆盖率", f"{content['cta_rate']:.0%}"),
    ])

    keyword_chips = "".join(f"<span class='tag'>{html.escape(k['word'])} · {k['count']}</span>"
                            for k in content["keywords"][:30]) or "无"

    if content["top_tags"]:
        rows = "".join(f"<tr><td>{html.escape(t['tag'])}</td><td class='num'>{t['count']}</td></tr>"
                       for t in content["top_tags"][:15])
        tag_table = (f"<table><thead><tr><th>标签</th><th>使用次数</th></tr></thead><tbody>{rows}</tbody></table>"
                     f"<p style='margin-top:8px;color:var(--muted)'>标签离散度 "
                     f"{content['tag_diversity']:.2f}（越低越聚焦），篇均 "
                     f"{content['avg_tags_per_note']} 个标签</p>")
    else:
        tag_table = "<p>该账号笔记未携带话题标签。</p>"

    # 图文 / 视频占比（旧 analysis.json 无这些字段时自动兜底，保证向后兼容）
    total_notes = formats.get("total_notes") or (formats["video_count"] + formats["image_count"])
    image_rate = formats.get("image_rate", round(1 - formats["video_rate"], 4))
    mix = formats.get("format_mix") or [
        {"label": "视频", "count": formats["video_count"], "rate": formats["video_rate"],
         "liked_median": formats["video_liked_median"], "collected_median": 0,
         "commented_median": 0},
        {"label": "图文", "count": formats["image_count"], "rate": image_rate,
         "liked_median": formats["image_liked_median"], "collected_median": 0,
         "commented_median": 0},
    ]
    mix_label = formats.get("mix_label") or (
        f"视频 {formats['video_count']} 条（{formats['video_rate']:.0%}） · "
        f"图文 {formats['image_count']} 条（{image_rate:.0%}）")

    mix_bar = svg_ratio_bar([(m["label"], m["count"]) for m in mix if m["count"]], height=110)
    mix_rows = "".join(
        f"<tr><td><strong>{html.escape(m['label'])}</strong></td>"
        f"<td class='num'>{m['count']}</td>"
        f"<td class='num'>{m['rate']:.0%}</td>"
        f"<td class='num'>{fmt_num(m.get('liked_median', 0))}</td>"
        f"<td class='num'>{fmt_num(m.get('collected_median', 0))}</td>"
        f"<td class='num'>{fmt_num(m.get('commented_median', 0))}</td></tr>"
        for m in mix)
    mix_table = (
        f"<table><thead><tr><th>内容形式</th><th>条数</th><th>占比</th>"
        f"<th>中位赞</th><th>中位收藏</th><th>中位评论</th></tr></thead>"
        f"<tbody>{mix_rows}</tbody></table>")

    format_grid = "".join([
        card("视频占比", f"{formats['video_rate']:.0%}",
             f"{formats['video_count']} 条视频", formats["video_rate"] * 100),
        card("图文占比", f"{image_rate:.0%}",
             f"{formats['image_count']} 条图文", image_rate * 100),
        card("占优形式", {"video": "视频", "image": "图文"}.get(formats["winner_format"], "—"),
             f"视频中位赞 {fmt_num(formats['video_liked_median'])} · "
             f"图文 {fmt_num(formats['image_liked_median'])}"),
        card("视频时长", f"{formats['duration_sec']['median']:.0f}s",
             f"区间 {formats['duration_sec']['min']:.0f}-{formats['duration_sec']['max']:.0f}s"),
        card("图文篇均图数", f"{formats['images_per_note']}", "每张图文笔记的平均图片数"),
        card("统计口径", f"{total_notes} 条", "以上占比基于本次抓取的全量笔记"),
    ]) + (
        f"<p style='margin:12px 0 6px'>内容形式结构：<strong>{html.escape(mix_label)}</strong>"
        f"（合计 {total_notes} 条，两种形式占比相加为 100%）</p>"
        + mix_bar + mix_table
    )

    cadence_block = (
        f"<p>观测窗口 <strong>{cad.get('span_days', 0)}</strong> 天，共 <strong>{cad.get('posts', 0)}</strong> 条，"
        f"更新频次 <strong>{cad.get('posts_per_week', 0)}</strong> 篇/周，中位间隔 "
        f"{cad.get('median_gap_hours', 0)} 小时，最长断更 {cad.get('max_gap_days', 0)} 天。"
        f"发布时段集中在 {_hours(cad.get('active_hours'))}。</p>"
        f"<p style='color:var(--muted)'>首次 {cad.get('first_post', '—')} / 最近 {cad.get('last_post', '—')}</p>"
    )

    if monet["detected"]:
        rows = "".join(
            f"<tr><td><strong>{html.escape(m)}</strong></td><td>{'、'.join(html.escape(s) for s in v['signals'][:8])}</td>"
            f"<td class='num'>{v['strength']}/10</td></tr>" for m, v in monet["detected"].items())
        monetize_block = (
            f"<table><thead><tr><th>变现模式</th><th>命中信号</th><th>强度</th></tr></thead><tbody>{rows}</tbody></table>"
            f"<p style='margin-top:10px'>账号阶段：<span class='badge b-accent'>{monet['fan_stage']}</span> "
            f"（{fmt_num(monet['fans'])} 粉丝）· CTA 覆盖率 {monet['cta_rate']:.0%}</p>"
            f"<p style='color:var(--muted)'>简介：{html.escape(monet['profile_desc'][:200]) or '（空）'}</p>"
        )
    else:
        monetize_block = (
            f"<p>未识别到明确的变现信号。账号阶段：<span class='badge b-accent'>{monet['fan_stage']}</span>，"
            f"CTA 覆盖率仅 {monet['cta_rate']:.0%}。</p>"
            f"<p style='color:var(--muted)'>简介：{html.escape(monet['profile_desc'][:200]) or '（空）'}</p>")

    if comments.get("count"):
        rate = comments["intent_rate"]
        rows = "".join(f"<tr><td>{html.escape(k)}</td><td class='num'>{v}</td>"
                       f"<td class='num'>{rate.get(k, 0):.1%}</td><td style='width:40%'>"
                       f"<div class='bar'><i style='width:{min(100, rate.get(k, 0) * 250):.0f}%'></i></div></td></tr>"
                       for k, v in comments["intent_distribution"].items())
        samples = "".join(
            f"<p><strong>{html.escape(k)}：</strong>" +
            " / ".join(html.escape(s[:40]) for s in v[:3]) + "</p>"
            for k, v in comments["intent_samples"].items())
        top = "".join(
            f"<tr><td class='num'>{c['like_count']}</td><td>{html.escape(c['content'])}</td>"
            f"<td>{html.escape(c['note_title'])}</td></tr>" for c in comments["top_comments"][:8])
        comments_block = (
            f"<p>采集评论 <strong>{comments['count']}</strong> 条，覆盖 "
            f"{comments['covered_notes']} 篇笔记。</p>"
            f"<table><thead><tr><th>意图</th><th>条数</th><th>占比</th><th>分布</th></tr></thead>"
            f"<tbody>{rows}</tbody></table><h3>典型原声</h3>{samples}"
            f"<h3>高赞评论</h3><table><thead><tr><th>赞</th><th>内容</th><th>来源笔记</th></tr></thead>"
            f"<tbody>{top}</tbody></table>")
    else:
        comments_block = "<p>未采集到评论数据（执行爬取时 --detail-top 需大于 0）。</p>"

    rows = ""
    for i, n in enumerate(analysis["top_notes"][:15], 1):
        rows += (f"<tr><td class='num'>{i}</td>"
                 f"<td>{html.escape((n['title'] or '(无标题)')[:40])}"
                 f"<div>{''.join(f'<span class=tag>{html.escape(t)}</span>' for t in n['tags'][:4])}</div></td>"
                 f"<td>{'视频' if n['type'] == 'video' else '图文'}"
                 f"<div class='d' style='color:var(--muted);font-size:11px'>{n.get('duration_sec', 0):.0f}s"
                 f" / {n.get('image_count', 0)}图</div></td>"
                 f"<td class='num'>{fmt_num(n['liked'])}</td>"
                 f"<td class='num'>{fmt_num(n['collected'])}</td>"
                 f"<td class='num'>{fmt_num(n['commented'])}</td>"
                 f"<td class='num'>{n['collect_like']:.0%}</td>"
                 f"<td><a href='{html.escape(n['note_url'])}' target='_blank' style='color:var(--accent)'>打开</a></td></tr>")
    top_table = (f"<table><thead><tr><th>#</th><th>标题 / 标签</th><th>形式</th><th>点赞</th>"
                 f"<th>收藏</th><th>评论</th><th>藏赞比</th><th>链接</th></tr></thead>"
                 f"<tbody>{rows}</tbody></table>")

    if analysis["gaps"]:
        rows = "".join(
            f"<tr><td>{html.escape(g['gap'])}</td><td class='num'>{html.escape(str(g['evidence']))}</td>"
            f"<td>{html.escape(g['action'])}</td></tr>" for g in analysis["gaps"])
        gaps_table = (f"<table><thead><tr><th>差距</th><th>证据</th><th>改进动作</th></tr></thead>"
                      f"<tbody>{rows}</tbody></table>")
    else:
        gaps_table = "<p>未发现结构性短板。</p>"

    media_section = ""
    if media_index and media_index.get("items"):
        cards = []
        for item in media_index["items"][:12]:
            src = item.get("sheet") or item.get("cover")
            if not src:
                continue
            rel = Path(src).as_posix()
            caption = (item.get("title") or "")[:26]
            extra = f" · {item['duration_sec']}s · {len(item.get('frames', []))}帧" if item.get("video") else ""
            cards.append(f"<figure><img src='{rel}' loading='lazy' alt=''>"
                         f"<figcaption>{html.escape(caption)}{extra}<br>"
                         f"<span style='color:var(--accent)'>{fmt_num(item.get('liked', 0))} 赞</span></figcaption></figure>")
        if cards:
            media_section = (f"<h2>附：爆款素材关键帧拼版</h2><div class='panel'><div class='gallery'>"
                             f"{''.join(cards)}</div></div>")

    narrative_html = md_to_html(narrative) if narrative else TODO

    meta = analysis.get("meta", {}) or {}
    window = meta.get("window", {}) or {}
    if window:
        span = f"近 {window.get('months')} 个月" if window.get("months") else "不限时间"
        window_text = (f"采集窗口 {span}"
                       f"（{window.get('start_date') or '不限'} 之后发布）")
        if window.get("dropped"):
            window_text += f" · 窗口外丢弃 {window['dropped']} 条"
    else:
        window_text = "采集窗口未记录"
    stopped = meta.get("stopped_reason") or "completed"

    return {
        "TITLE": title,
        "SUBTITLE": (f"{profile.get('desc', '')[:60] or '账号定位待诊断'} · "
                     f"{fmt_num(profile.get('fans', 0))} 粉丝 · {profile.get('ip_location') or '—'}"
                     f"<br><span style='color:var(--muted);font-size:13px'>"
                     f"{html.escape(window_text)} · 采集节奏 {html.escape(meta.get('pace', '—'))}"
                     f" · 结束原因 {html.escape(stopped)}</span>"),
        "GENERATED_AT": analysis.get("generated_at", ""),
        "SAMPLE_SIZE": str(analysis["notes_count"]),
        "SCORE_CARDS": score_cards,
        "VERDICT": verdict,
        "KPI_GRID": kpi_grid,
        "TIER_BLOCK": tier_block,
        "CHART_ENGAGEMENT": chart,
        "ENGAGE_GRID": engage_grid,
        "HEALTH_BLOCK": health_block,
        "CONTENT_GRID": content_grid,
        "KEYWORD_CHIPS": keyword_chips,
        "TAG_TABLE": tag_table,
        "FORMAT_GRID": format_grid,
        "CADENCE_BLOCK": cadence_block,
        "MONETIZE_BLOCK": monetize_block,
        "COMMENTS_BLOCK": comments_block,
        "TOP_NOTES_TABLE": top_table,
        "VIRAL_SECTION": TODO,
        "GAPS_TABLE": gaps_table,
        "SOP_SECTION": TODO,
        "ROADMAP_SECTION": TODO,
        "MEDIA_SECTION": media_section,
        "_narrative_html": narrative_html,
    }


def _hours(pairs) -> str:
    if not pairs:
        return "—"
    return "、".join(f"{h}:00-{(h + 3) % 24}:00({c}次)" for h, c in pairs[:3])


def render_html(slots: dict, narrative_map: dict) -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    data = dict(slots)
    # 叙事段落：允许 narrative.md 用二级标题分区，按标题关键字落到对应章节
    for key in ("VIRAL_SECTION", "SOP_SECTION", "ROADMAP_SECTION"):
        if narrative_map.get(key):
            data[key] = narrative_map[key]
    if narrative_map.get("MAIN"):
        data["VERDICT"] = data["VERDICT"] + narrative_map["MAIN"]
    for k, v in data.items():
        if k.startswith("_"):
            continue
        template = template.replace("{{" + k + "}}", v if isinstance(v, str) else "")
    return template


# --------------------------------------------------------------------------- #
# Markdown 报告
# --------------------------------------------------------------------------- #
def render_md(analysis: dict, dataset: dict, narrative: str, media_index: dict | None) -> str:
    p, e, c = analysis["profile"], analysis["engagement"], analysis["content"]
    t, h, m, s = analysis["tier"], analysis["health"], analysis["monetization"], analysis["scores"]
    f, cad, cm = analysis["formats"], analysis["cadence"], analysis["comments"]
    name = p.get("nickname") or p.get("user_id")
    lines: list[str] = []

    def h2(text): lines.append(f"\n## {text}\n")
    def h3(text): lines.append(f"\n### {text}\n")

    lines.append(f"# 小红书账号深度拆解 · {name}\n")
    lines.append(f"> 生成时间：{analysis['generated_at']} ｜ 样本：{analysis['notes_count']} 条笔记 ｜ "
                 f"采集通道：{analysis['meta'].get('tier', '—')}\n")
    _meta = analysis.get("meta", {}) or {}
    _win = _meta.get("window", {}) or {}
    if _win:
        _span = f"近 {_win.get('months')} 个月" if _win.get("months") else "不限时间"
        lines.append(f"> **采集窗口**：{_span}（{_win.get('start_date') or '不限'} 之后发布的笔记）"
                     f"｜节奏：{_meta.get('pace', '—')}"
                     f"｜结束原因：{_meta.get('stopped_reason', '—')}\n")
        if _win.get("dropped"):
            lines.append(f"> 窗口外已丢弃 {_win['dropped']} 条更早的笔记\n")

    h2("一、结论速览")
    lines.append(f"| 维度 | 得分 | 说明 |\n|---|---|---|")
    lines.append(f"| 综合 | **{s['overall']}** | 加权总分 |")
    lines.append(f"| 商业价值 | {s['business_value']} | {s['formula_note']} |")
    lines.append(f"| 内容力 | {s['content_strength']} | 人群/痛点/结构化词命中率 |")
    lines.append(f"| 爆款确定性 | {s['viral_certainty']} | 水位与浓度推导 |")
    lines.append(f"| 可复制性 | {s['replicability']} | 标签聚焦度与套路稳定度 |\n")
    lines.append(f"**一句话判断**：{name} 处于 {t['level']} 级 · {t['shape']}，{t['shape_desc']}。\n")
    _img_rate = f.get("image_rate", round(1 - f["video_rate"], 4))
    lines.append(f"- 内容形式结构：视频 {f['video_count']} 条（{f['video_rate']:.0%}） · "
                 f"图文 {f['image_count']} 条（{_img_rate:.0%}）"
                 f"（口径：全部 {analysis['notes_count']} 条）｜占优形式："
                 f"{ {'video': '视频', 'image': '图文'}.get(f['winner_format'], '—') }")
    lines.append(f"- 峰值 {fmt_num(t['peak_liked'])} 赞 / 水位 {fmt_num(t['water_level'])} 赞 / "
                 f"浓度 {t['concentration']:.1f}× / 稳态 {t.get('steadiness', 0):.2f}")
    comp = e.get("data_completeness", {})
    lines.append(f"- 收藏赞比 {ratio_text(e['collect_like_ratio'], comp.get('collected'))} ｜ "
                 f"评论赞比 {ratio_text(e['comment_like_ratio'], comp.get('commented'), 2)} ｜ "
                 f"篇均互动/粉丝 {e['engage_per_fan']:.2%}")
    if comp.get("missing"):
        lines.append(f"- ⚠️ **{'、'.join(comp['missing'])}未采集到**（免登录通道只下发点赞数），"
                     f"相关指标与结论暂缺；登录后重跑即可补齐")
    lines.append(f"- 下一步门槛：{t['next_gate']}\n")
    lines.append("> ✍️ **待补写**：商业定位诊断（变现模式是否健康、天花板在哪）\n")

    h2("二、账号基本盘")
    lines.append(f"- 昵称：{name}（{p.get('red_id') or '红书号未获取'}）")
    lines.append(f"- 粉丝：{fmt_num(p.get('fans', 0))} ｜ IP 属地：{p.get('ip_location') or '—'}")
    lines.append(f"- 简介：{p.get('desc') or '（空）'}")
    lines.append(f"- 观测窗口：{cad.get('span_days', 0)} 天 / {cad.get('posts', 0)} 条，"
                 f"更新 {cad.get('posts_per_week', 0)} 篇/周，中位间隔 {cad.get('median_gap_hours', 0)} 小时")
    lines.append(f"- 发布时段：{_hours(cad.get('active_hours'))}\n")

    h2("三、互动结构与流量层级")
    lines.append(f"| 指标 | 中位数 | 均值 | P90 | 最高 |\n|---|---|---|---|---|")
    for key, label in (("liked", "点赞"), ("collected", "收藏"), ("commented", "评论")):
        blk = e[key]
        lines.append(f"| {label} | {fmt_num(blk['median'])} | {fmt_num(blk['mean'])} | "
                     f"{fmt_num(blk.get('p90', 0))} | {fmt_num(blk.get('max', 0))} |")
    lines.append("")
    lines.append(f"- 爆款率 {e['viral_rate']:.0%}（{e['viral_count']} 条 ≥ 3 倍水位）")
    lines.append(f"- 头部单条占总量 {e['top1_share']:.0%}，浓度系数 {e['concentration']:.1f}×，"
                 f"水位占峰值 {t.get('water_ratio', 0):.1%}")
    lines.append(f"- 数据健康：{ {'high': '高风险', 'mid': '中风险', 'low': '良好'}[h['risk_level']] }")
    for flag in h["flags"]:
        lines.append(f"  - [{flag['level']}] {flag['item']} → {flag['meaning']}")
    lines.append("\n> ✍️ **待补写**：算法逻辑推演（流量层级跃迁路径、标签精准度、赛道拥挤度）\n")

    h2("四、内容结构拆解")
    lines.append(f"| 结构指标 | 数值 |\n|---|---|")
    lines.append(f"| 标题均长 | {c['title_len']['mean']} 字 |")
    lines.append(f"| 人群词命中率 | {c['audience_rate']:.0%} |")
    lines.append(f"| 痛点词命中率 | {c['pain_rate']:.0%} |")
    lines.append(f"| 结构化词命中率 | {c['format_rate']:.0%} |")
    lines.append(f"| 数字型标题 | {c['number_title_rate']:.0%} |")
    lines.append(f"| 疑问式标题 | {c['question_title_rate']:.0%} |")
    lines.append(f"| 命令式开头 | {c['command_title_rate']:.0%} |")
    lines.append(f"| CTA 覆盖率 | {c['cta_rate']:.0%} |")
    lines.append(f"| 篇均 emoji | {c['emoji_per_note']} |")
    lines.append(f"| 标签离散度 | {c['tag_diversity']:.2f} |")
    lines.append(f"| 篇均标签数 | {c['avg_tags_per_note']} |\n")
    lines.append("高频关键词：" + "、".join(f"{k['word']}({k['count']})" for k in c["keywords"][:20]))
    lines.append("\nTop 标签：" + "、".join(f"#{t['tag']}({t['count']})" for t in c["top_tags"][:12]))
    lines.append("\n> ✍️ **待补写**：选题库结构 / 标题公式 / 正文骨架 / 钩子设置\n")

    h2("五、形式与节奏")
    f_total = f.get("total_notes") or (f["video_count"] + f["image_count"])
    f_image_rate = f.get("image_rate", round(1 - f["video_rate"], 4))
    f_mix_label = f.get("mix_label") or (
        f"视频 {f['video_count']} 条（{f['video_rate']:.0%}） · "
        f"图文 {f['image_count']} 条（{f_image_rate:.0%}）")
    lines.append(f"- **内容形式结构：{f_mix_label}**（口径：本次抓取的全部 {f_total} 条笔记）")
    lines.append("")
    lines.append("| 内容形式 | 条数 | 占比 | 中位赞 | 中位收藏 | 中位评论 |")
    lines.append("|---|---|---|---|---|---|")
    for item in (f.get("format_mix") or [
        {"label": "视频", "count": f["video_count"], "rate": f["video_rate"],
         "liked_median": f["video_liked_median"], "collected_median": 0, "commented_median": 0},
        {"label": "图文", "count": f["image_count"], "rate": f_image_rate,
         "liked_median": f["image_liked_median"], "collected_median": 0, "commented_median": 0},
    ]):
        lines.append(f"| {item['label']} | {item['count']} | {item['rate']:.0%} | "
                     f"{fmt_num(item.get('liked_median', 0))} | "
                     f"{fmt_num(item.get('collected_median', 0))} | "
                     f"{fmt_num(item.get('commented_median', 0))} |")
    lines.append("")
    lines.append(f"- 占优形式：{ {'video': '视频', 'image': '图文'}.get(f['winner_format'], '—') }"
                 f"（按中位赞比较）")
    lines.append(f"- 视频时长中位 {f['duration_sec']['median']:.0f}s"
                 f"（{f['duration_sec']['min']:.0f}-{f['duration_sec']['max']:.0f}s）")
    lines.append(f"- 图文篇均 {f['images_per_note']} 张图")
    lines.append(f"- 最长断更 {cad.get('max_gap_days', 0)} 天\n")

    h2("六、商业定位诊断")
    if m["detected"]:
        lines.append("| 变现模式 | 命中信号 | 强度 |\n|---|---|---|")
        for model, v in m["detected"].items():
            lines.append(f"| {model} | {'、'.join(v['signals'][:8])} | {v['strength']}/10 |")
    else:
        lines.append("未识别到明确变现信号。")
    lines.append(f"\n- 账号阶段：{m['fan_stage']}（{fmt_num(m['fans'])} 粉丝）")
    lines.append(f"- CTA 覆盖率：{m['cta_rate']:.0%}")
    lines.append("\n> ✍️ **待补写**：变现健康度诊断（是否过度依赖广告 / 客单价与转化链路 / 天花板）\n")

    h2("七、评论洞察")
    if cm.get("count"):
        lines.append(f"采集 {cm['count']} 条评论，覆盖 {cm['covered_notes']} 篇笔记。\n")
        lines.append("| 意图 | 条数 | 占比 |\n|---|---|---|")
        for k, v in cm["intent_distribution"].items():
            lines.append(f"| {k} | {v} | {cm['intent_rate'].get(k, 0):.1%} |")
        lines.append("\n> ✍️ **待补写**：用户真实需求聚类 → 反推下期选题\n")
    else:
        lines.append("未采集评论。")

    h2("八、TOP 内容榜")
    lines.append("| # | 标题 | 形式 | 点赞 | 收藏 | 评论 | 藏赞比 | 链接 |\n|---|---|---|---|---|---|---|---|")
    for i, n in enumerate(analysis["top_notes"][:15], 1):
        lines.append(f"| {i} | {(n['title'] or '(无标题)')[:34]} | "
                     f"{'视频' if n['type'] == 'video' else '图文'} | {fmt_num(n['liked'])} | "
                     f"{fmt_num(n['collected'])} | {fmt_num(n['commented'])} | {n['collect_like']:.0%} | "
                     f"[打开]({n['note_url']}) |")

    h2("九、爆款结构拆解")
    lines.append("> ✍️ **待补写**（必须结合素材）：\n")
    lines.append("1. 按素材清单逐条核对可用素材：封面图、关键帧拼版、视频原片，缺哪类注明降级")
    lines.append("2. 黄金前 3 秒：画面信息 + 口播首句 + 字幕钩子")
    lines.append("3. 中段结构：信息密度曲线 / 节奏点 / 转场方式")
    lines.append("4. 结尾设计：CTA 与评论引导")
    lines.append("5. 封面：排版、字数、配色、情绪脸\n")
    if media_index and media_index.get("items"):
        lines.append("已就绪素材：")
        for item in media_index["items"][:10]:
            lines.append(f"- `{item['note_id']}` {(item.get('title') or '')[:24]} ｜ "
                         f"{fmt_num(item.get('liked', 0))} 赞 ｜ "
                         f"{'视频 ' + str(item.get('duration_sec', '')) + 's / ' + str(len(item.get('frames', []))) + ' 关键帧' if item.get('video') else '图文'}"
                         f"{' ｜ sheet: ' + item['sheet'] if item.get('sheet') else ''}")

    h2("十、差距清单与改进动作")
    if analysis["gaps"]:
        lines.append("| 差距 | 证据 | 改进动作 |\n|---|---|---|")
        for g in analysis["gaps"]:
            lines.append(f"| {g['gap']} | {g['evidence']} | {g['action']} |")
    else:
        lines.append("未发现结构性短板。")

    h2("十一、可复制 SOP")
    lines.append("> ✍️ **待补写**：选题库 / 拍摄清单 / 剪辑模板 / 发布节奏 / 数据复盘表\n")

    h2("十二、执行排期")
    lines.append("> ✍️ **待补写**：按 30 天拆成 4 周，每周目标、动作与验收指标\n")

    if narrative:
        lines.append("\n---\n\n# 附录：深度分析叙事\n")
        lines.append(narrative)

    return "\n".join(lines) + "\n"


def split_narrative(text: str) -> dict:
    """把 narrative.md 按二级标题拆到对应章节。"""
    result = {"MAIN": "", "VIRAL_SECTION": "", "SOP_SECTION": "", "ROADMAP_SECTION": ""}
    if not text:
        return result
    mapping = [
        (("爆款", "结构拆解", "分镜", "视频结构"), "VIRAL_SECTION"),
        (("SOP", "标准作业", "执行手册", "运营流程"), "SOP_SECTION"),
        (("排期", "路线", "roadmap", "30天", "三十天"), "ROADMAP_SECTION"),
    ]
    blocks: list[tuple[str, str]] = []
    current_title, current_body = "", []
    for line in text.split("\n"):
        m = re.match(r"^##\s+(.*)", line)
        if m:
            blocks.append((current_title, "\n".join(current_body).strip()))
            current_title, current_body = m.group(1), []
        else:
            current_body.append(line)
    blocks.append((current_title, "\n".join(current_body).strip()))

    for title, body in blocks:
        if not body:
            continue
        key = "MAIN"
        for keys, target in mapping:
            if any(k.lower() in title.lower() for k in keys):
                key = target
                break
        result[key] += md_to_html(f"### {title}\n{body}") if title else md_to_html(body)
        result[key] += "\n"
    return result


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--analysis", required=True)
    ap.add_argument("--dataset", default="")
    ap.add_argument("--narrative", default="", help="Agent 撰写的叙事 Markdown")
    ap.add_argument("--media-index", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--format", default="both", choices=["md", "html", "both"])
    args = ap.parse_args()

    analysis_path = Path(args.analysis).resolve()
    analysis = read_json(analysis_path)
    if not analysis:
        raise SystemExit(f"读取失败：{analysis_path}")
    out_dir = Path(args.out).resolve() if args.out else analysis_path.parent
    dataset = read_json(Path(args.dataset)) if args.dataset else {}
    narrative = Path(args.narrative).read_text(encoding="utf-8") if args.narrative and Path(args.narrative).exists() else ""
    media_index = read_json(Path(args.media_index)) if args.media_index else None
    if media_index is None:
        candidate = out_dir / "media" / "media_index.json"
        media_index = read_json(candidate) if candidate.exists() else None

    if args.format in ("md", "both"):
        md = render_md(analysis, dataset, narrative, media_index)
        (out_dir / "report.md").write_text(md, encoding="utf-8")
        log.info("Markdown 报告：%s", out_dir / "report.md")

    if args.format in ("html", "both"):
        slots = build_slots(analysis, dataset, narrative, media_index)
        narrative_map = split_narrative(narrative) if narrative else {}
        html_text = render_html(slots, narrative_map)
        (out_dir / "report.html").write_text(html_text, encoding="utf-8")
        log.info("HTML 报告：%s", out_dir / "report.html")
    return 0


if __name__ == "__main__":
    from xhs_env import ensure_ready
    ensure_ready(need_browser=False)     # 纯渲染，不需要 Chromium 内核
    raise SystemExit(main())
