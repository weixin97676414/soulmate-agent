#!/usr/bin/env python3
"""
舆情监控报告生成器 v3.0
- 模板注入架构：HTML 模板 + JSON 数据分离
- 兼容新旧两套 JSON schema
- 自动查找模板路径（assets/report_template.html）
"""
import json
import sys
import os
import argparse
from pathlib import Path
from datetime import datetime


def find_template(custom_path=None):
    """查找模板文件"""
    if custom_path and os.path.exists(custom_path):
        return custom_path
    # 相对脚本目录查找
    script_dir = Path(__file__).parent.parent
    default = script_dir / "assets" / "report_template.html"
    if default.exists():
        return str(default)
    print("❌ 找不到模板文件 assets/report_template.html")
    sys.exit(1)


def generate_report(input_path, output_path, template_path=None):
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 补充 generated_at
    if "report_meta" in data:
        if not data["report_meta"].get("generated_at"):
            data["report_meta"]["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elif not data.get("generated_at"):
        data["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    tmpl = find_template(template_path)
    with open(tmpl, "r", encoding="utf-8") as f:
        html = f.read()

    report_html = html.replace("__REPORT_DATA__", json.dumps(data, ensure_ascii=False, indent=2))

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_html)

    meta = data.get("report_meta", data)
    total = meta.get("total_items") or meta.get("total") or len(data.get("items", []))
    print(f"✅ 报告已生成: {output_path}")
    print(f"   关键词: {meta.get('keyword','未知')} | 总条数: {total}")
    print(f"   时间范围: {meta.get('time_range','')}")


def main():
    parser = argparse.ArgumentParser(description="生成舆情监控 HTML 报告")
    parser.add_argument("--input",    "-i", required=True, help="输入 JSON 数据文件路径")
    parser.add_argument("--output",   "-o", required=True, help="输出 HTML 报告路径")
    parser.add_argument("--template", "-t", default=None,  help="自定义模板路径（可选）")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ 输入文件不存在: {args.input}")
        sys.exit(1)

    generate_report(args.input, args.output, args.template)


if __name__ == "__main__":
    main()
