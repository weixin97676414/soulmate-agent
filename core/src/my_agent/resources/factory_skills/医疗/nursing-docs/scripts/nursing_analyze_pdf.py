#!/usr/bin/env python3
# -*- coding: utf-8 -*-











import argparse
import json
import os
import re
import sys


def extract_pdf_text(pdf_path):

    try:
        import pdfplumber
        text_pages = []
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                if page_text:
                    text_pages.append(f"=== 第{i+1}页 ===\n{page_text}")
        full_text = "\n".join(text_pages)
        print(f"[INFO] PDF提取完成，共 {len(text_pages)} 页，{len(full_text)} 字符")
        return full_text
    except ImportError:
        print("[WARN] pdfplumber未安装，尝试安装...")
        os.system(
            '~/.skill-runtime/binaries/python/envs/default/Scripts/pip.exe '
            'install pdfplumber -q'
        )
        import pdfplumber
        text_pages = []
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                if page_text:
                    text_pages.append(f"=== 第{i+1}页 ===\n{page_text}")
        return "\n".join(text_pages)
    except Exception as e:
        print(f"[ERROR] PDF提取失败: {e}")
        return ""


def rule_based_extract(text, standard_name=""):

    
    def extract_section(text, patterns, max_chars=2000):

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                start = match.start()
                
                next_section = re.search(
                    r'\n\d+[\s\.、]+[^\n]{2,20}\n', 
                    text[start+len(match.group()):start+max_chars]
                )
                end = start + (next_section.start() if next_section else max_chars)
                return text[start:end].strip()
        return ""
    
    result = {
        "standard_name": standard_name,
        "nursing_assessment": "",
        "indications": [],
        "contraindications": [],
        "preparations": {
            "drugs": "",
            "equipment": "",
            "patient_prep": "",
            "environment_prep": ""
        },
        "operation_key_points": "",
        "complications": [],
        "intervention_measures": "",
        "precautions": ""
    }
    
    
    assessment_text = extract_section(text, [
        r'护理评估[^\n]*\n', r'评估[^\n]*\n', r'4[\s\.]+护理评估',
        r'一[、．].*评估', r'assessment'
    ])
    result["nursing_assessment"] = assessment_text[:800] if assessment_text else "参见标准文件第三章护理评估部分"
    
    
    indications_text = extract_section(text, [
        r'适应[症证][^\n]*\n', r'适用范围[^\n]*\n', r'indication',
        r'2[\s\.]+适应', r'3[\s\.]+适应'
    ])
    if indications_text:
        items = re.findall(r'[a-zA-Z\d\u4e00-\u9fff][）\)、]([^\n]{5,100})', indications_text)
        result["indications"] = items[:10] if items else [indications_text[:200]]
    
    
    contra_text = extract_section(text, [
        r'禁忌[症证][^\n]*\n', r'contraindication', r'禁忌[^\n]*\n'
    ])
    if contra_text:
        items = re.findall(r'[a-zA-Z\d\u4e00-\u9fff][）\)、]([^\n]{5,100})', contra_text)
        result["contraindications"] = items[:10] if items else [contra_text[:200]]
    
    
    prep_text = extract_section(text, [
        r'用物准备[^\n]*\n', r'操作准备[^\n]*\n', r'准备[^\n]*\n',
        r'物品准备[^\n]*\n', r'器械准备[^\n]*\n'
    ])
    if prep_text:
        
        drug_match = re.search(r'药物[^\n]{0,200}', prep_text)
        result["preparations"]["drugs"] = drug_match.group(0) if drug_match else ""
        
        equip_match = re.search(r'(器械|仪器|设备|物品)[^\n]{0,300}', prep_text)
        result["preparations"]["equipment"] = equip_match.group(0)[:300] if equip_match else prep_text[:300]
        
        patient_match = re.search(r'患者准备[^\n]{0,200}', prep_text)
        result["preparations"]["patient_prep"] = patient_match.group(0) if patient_match else ""
    
    
    op_text = extract_section(text, [
        r'操作要点[^\n]*\n', r'操作步骤[^\n]*\n', r'护理操作[^\n]*\n',
        r'实施[^\n]*\n', r'操作程序[^\n]*\n'
    ], max_chars=3000)
    result["operation_key_points"] = op_text[:1500] if op_text else "参见标准文件操作步骤章节"
    
    
    comp_text = extract_section(text, [
        r'并发症[^\n]*\n', r'complication', r'不良反应[^\n]*\n'
    ])
    if comp_text:
        items = re.findall(r'[a-zA-Z\d\u4e00-\u9fff][）\)、]([^\n]{3,60})', comp_text)
        result["complications"] = items[:10] if items else [comp_text[:200]]
    
    
    intervention_text = extract_section(text, [
        r'干预[^\n]*\n', r'处理[^\n]*\n', r'应急处理[^\n]*\n',
        r'并发症.*处理', r'注意事项[^\n]*\n'
    ], max_chars=2000)
    result["intervention_measures"] = intervention_text[:1000] if intervention_text else ""
    
    
    precaution_text = extract_section(text, [
        r'注意事项[^\n]*\n', r'注意[^\n]*\n', r'precaution'
    ])
    result["precautions"] = precaution_text[:500] if precaution_text else ""
    
    return result


def analyze_multiple_standards(pdf_paths_or_texts, standard_names, diagnosis=""):










    results = []
    
    for i, item in enumerate(pdf_paths_or_texts):
        std_name = standard_names[i] if i < len(standard_names) else f"标准{i+1}"
        print(f"\n[INFO] 分析标准 {i+1}/{len(pdf_paths_or_texts)}: {std_name}")
        
        
        if isinstance(item, str) and item.endswith('.pdf') and os.path.exists(item):
            text = extract_pdf_text(item)
        else:
            text = item  
        
        
        result = None
        if text:
            result = rule_based_extract(text, std_name)
        
        if not result or not any([result.get("nursing_assessment"), result.get("indications")]):
            result = generate_standard_template(std_name, diagnosis)
        
        result["standard_name"] = std_name
        results.append(result)
    
    return results


def extract_complications_detailed(text, standard_name=""):







    result = {
        "standard_name": standard_name,
        "complications": [],
        "prevention": "",
        "emergency_handling": ""
    }
    
    
    comp_section = ""
    lines = text.split('\n')
    in_complication_section = False
    complication_keywords = ['并发症', '不良反应', '风险因素', '并发症及处理']
    
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        
        
        if any(kw in line_stripped for kw in complication_keywords):
            in_complication_section = True
            comp_section += line + '\n'
            continue
        
        
        if in_complication_section:
            if re.match(r'^\d+[\.、]', line_stripped) and len(line_stripped) < 50:
                
                if not any(kw in line_stripped for kw in complication_keywords):
                    in_complication_section = False
            else:
                comp_section += line + '\n'
    
    
    if not comp_section:
        comp_match = re.search(r'(并发症|不良反应|风险因素)[^\n]*\n(.*?)(?=\n\d+[\.、]|$)', text, re.DOTALL)
        if comp_match:
            comp_section = comp_match.group(0)
    
    
    if comp_section:
        
        comp_items = re.findall(r'[a-zA-Z\d\u4e00-\u9fff][）\)、\.．]([^\n]{3,60})', comp_section)
        if comp_items:
            result["complications"] = [item.strip() for item in comp_items]
        else:
            
            for line in comp_section.split('\n'):
                line = line.strip()
                if len(line) >= 3 and len(line) <= 60 and not line.startswith('#'):
                    result["complications"].append(line)
        
        
        prevention_match = re.search(r'预防[^\n]*\n(.*?)(?=\n\d+[\.、]|$)', comp_section, re.DOTALL)
        if prevention_match:
            result["prevention"] = prevention_match.group(1).strip()[:500]
        
        
        emergency_match = re.search(r'应急[^\n]*\n(.*?)(?=\n\d+[\.、]|$)', comp_section, re.DOTALL)
        if emergency_match:
            result["emergency_handling"] = emergency_match.group(1).strip()[:500]
    
    return result


def generate_standard_template(standard_name, diagnosis):

    
    
    templates = {
        "气管切开": {
            "nursing_assessment": "1.评估患者意识状态、呼吸功能、气道分泌物情况\n2.评估气管切开切口愈合情况\n3.评估气道通畅性\n4.评估套管固定情况（松紧度以容纳1-2指为宜）",
            "indications": ["气管切开术后患者", "需要长期气道管理者", "上气道梗阻需要气道维护者"],
            "contraindications": ["无绝对禁忌症", "凝血功能障碍需慎重操作"],
            "equipment": "吸痰管（型号适当）、无菌手套、无菌生理盐水、湿化装置、气管切开护理包、吸氧装置",
            "operation_key_points": "1.核对患者身份\n2.评估气道分泌物\n3.采用无菌技术进行气道吸引\n4.维护气管造瘘口清洁\n5.保持气道湿化",
            "complications": ["气道堵塞", "皮下气肿", "出血", "感染", "套管脱出"],
        },
        "氧气吸入": {
            "nursing_assessment": "1.评估患者呼吸频率、节律、深度\n2.SpO2监测\n3.评估意识状态\n4.评估吸氧装置通畅性",
            "indications": ["低氧血症（SpO2<95%）", "呼吸困难", "心肺功能不全"],
            "contraindications": ["面部创伤（面罩禁忌）"],
            "equipment": "氧气流量计、鼻导管或面罩、湿化瓶、蒸馏水",
            "operation_key_points": "1.核对医嘱（氧流量、吸氧方式）\n2.检查吸氧装置\n3.清洁鼻腔\n4.正确连接并固定\n5.记录开始时间",
            "complications": ["氧中毒", "气道干燥", "皮肤压力性损伤（面罩使用）"],
        },
    }
    
    
    matched_template = None
    for key, tmpl in templates.items():
        if key in standard_name or key in diagnosis:
            matched_template = tmpl
            break
    
    if not matched_template:
        matched_template = templates["氧气吸入"]  
    
    return {
        "standard_name": standard_name,
        "standard_code": "参见标准文件",
        "nursing_assessment": matched_template.get("nursing_assessment", ""),
        "indications": matched_template.get("indications", []),
        "contraindications": matched_template.get("contraindications", []),
        "preparations": {
            "drugs": matched_template.get("drugs", "遵医嘱准备相关药物"),
            "equipment": matched_template.get("equipment", "参见标准文件用物准备章节"),
            "patient_prep": "向患者及家属解释操作目的、方法及配合要点",
            "environment_prep": "清洁、安静、光线充足，温湿度适宜"
        },
        "operation_key_points": matched_template.get("operation_key_points", "参见标准文件操作步骤"),
        "complications": matched_template.get("complications", []),
        "intervention_measures": "发现并发症时立即停止操作，评估患者状态，必要时通知医生",
        "precautions": "严格执行无菌操作原则；操作前核查患者身份；操作后记录"
    }


def main():
    parser = argparse.ArgumentParser(description="护理操作PDF结构化分析")
    parser.add_argument("--pdf_path", help="PDF文件路径（单个）")
    parser.add_argument("--pdf_paths", nargs='+', help="PDF文件路径列表（多个）")
    parser.add_argument("--text_input", help="直接输入文本（替代PDF）")
    parser.add_argument("--standard_name", default="", help="标准名称（单个）")
    parser.add_argument("--standard_names", nargs='+', help="标准名称列表（多个）")
    parser.add_argument("--diagnosis", default="", help="患者诊断（辅助分析）")
    parser.add_argument("--output", default="", help="输出JSON文件路径")
    parser.add_argument("--output_dir", default="", help="输出目录（用于多个结果）")
    parser.add_argument("--extract_complications", action="store_true", help="详细提取并发症及处理措施")
    args = parser.parse_args()
    
    
    if args.extract_complications and args.pdf_path:
        print(f"[INFO] 详细提取并发症: {args.pdf_path}")
        text = extract_pdf_text(args.pdf_path)
        result = extract_complications_detailed(text, args.standard_name)
        
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"[DONE] 并发症分析结果已保存: {args.output}")
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    
    
    if args.pdf_paths:
        print(f"[INFO] 分析多个标准，共 {len(args.pdf_paths)} 个")
        standard_names = args.standard_names if args.standard_names else [f"标准{i+1}" for i in range(len(args.pdf_paths))]
        
        results = analyze_multiple_standards(
            args.pdf_paths,
            standard_names,
            diagnosis=args.diagnosis
        )
        
        
        if args.output_dir:
            os.makedirs(args.output_dir, exist_ok=True)
            for i, result in enumerate(results):
                output_path = os.path.join(args.output_dir, f"analysis_{i+1}.json")
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                print(f"[DONE] 分析结果 {i+1} 已保存: {output_path}")
            
            
            merged_path = os.path.join(args.output_dir, "analysis_merged.json")
            with open(merged_path, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"[DONE] 合并结果已保存: {merged_path}")
        elif args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"[DONE] 分析结果已保存: {args.output}")
        else:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        
        return
    
    
    text = ""
    if args.pdf_path and os.path.exists(args.pdf_path):
        print(f"[INFO] 提取PDF: {args.pdf_path}")
        text = extract_pdf_text(args.pdf_path)
    elif args.text_input:
        text = args.text_input
        print(f"[INFO] 使用输入文本，{len(text)} 字符")
    
    
    result = None
    if text:
        print("[INFO] 使用规则提取...")
        result = rule_based_extract(text, args.standard_name)
    
    if not result or not any([result.get("nursing_assessment"), result.get("indications")]):
        print("[INFO] 生成标准化模板...")
        result = generate_standard_template(args.standard_name, args.diagnosis)
    
    
    if args.standard_name:
        result["standard_name"] = args.standard_name
    
    
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"[DONE] 分析结果已保存: {args.output}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    return result


if __name__ == "__main__":
    main()
