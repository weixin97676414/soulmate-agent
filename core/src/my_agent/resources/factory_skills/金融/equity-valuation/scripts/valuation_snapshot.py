#!/usr/bin/env python3
# -*- coding: utf-8 -*-













import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import sys
import argparse


INDEX_MAPPING = {
    "000300": "sh000300",  
    "000016": "sh000016",  
    "000905": "sh000905",  
    "399006": "sz399006",  
    "000688": "sh000688",  
    "HSI": "hkHSI",        
    "HSTECH": "hkHSTECH",  
}


def get_stock_valuation(stock_code, market="A"):










    try:
        if market == "A":
            
            df = ak.stock_zh_a_spot_em()
            stock_row = df[df['代码'] == stock_code]
            if len(stock_row) == 0:
                return None
            
            row = stock_row.iloc[0]
            return {
                "code": stock_code,
                "name": row['名称'],
                "price": float(row['最新价']) if pd.notna(row['最新价']) else None,
                "pe_ttm": float(row['市盈率-动态']) if pd.notna(row['市盈率-动态']) else None,
                "pb": float(row['市净率']) if pd.notna(row['市净率']) else None,
                "ps_ttm": None,  
                "dividend_yield": float(row['股息率']) if pd.notna(row['股息率']) else None,
                "market_cap": float(row['总市值']) / 1e8 if pd.notna(row['总市值']) else None,  
                "market": "A股"
            }
        else:
            
            df = ak.stock_hk_ggt_components_em()
            stock_row = df[df['代码'].str.contains(stock_code)]
            if len(stock_row) == 0:
                return None
            
            row = stock_row.iloc[0]
            return {
                "code": stock_code,
                "name": row['名称'],
                "price": float(row['最新价']) if pd.notna(row['最新价']) else None,
                "pe_ttm": float(row['市盈率']) if pd.notna(row['市盈率']) else None,
                "pb": None,  
                "ps_ttm": None,
                "dividend_yield": None,
                "market_cap": None,
                "market": "港股"
            }
    except Exception as e:
        print(f"获取估值数据失败: {e}", file=sys.stderr)
        return None


def get_historical_valuation(stock_code, years=10):






    try:
        
        
        
        
        
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=365*years)).strftime("%Y%m%d")
        
        df = ak.stock_zh_a_hist(symbol=stock_code, period="daily", 
                                start_date=start_date, end_date=end_date)
        
        if df is None or len(df) == 0:
            return None
        
        
        df['收盘'] = pd.to_numeric(df['收盘'], errors='coerce')
        return df
    except Exception as e:
        print(f"获取历史数据失败: {e}", file=sys.stderr)
        return None


def calculate_percentile(current_value, historical_values):










    if historical_values is None or len(historical_values) == 0:
        return None
    
    historical_values = np.array(historical_values)
    historical_values = historical_values[~np.isnan(historical_values)]
    
    if len(historical_values) == 0:
        return None
    
    percentile = (historical_values <= current_value).mean() * 100
    return percentile


def get_industry_valuation(stock_code):






    try:
        
        df = ak.stock_zh_a_spot_em()
        
        
        
        pe_median = df['市盈率-动态'].median()
        pb_median = df['市净率'].median()
        
        return {
            "market_pe_median": float(pe_median) if pd.notna(pe_median) else None,
            "market_pb_median": float(pb_median) if pd.notna(pb_median) else None,
            "note": "全市场中位数（行业数据需要更细分的分类接口）"
        }
    except Exception as e:
        print(f"获取行业估值失败: {e}", file=sys.stderr)
        return None


def format_valuation_report(valuation_data, percentiles=None, industry_data=None):



    if valuation_data is None:
        return "无法获取估值数据"
    
    report = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 估值分析报告 - {valuation_data['name']} ({valuation_data['code']})
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💰 基础数据
  当前价格: {valuation_data['price']:.2f} 元
  总市值: {valuation_data['market_cap']:.2f} 亿元
  市场: {valuation_data['market']}

📈 估值指标
"""
    
    if valuation_data['pe_ttm']:
        report += f"  PE-TTM: {valuation_data['pe_ttm']:.2f}x"
        if percentiles and 'pe' in percentiles:
            report += f" (历史{percentiles['pe']:.0f}%分位)"
        report += "\n"
    
    if valuation_data['pb']:
        report += f"  PB: {valuation_data['pb']:.2f}x"
        if percentiles and 'pb' in percentiles:
            report += f" (历史{percentiles['pb']:.0f}%分位)"
        report += "\n"
    
    if valuation_data['dividend_yield']:
        report += f"  股息率: {valuation_data['dividend_yield']:.2f}%\n"
    
    if industry_data:
        report += f"""
🏭 行业对比
  全市场 PE 中位数: {industry_data['market_pe_median']:.2f}x
  全市场 PB 中位数: {industry_data['market_pb_median']:.2f}x
  {industry_data['note']}
"""
    
    report += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    return report


def main():
    parser = argparse.ArgumentParser(description='股票估值分析工具')
    parser.add_argument('stock_code', help='股票代码 (如 000858)')
    parser.add_argument('--market', choices=['A', 'HK'], default='A', help='市场 (A 或 HK)')
    parser.add_argument('--history-years', type=int, default=10, help='历史数据年限')
    
    args = parser.parse_args()
    
    
    valuation = get_stock_valuation(args.stock_code, args.market)
    
    if valuation is None:
        print(f"无法获取股票 {args.stock_code} 的数据", file=sys.stderr)
        sys.exit(1)
    
    
    hist_data = get_historical_valuation(args.stock_code, args.history_years)
    percentiles = {}
    
    if hist_data is not None:
        
        if valuation['price']:
            percentiles['price'] = calculate_percentile(
                valuation['price'], 
                hist_data['收盘'].values
            )
    
    
    industry = get_industry_valuation(args.stock_code)
    
    
    report = format_valuation_report(valuation, percentiles, industry)
    print(report)
    
    
    result = {
        "valuation": valuation,
        "percentiles": percentiles,
        "industry": industry,
        "timestamp": datetime.now().isoformat()
    }
    
    
    print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)


if __name__ == "__main__":
    main()
