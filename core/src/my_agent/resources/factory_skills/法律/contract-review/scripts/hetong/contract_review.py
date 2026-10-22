







import json
import re
import sys
import argparse
from typing import Dict, List, Optional, Any
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.clause_extraction import ClauseExtractor
from scripts.risk_detection import RiskDetector
from scripts.compliance_check import ComplianceChecker
from scripts.report_generator import ReportGenerator


class ContractReviewer:

    
    def __init__(self, contract_type: Optional[str] = None):
        self.contract_type = contract_type
        self.clause_extractor = ClauseExtractor()
        self.risk_detector = RiskDetector()
        self.compliance_checker = ComplianceChecker()
        self.report_generator = ReportGenerator()
        
    def review(self, contract_text: str) -> Dict[str, Any]:









        result = {
            "status": "success",
            "phases": {}
        }
        
        
        if not self.contract_type:
            self.contract_type = self._identify_contract_type(contract_text)
        result["contract_type"] = self.contract_type
        
        
        clauses = self.clause_extractor.extract(contract_text, self.contract_type)
        result["phases"]["clause_extraction"] = clauses
        
        
        risks = self.risk_detector.detect(clauses, self.contract_type)
        result["phases"]["risk_detection"] = risks
        
        
        compliance = self.compliance_checker.check(contract_text, clauses, self.contract_type)
        result["phases"]["compliance_check"] = compliance
        
        
        result["overall_rating"] = self._calculate_overall_rating(risks, compliance)
        result["risks_summary"] = self._summarize_risks(risks)
        result["compliance_summary"] = self._summarize_compliance(compliance)
        
        return result
    
    def _identify_contract_type(self, text: str) -> str:

        
        type_patterns = {
            "劳动合同": ["劳动合同", "甲方", "乙方", "工作内容", "劳动报酬", "社会保险"],
            "买卖合同": ["买卖", "买方", "卖方", "标的物", "货款", "交货"],
            "租赁合同": ["租赁", "出租方", "承租方", "租金", "租赁物", "押金"],
            "服务合同": ["服务", "委托", "受托", "服务费", "服务内容"],
            "借款合同": ["借款", "借款人", "出借人", "借款金额", "利率", "还款"],
            "技术合同": ["技术", "开发", "转让", "许可", "知识产权", "成果"]
        }
        
        scores = {}
        for contract_type, keywords in type_patterns.items():
            score = sum(1 for kw in keywords if kw in text)
            scores[contract_type] = score
        
        
        max_type = max(scores, key=scores.get)
        if scores[max_type] > 0:
            return max_type
        return "未知类型合同"
    
    def _calculate_overall_rating(self, risks: Dict, compliance: Dict) -> str:

        high_risk_count = len(risks.get("high_risk", []))
        medium_risk_count = len(risks.get("medium_risk", []))
        compliance_issues = len(compliance.get("issues", []))
        
        
        if high_risk_count > 0 or compliance_issues > 2:
            return "高危"
        elif medium_risk_count > 0 or compliance_issues > 0:
            return "中危"
        else:
            return "低危"
    
    def _summarize_risks(self, risks: Dict) -> Dict:

        return {
            "high_risk_count": len(risks.get("high_risk", [])),
            "medium_risk_count": len(risks.get("medium_risk", [])),
            "low_risk_count": len(risks.get("low_risk", [])),
            "total_risk_count": len(risks.get("high_risk", [])) + 
                              len(risks.get("medium_risk", [])) + 
                              len(risks.get("low_risk", []))
        }
    
    def _summarize_compliance(self, compliance: Dict) -> Dict:

        return {
            "total_issues": len(compliance.get("issues", [])),
            "mandatory_violations": len(compliance.get("mandatory_violations", [])),
            "format_clause_issues": len(compliance.get("format_clause_issues", [])),
            "pending_validity": len(compliance.get("pending_validity", []))
        }
    
    def generate_report(self, result: Dict, output_path: Optional[str] = None) -> str:










        return self.report_generator.generate(result, output_path)


def parse_arguments():

    parser = argparse.ArgumentParser(
        description="合同智能审查工具 - 智能识别合同类型、提取条款、检测风险、检查合规性"
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        help="合同文本内容或文件路径"
    )
    parser.add_argument(
        "--type", "-t",
        type=str,
        choices=["劳动合同", "买卖合同", "租赁合同", "服务合同", "借款合同", "技术合同", "auto"],
        default="auto",
        help="合同类型（auto表示自动识别）"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        help="输出报告文件路径（可选）"
    )
    parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["json", "markdown", "text"],
        default="markdown",
        help="输出格式"
    )
    parser.add_argument(
        "--file",
        type=str,
        help="从文件读取合同内容"
    )
    return parser.parse_args()


def main():

    args = parse_arguments()
    
    
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            contract_text = f.read()
    elif args.input:
        contract_text = args.input
    else:
        print("错误：请提供合同文本内容（--input）或合同文件路径（--file）")
        sys.exit(1)
    
    
    contract_type = None if args.type == "auto" else args.type
    
    
    print("🔍 合同智能审查系统启动...")
    print(f"📄 合同类型：{'自动识别中' if contract_type is None else contract_type}")
    
    reviewer = ContractReviewer(contract_type)
    
    print("⏳ 正在进行条款提取...")
    print("⏳ 正在进行风险检测...")
    print("⏳ 正在进行合规检查...")
    
    result = reviewer.review(contract_text)
    
    
    print("⏳ 正在生成审查报告...")
    report = reviewer.generate_report(result, args.output)
    
    
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(report)
    
    
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n✅ 报告已保存至：{args.output}")
    
    return result


if __name__ == "__main__":
    main()
