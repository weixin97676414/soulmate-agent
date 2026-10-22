import sys
import json
import os
from pathlib import Path

def parse_resume_text(text):

    
    prompt = f"""
请将以下简历文本解析为标准JSON格式，严格遵循以下结构：
{{
  "basic_info": {{
    "name": "",
    "phone": "",
    "email": "",
    "age": null,
    "gender": "",
    "location": "",
    "work_years": null
  }},
  "education": [
    {{
      "school": "",
      "major": "",
      "degree": "",
      "start_date": "",
      "end_date": "",
      "gpa": "",
      "courses": []
    }}
  ],
  "work_experience": [
    {{
      "company": "",
      "position": "",
      "start_date": "",
      "end_date": "",
      "description": "",
      "achievements": [],
      "technologies": []
    }}
  ],
  "projects": [
    {{
      "name": "",
      "role": "",
      "start_date": "",
      "end_date": "",
      "description": "",
      "technologies": [],
      "achievements": []
    }}
  ],
  "skills": {{
    "technical": [],
    "soft": [],
    "languages": []
  }},
  "certificates": [],
  "awards": [],
  "self_assessment": ""
}}

要求：
1. 只返回JSON，不要任何解释性文字
2. 信息缺失的字段留空或null，不要编造
3. 日期格式统一为"YYYY-MM"，如果只有年份就填"YYYY"
4. 所有提取的信息必须完全来自简历文本，不要添加外部信息
5. 技术栈和成果尽量拆分为数组项，不要合并成大段文字

简历文本：
{text}
"""
    
    
    try:
        
        
        return {
            "status": "success",
            "prompt": prompt,
            "note": "请将上述提示词传入大模型获取结构化JSON结果"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python parse_resume.py <extracted-text-file>")
        sys.exit(1)
    
    text_file = sys.argv[1]
    try:
        with open(text_file, 'r', encoding='utf-8') as f:
            text = f.read()
        result = parse_resume_text(text)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))
