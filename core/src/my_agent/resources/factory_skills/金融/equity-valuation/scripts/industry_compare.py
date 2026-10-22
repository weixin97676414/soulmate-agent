#!/usr/bin/env python3
# -*- coding: utf-8 -*-












import akshare as ak
import pandas as pd
import argparse
import json
import sys
from datetime import datetime




INDUSTRY_MAPPING = {
    
    "000858": "白酒",  
    "000568": "白酒",  
    "600519": "白酒",  
    "000596": "白酒",  
    "600809": "白酒",  
    
    
    "600036": "银行",  
    "601398": "银行",  
    "601288": "银行",  
    "601939": "银行",  
    "600016": "银行",  
    
    
    "601318": "保险",  
    "601628": "保险",  
    "601336": "保险",  
    "601601": "保险",  
}


def get_industry_stocks(industry_name):






    stocks = []
    for code, industry in INDUSTRY_MAPPING.items():
        if industry == industry_name:
            stocks.append(code)
    return stocks


def get_stock_valuation_batch(stock_codes):






    try:
        df = ak.stock_zh_a_spot_em()
        
        
        filtered = df[df['代码'].isin(stock_codes)]
        
        result = []
        for _, row in filtered.iterrows():
            result.append({
                "code": row['代码'],
                "name": row['名称'],
                "price": float(row['最新价']) if pd.notna(row['最新价']) else None,
                "pe_ttm": float(row['市盈率-动态']) if pd.notna(row['市盈率-动态']) else None,
                "pb": float(row['市净率']) if pd.notna(row['市净率']) else None,
                "market_cap": float(row['总市值']) / 1e8 if pd.notna(row['总市值']) else None,
                "dividend_yield": float(row['股息率']) if pd.notna(row['股息率']) else None
            })
        
        return pd.DataFrame(result)
    except Exception as e:
        print(f"获取估值数据失败: {e}", file=sys.stderr)
        return None


def analyze_industry_valuation(df, target_code=None):










    if df is None or len(df) == 0:
        return None
    
    
    pe_valid = df[df['pe_ttm'].notna() & (df['pe_ttm'] > 0) & (df['pe_ttm'] < 100)]
    pb_valid = df[df['pb'].notna() & (df['pb'] > 0) & (df['pb'] < 20)]
    
    analysis = {
        "sample_size": len(df),
        "pe_analysis": {
            "median": pe_valid['pe_ttm'].median() if len(pe_valid) > 0 else None,
            "mean": pe_valid['pe_ttm'].mean() if len(pe_valid) > 0 else None,
            "min": pe_valid['pe_ttm'].min() if len(pe_valid) > 0 else None,
            "max": pe_valid['pe_ttm'].max() if len(pe_valid) > 0 else None,
            "25th": pe_valid['pe_ttm'].quantile(0.25) if len(pe_valid) > 0 else None,
            "75th": pe_valid['pe_ttm'].quantile(0.75) if len(pe_valid) > 0 else None
        },
        "pb_analysis": {
            "median": pb_valid['pb'].median() if len(pb_valid) > 0 else None,
            "mean": pb_valid['pb'].mean() if len(pb_valid) > 0 else None,
            "min": pb_valid['pb'].min() if len(pb_valid) > 0 else None,
            "max": pb_valid['pb'].max() if len(pb_valid) > 0 else None
        }
    }
    
    
    if target_code:
        target = df[df['code'] == target_code]
        if len(target) > 0:
            target_row = target.iloc[0]
            analysis["target"] = {
                "code": target_code,
                "name": target_row['name'],
                "pe": target_row['pe_ttm'],
                "pb": target_row['pb'],
                "market_cap": target_row['market_cap']
            }
            
            
            if target_row['pe_ttm'] and analysis["pe_analysis"]["median"]:
                pe_vs_median = (target_row['pe_ttm'] / analysis["pe_analysis"]["median"] - 1) * 100
                analysis["target"]["pe_vs_median"] = f"{pe_vs_median:+.1f}%"
            
            if target_row['pb'] and analysis["pb_analysis"]["median"]:
                pb_vs_median = (target_row['pb'] / analysis["pb_analysis"]["median"] - 1) * 100
                analysis["target"]["pb_vs_median"] = f"{pb_vs_median:+.1f}%"
    
    return analysis


def format_comparison_report(analysis, industry_name=""):



    if analysis is None:
        return "无法生成报告"
    
    title = f"{industry_name}行业估值对比" if industry_name else "行业估值对比"
    
    report = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏭 {title}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

样本数量: {analysis['sample_size']} 家公司

📊 PE-TTM 分布
  中位数: {analysis['pe_analysis']['median']:.2f}x
  平均值: {analysis['pe_analysis']['mean']:.2f}x
  25%分位: {analysis['pe_analysis']['25th']:.2f}x
  75%分位: {analysis['pe_analysis']['75th']:.2f}x
  区间: {analysis['pe_analysis']['min']:.2f}x - {analysis['pe_analysis']['max']:.2f}x

📊 PB 分布
  中位数: {analysis['pb_analysis']['median']:.2f}x
  平均值: {analysis['pb_analysis']['mean']:.2f}x
  区间: {analysis['pb_analysis']['min']:.2f}x - {analysis['pb_analysis']['max']:.2f}x
"""
    
    if "target" in analysis:
        t = analysis["target"]
        report += f"""
🎯 目标公司对比: {t['name']} ({t['code']})
  PE-TTM: {t['pe']:.2f}x ({t.get('pe_vs_median', 'N/A')} vs 行业中位数)
  PB: {t['pb']:.2f}x ({t.get('pb_vs_median', 'N/A')} vs 行业中位数)
  市值: {t['market_cap']:.2f} 亿元
"""
    
    report += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    return report


def main():
    parser = argparse.ArgumentParser(description='同行业估值对比工具')
    parser.add_argument('--stock', help='目标股票代码（用于在行业中定位）')
    parser.add_argument('--industry', help='行业名称（如 白酒、银行等）')
    parser.add_argument('--codes', help='股票代码列表，逗号分隔（直接指定对比标的）')
    
    args = parser.parse_args()
    
    
    if args.codes:
        stock_codes = [c.strip() for c in args.codes.split(',')]
        industry_name = "自定义"
    elif args.industry:
        stock_codes = get_industry_stocks(args.industry)
        industry_name = args.industry
    elif args.stock:
        
        industry = INDUSTRY_MAPPING.get(args.stock)
        if industry:
            stock_codes = get_industry_stocks(industry)
            industry_name = industry
        else:
            print(f"股票 {args.stock} 的行业分类未知，请使用 --codes 直接指定对比标的", file=sys.stderr)
            sys.exit(1)
    else:
        print("请提供 --stock、--industry 或 --codes 参数", file=sys.stderr)
        sys.exit(1)
    
    if len(stock_codes) < 2:
        print("对比样本不足，请提供更多股票代码", file=sys.stderr)
        sys.exit(1)
    
    
    df = get_stock_valuation_batch(stock_codes)
    
    if df is None or len(df) == 0:
        print("无法获取估值数据", file=sys.stderr)
        sys.exit(1)
    
    
    analysis = analyze_industry_valuation(df, args.stock)
    
    
    report = format_comparison_report(analysis, industry_name)
    print(report)
    
    
    output = {
        "analysis": analysis,
        "raw_data": df.to_dict('records'),
        "timestamp": datetime.now().isoformat()
    }
    
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str), file=sys.stderr)


if __name__ == "__main__":
    main()
