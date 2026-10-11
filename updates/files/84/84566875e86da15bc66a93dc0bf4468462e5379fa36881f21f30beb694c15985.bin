#!/usr/bin/env python3
"""数据库初始化 - Initialize Database"""
import sys
import os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(__file__))
from db import init_database, DB_PATH

print("正在初始化数据库...")
print(f"数据库路径: {DB_PATH}")

init_database()

print("[OK] 数据库初始化完成!")
print(f"   数据库文件: {DB_PATH}")
print(f"   已创建表: articles, questions, fetch_logs")
