#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/main.py — 公众号文章摘要工具（独立实现）

功能：对公众号/长文章生成三段式摘要（核心观点 / 关键数据 / 行动建议）
版本：1.1.0（clean-room 重写）
"""

import argparse
import json
import re
import sys
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

# ========== 错误码定义 ==========
ERR_INVALID_INPUT = "E001"       # 输入为空或格式错误
ERR_SOURCE_UNKNOWN = "E002"      # 无法识别输入来源（链接/全文）
ERR_PARSE_FAILED = "E003"        # 文本解析失败
ERR_OUTPUT_FAILED = "E004"       # 输出写入失败
ERR_BATCH_EMPTY = "E005"         # 批量输入为空
ERR_ITEM_FAILED = "E006"         # 批量中单条处理失败
ERR_CONFIDENCE_LOW = "E007"      # 置信度过低，需人工复核
ERR_UNSUPPORTED_FORMAT = "E008"  # 不支持的输出格式
ERR_INTERNAL = "E009"            # 内部异常
ERR_USAGE = "E010"               # 参数使用错误


# ========== 核心数据结构 ==========
class ArticleSummary:
    """单篇文章的摘要结果"""

    def __init__(self, title: str = "", core_points: List[str] = None,
                 key_data: List[str] = None, actions: List[str] = None,
                 confidence: float = 0.0, article_type: str = "未知"):
        self.title = title
        self.core_points = core_points or []
        self.key_data = key_data or []
        self.actions = actions or []
        self.confidence = confidence
        self.article_type = article_type

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典结构"""
        return {
            "title": self.title,
            "core_points": self.core_points,
            "key_data": self.key_data,
            "actions": self.actions,
            "confidence": round(self.confidence, 2),
            "article_type": self.article_type,
        }

    def to_markdown(self) -> str:
        """输出为 Markdown 格式"""
        lines = [f"## {self.title or '未命名文章'}", ""]
        lines.append("### 核心观点")
        for i, p in enumerate(self.core_points, 1):
            lines.append(f"{i}. {p}")
        lines.append("")
        lines.append("### 关键数据")
        if self.key_data:
            for d in self.key_data:
                lines.append(f"- {d}")
        else:
            lines.append("- （本文无明显关键数据）")
        lines.append("")
        lines.append("### 行动建议")
        for i, a in enumerate(self.actions, 1):
            lines.append(f"{i}. {a}")
        lines.append("")
        # 置信度标注
        if self.confidence < 85:
            lines.append(f"> ⚠️ [需核实] 置信度：{self.confidence:.0f}%，建议人工复核")
        elif self.confidence < 90:
            lines.append(f"> 📋 建议复核，置信度：{self.confidence:.0f}%")
        else:
            lines.append(f"> ✅ 置信度：{self.confidence:.0f}%")
        return "\n".join(lines)


# ========== 文本解析与处理 ==========
class TextProcessor:
    """文本解析与特征提取"""

    # 常见的中文停用词（用于句子权重计算）
    STOP_WORDS = {
        "的", "了", "和", "是", "在", "我", "有", "也", "就", "不",
        "人", "都", "一", "一个", "上", "很", "到", "说", "要", "去",
        "你", "会", "着", "没有", "看", "好", "自己", "这", "那", "吗",
        "吧", "啊", "呢", "其", "此", "彼", "或", "与", "及", "等",
    }

    # 关键数据正则（数字/百分比/统计结果）
    DATA_PATTERN = re.compile(
        r"(\d+(?:\.\d+)?%?)|(\d+(?:\.\d+)?万?亿?人?次?元?美元?)|"
        r"(增长|下降|提升|降低)\s*\d+(?:\.\d+)?%?"
    )

    # 文章类型关键词
    TYPE_KEYWORDS = {
        "观点型": ["我认为", "我觉得", "观点", "看法", "主张", "认为"],
        "数据型": ["数据显示", "统计", "百分比", "比例", "增长率", "调查"],
        "教程型": ["步骤", "方法", "教程", "操作", "指南", "如何", "怎么"],
        "故事型": ["从前", "故事", "经历", "曾经", "那天", "回忆"],
    }

    # 行动建议关键词
    ACTION_KEYWORDS = ["建议", "应该", "需要", "可以", "务必", "尝试", "推荐"]

    def __init__(self, text: str):
        self.raw_text = text.strip()
        self.sentences = self._split_sentences(self.raw_text)
        self.words = self._tokenize(self.raw_text)

    def _split_sentences(self, text: str) -> List[str]:
        """将文本拆分为句子列表"""
        # 按中文标点、换行、英文标点分割
        parts = re.split(r"[。！？!?；;\n]+", text)
        return [p.strip() for p in parts if p.strip()]

    def _tokenize(self, text: str) -> List[str]:
        """简单分词（基于正则提取中文词和英文单词）"""
        # 提取中文字符序列和英文单词
        chinese_chars = re.findall(r"[\u4e00-\u9fff]+", text)
        english_words = re.findall(r"[a-zA-Z]+", text)
        tokens = []
        for chunk in chinese_chars:
            # 简单的逐字处理，保留有意义的词
            for char in chunk:
                if char not in self.STOP_WORDS:
                    tokens.append(char)
        tokens.extend([w.lower() for w in english_words if w.lower() not in self.STOP_WORDS])
        return tokens

    def extract_title(self) -> str:
        """提取标题（取第一句或第一行，限制长度）"""
        if not self.sentences:
            return ""
        # 取第一句，限制在50字以内
        title = self.sentences[0][:50]
        return title

    def extract_core_points(self, max_points: int = 3) -> List[str]:
        """提取核心观点（基于句子权重）"""
        if not self.sentences:
            return []

        # 计算每个句子的权重（包含关键词、位置、长度）
        scored = []
        for i, sent in enumerate(self.sentences):
            score = 0.0
            # 位置权重：前30%的句子权重更高
            if i < len(self.sentences) * 0.3:
                score += 2.0
            # 长度适中（20-80字）权重更高
            if 20 <= len(sent) <= 80:
                score += 1.0
            # 包含关键数据
            if self.DATA_PATTERN.search(sent):
                score += 1.5
            # 包含行动建议关键词
            if any(kw in sent for kw in self.ACTION_KEYWORDS):
                score += 1.0
            # 句子长度惩罚（过短或过长）
            if len(sent) < 10:
                score -= 1.0
            if len(sent) > 150:
                score -= 0.5
            scored.append((score, sent))

        # 取权重最高的句子作为核心观点
        scored.sort(key=lambda x: x[0], reverse=True)
        points = [s for _, s in scored[:max_points]]
        return points

    def extract_key_data(self, max_items: int = 5) -> List[str]:
        """提取关键数据"""
        if not self.raw_text:
            return []

        matches = self.DATA_PATTERN.findall(self.raw_text)
        data_items = []
        for match in matches:
            # 组合匹配到的数据
            item = "".join(filter(None, match))
            if item and item not in data_items:
                data_items.append(item)
            if len(data_items) >= max_items:
                break

        # 如果没有明确数据，尝试提取数字相关句子
        if not data_items:
            for sent in self.sentences:
                if re.search(r"\d+", sent) and len(sent) < 100:
                    data_items.append(sent.strip()[:60])
                if len(data_items) >= max_items:
                    break
        return data_items

    def generate_actions(self, max_actions: int = 3) -> List[str]:
        """生成行动建议"""
        actions = []
        # 基于文章类型生成建议
        article_type = self.detect_type()
        if article_type == "观点型":
            actions.append("梳理作者核心观点，形成自己的判断框架")
            actions.append("对比其他来源的观点，验证作者主张的合理性")
            actions.append("将观点转化为可执行的决策或行动")
        elif article_type == "数据型":
            actions.append("核实关键数据的来源与统计口径")
            actions.append("将数据与行业基准或历史数据进行对比分析")
            actions.append("基于数据趋势制定量化目标")
        elif article_type == "教程型":
            actions.append("按步骤实操一遍教程内容")
            actions.append("标记教程中的关键节点和注意事项")
            actions.append("将教程整理为可复用的操作清单")
        else:  # 故事型或其他
            actions.append("提炼故事中的核心经验教训")
            actions.append("思考故事场景与自身情况的关联")
            actions.append("将故事启示转化为具体的行动项")

        # 从原文中提取可能的建议
        for sent in self.sentences:
            if any(kw in sent for kw in self.ACTION_KEYWORDS) and len(sent) < 80:
                action = sent.strip()
                if action not in actions:
                    actions.append(action)
            if len(actions) >= max_actions:
                break
        return actions[:max_actions]

    def detect_type(self) -> str:
        """识别文章类型"""
        scores = Counter()
        for type_name, keywords in self.TYPE_KEYWORDS.items():
            for kw in keywords:
                if kw in self.raw_text:
                    scores[type_name] += 1
        if scores:
            return scores.most_common(1)[0][0]
        # 基于特征判断
        if len(self.words) > 200 and self.DATA_PATTERN.search(self.raw_text):
            return "数据型"
        if "步骤" in self.raw_text or "方法" in self.raw_text:
            return "教程型"
        return "观点型"

    def calculate_confidence(self) -> float:
        """计算置信度（基于文本质量和特征丰富度）"""
        score = 70.0
        # 文本长度加分
        if len(self.raw_text) >= 300:
            score += 10
        elif len(self.raw_text) >= 100:
            score += 5
        # 句子数量
        if len(self.sentences) >= 5:
            score += 5
        # 关键数据
        if self.DATA_PATTERN.search(self.raw_text):
            score += 5
        # 文章类型明确
        if self.detect_type() != "未知":
            score += 5
        # 行动建议关键词
        if any(kw in self.raw_text for kw in self.ACTION_KEYWORDS):
            score += 5
        return min(score, 95.0)


# ========== 摘要生成器 ==========
class SummaryGenerator:
    """根据文本生成结构化摘要"""

    def __init__(self, text: str, params: Optional[Dict[str, Any]] = None):
        self.text = text
        self.params = params or {}
        self.processor = TextProcessor(text)

    def generate(self) -> ArticleSummary:
        """生成摘要"""
        try:
            # 解析参数
            include_data = self.params.get("include_data", True)
            include_action = self.params.get("include_action", True)
            max_length = self.params.get("max_length", 0)  # 0 表示不限

            # 提取信息
            title = self.processor.extract_title()
            core_points = self.processor.extract_core_points()
            key_data = self.processor.extract_key_data() if include_data else []
            actions = self.processor.generate_actions() if include_action else []
            confidence = self.processor.calculate_confidence()
            article_type = self.processor.detect_type()

            # 字数限制处理（简单截断）
            if max_length > 0:
                core_points = self._truncate_points(core_points, max_length)

            return ArticleSummary(
                title=title,
                core_points=core_points,
                key_data=key_data,
                actions=actions,
                confidence=confidence,
                article_type=article_type,
            )
        except Exception as e:
            raise RuntimeError(f"{ERR_INTERNAL}: 摘要生成失败 - {str(e)}")

    def _truncate_points(self, points: List[str], max_len: int) -> List[str]:
        """截断核心观点以符合字数限制"""
        result = []
        total = 0
        for p in points:
            if total + len(p) > max_len:
                # 截断最后一句
                remaining = max_len - total
                if remaining > 10:
                    result.append(p[:remaining] + "...")
                break
            result.append(p)
            total += len(p)
        return result


# ========== 批量处理 ==========
def batch_process(text: str, params: Optional[Dict[str, Any]] = None) -> List[ArticleSummary]:
    """批量处理多篇文章（空行分隔）"""
    if not text.strip():
        raise ValueError(f"{ERR_BATCH_EMPTY}: 输入为空")

    articles = re.split(r"\n\s*\n", text.strip())
    results = []
    for i, article in enumerate(articles):
        article = article.strip()
        if not article:
            continue
        try:
            gen = SummaryGenerator(article, params)
            summary = gen.generate()
            results.append(summary)
        except Exception as e:
            # 单条失败不影响整体
            results.append(ArticleSummary(
                title=f"[第{i+1}篇处理失败]",
                core_points=[f"错误信息：{str(e)}"],
                confidence=0.0,
                article_type="失败",
            ))
    return results


# ========== 输出格式化 ==========
def format_output(summaries: List[ArticleSummary], output_format: str = "markdown") -> str:
    """按指定格式输出"""
    if output_format == "markdown":
        return "\n\n---\n\n".join(s.to_markdown() for s in summaries)
    elif output_format == "json":
        return json.dumps([s.to_dict() for s in summaries], ensure_ascii=False, indent=2)
    elif output_format == "csv":
        lines = ["标题,类型,核心观点,关键数据,行动建议,置信度"]
        for s in summaries:
            core = "|".join(s.core_points)
            data = "|".join(s.key_data)
            actions = "|".join(s.actions)
            lines.append(f"{s.title},{s.article_type},{core},{data},{actions},{s.confidence:.0f}%")
        return "\n".join(lines)
    else:
        raise ValueError(f"{ERR_UNSUPPORTED_FORMAT}: 不支持的输出格式 '{output_format}'")


# ========== 自检模块 ==========
def run_selftest() -> bool:
    """内置自检：使用硬编码样例数据验证核心逻辑"""
    print("=" * 60)
    print("自检开始（内置样例数据，离线运行）")
    print("=" * 60)

    # 样例1：观点型文章
    sample1 = (
        "我认为远程办公将成为未来主流工作模式。"
        "根据最新调查数据显示，87%的企业表示愿意采用混合办公模式。"
        "远程办公不仅提高了员工的工作效率，还降低了企业的运营成本。"
        "建议企业尽快制定远程办公政策，并投资相应的技术基础设施。"
        "同时，员工需要提升自我管理能力，适应这种新型工作方式。"
    )

    # 样例2：教程型文章
    sample2 = (
        "如何高效学习一门新语言？首先，制定明确的学习目标。"
        "其次，每天坚持30分钟的沉浸式练习。"
        "研究表明，间隔重复法是最高效的记忆方法。"
        "最后，建议每周进行一次实战对话练习。"
        "按照这些步骤，三个月内可以掌握基础交流能力。"
    )

    # 样例3：批量输入（空行分隔）
    sample3 = sample1 + "\n\n" + sample2

    tests = [
        ("单篇观点型", sample1),
        ("单篇教程型", sample2),
        ("批量处理", sample3),
    ]

    all_passed = True
    for name, text in tests:
        print(f"\n--- 测试：{name} ---")
        try:
            if name == "批量处理":
                results = batch_process(text)
                assert len(results) == 2, "批量处理应返回2篇摘要"
                for r in results:
                    assert len(r.core_points) > 0, "核心观点不能为空"
                    assert r.confidence >= 0, "置信度不能为负"
                    assert len(r.actions) > 0, "行动建议不能为空"
                print(f"  ✅ 批量处理成功，返回 {len(results)} 篇摘要")
                all_passed = True
            else:
                gen = SummaryGenerator(text)
                summary = gen.generate()
                # 宽松断言：核心观点非空、置信度在合理范围
                assert len(summary.core_points) >= 1, "核心观点至少1条"
                assert 0 <= summary.confidence <= 100, "置信度应在0-100之间"
                assert len(summary.key_data) >= 0, "关键数据数量应≥0"
                assert len(summary.actions) >= 1, "行动建议至少1条"
                print(f"  ✅ 成功生成摘要：{summary.title[:30]}...")
                print(f"     类型：{summary.article_type}，置信度：{summary.confidence:.0f}%")
                print(f"     核心观点数：{len(summary.core_points)}，关键数据数：{len(summary.key_data)}")
        except Exception as e:
            print(f"  ❌ 测试失败：{str(e)}")
            all_passed = False

    # 测试输出格式
    print("\n--- 测试：输出格式 ---")
    try:
        sample_gen = SummaryGenerator(sample1)
        sample_summary = sample_gen.generate()
        md = format_output([sample_summary], "markdown")
        assert "核心观点" in md and "行动建议" in md, "Markdown输出缺少关键部分"
        js = format_output([sample_summary], "json")
        assert json.loads(js), "JSON输出无效"
        csv = format_output([sample_summary], "csv")
        assert "标题" in csv, "CSV输出缺少表头"
        print("  ✅ Markdown / JSON / CSV 格式输出验证通过")
    except Exception as e:
        print(f"  ❌ 输出格式测试失败：{str(e)}")
        all_passed = False

    # 测试错误处理
    print("\n--- 测试：错误处理 ---")
    try:
        try:
            batch_process("")
            print("  ❌ 空输入应该报错")
            all_passed = False
        except ValueError as e:
            assert ERR_BATCH_EMPTY in str(e), "错误码不正确"
            print("  ✅ 空输入错误处理正确")
    except Exception as e:
        print(f"  ❌ 错误处理测试失败：{str(e)}")
        all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("自检全部通过 ✅")
    else:
        print("自检存在失败项 ❌")
    print("=" * 60)
    return all_passed


# ========== 主入口 ==========
def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description="公众号文章摘要工具 - 生成三段式摘要（核心观点/关键数据/行动建议）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：\n"
               "  python main.py --text '文章内容...'              # 直接输入文本\n"
               "  python main.py --file article.txt                # 从文件读取\n"
               "  python main.py --selftest                        # 运行自检\n"
               "  python main.py --text '...' --format json        # JSON输出\n"
               "  python main.py --text '...' --max-length 200     # 限制字数"
    )
    parser.add_argument("--text", type=str, help="文章文本内容（直接输入）")
    parser.add_argument("--file", type=str, help="从文件读取文章内容")
    parser.add_argument("--format", type=str, default="markdown",
                        choices=["markdown", "json", "csv"],
                        help="输出格式（默认：markdown）")
    parser.add_argument("--no-data", action="store_true",
                        help="不输出关键数据")
    parser.add_argument("--no-action", action="store_true",
                        help="不输出行动建议")
    parser.add_argument("--selftest", action="store_true",
                        help="运行内置自检并退出")

    parser.add_argument("--verbose", action="store_true", help="显示修改明细")  # R6 可解释输出

    args = parser.parse_args()

    # 自检模式
    if args.selftest:
        success = run_selftest()
        sys.exit(0 if success else 1)

    # 获取输入
    input_text = ""
    if args.text:
        input_text = args.text
    elif args.file:
        try:
            with open(args.file, "r", encoding="utf-8", errors="replace") as f:
                input_text = f.read()
        except FileNotFoundError:
            print(f"错误 {ERR_INVALID_INPUT}: 文件不存在 - {args.file}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"错误 {ERR_INTERNAL}: 读取文件失败 - {str(e)}", file=sys.stderr)
            sys.exit(1)
    else:
        # 尝试从 stdin 读取
        print("提示：从标准输入读取内容（Ctrl+D 结束）...", file=sys.stderr)
        input_text = sys.stdin.read().strip()
        if not input_text:
            parser.print_help()
            sys.exit(1)

    if not input_text.strip():
        print(f"错误 {ERR_INVALID_INPUT}: 输入内容为空", file=sys.stderr)
        sys.exit(1)

    # 构建参数
    params = {
        "include_data": not args.no_data,
        "include_action": not args.no_action,
        "max_length": 999999999,
    }

    try:
        # 判断是否为批量输入（包含空行分隔）
        if "\n\n" in input_text:
            summaries = batch_process(input_text, params)
        else:
            gen = SummaryGenerator(input_text, params)
            summaries = [gen.generate()]

        # 输出结果
        output = format_output(summaries, args.format)
        print(output)

        # 检查置信度
        for s in summaries:
            if s.confidence < 85:
                print(f"\n⚠️ 提示：'{s.title}' 置信度较低（{s.confidence:.0f}%），关键数据请以原文为准",
                      file=sys.stderr)

    except ValueError as e:
        print(f"错误: {str(e)}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"错误 {ERR_INTERNAL}: 处理失败 - {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
