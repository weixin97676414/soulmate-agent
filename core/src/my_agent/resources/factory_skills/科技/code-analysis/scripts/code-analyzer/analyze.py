#!/usr/bin/env python3





import os
import sys
import ast
import json
import argparse
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Any
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
import re






@dataclass
class FunctionInfo:

    name: str
    file: str
    line_start: int
    line_end: int
    parameters: List[str]
    return_type: str
    calls: List[str] = field(default_factory=list)  
    called_by: List[str] = field(default_factory=list)  
    complexity: int = 1
    is_entry_point: bool = False
    business_logic: bool = False


@dataclass
class DataModel:

    name: str
    type: str  
    file: str
    fields: List[Dict] = field(default_factory=list)
    methods: List[str] = field(default_factory=list)
    relationships: List[str] = field(default_factory=list)  
    is_entity: bool = False  
    is_value_object: bool = False
    is_dto: bool = False


@dataclass
class BusinessRule:

    id: str
    description: str
    location: str  
    rule_type: str  
    conditions: List[str] = field(default_factory=list)
    outcomes: List[str] = field(default_factory=list)
    priority: str = "medium"  


@dataclass
class ExternalDependency:

    name: str
    type: str  
    usage: str  
    endpoints: List[str] = field(default_factory=list)
    critical: bool = False  


@dataclass 
class DataFlow:

    source: str
    destination: str
    data_type: str
    transformation: str
    trigger: str  


@dataclass
class ExecutionPath:

    name: str
    description: str
    entry_point: str
    steps: List[Dict] = field(default_factory=list)
    critical: bool = False


@dataclass
class DeepAnalysisReport:

    timestamp: str = ""
    path: str = ""
    
    
    total_files: int = 0
    total_lines: int = 0
    languages: Dict[str, int] = field(default_factory=dict)
    
    
    entry_points: List[FunctionInfo] = field(default_factory=list)
    functions: List[FunctionInfo] = field(default_factory=list)
    data_models: List[DataModel] = field(default_factory=list)
    business_rules: List[BusinessRule] = field(default_factory=list)
    external_deps: List[ExternalDependency] = field(default_factory=list)
    data_flows: List[DataFlow] = field(default_factory=list)
    execution_paths: List[ExecutionPath] = field(default_factory=list)
    
    
    architecture_style: str = ""
    layers: List[str] = field(default_factory=list)
    modules: List[Dict] = field(default_factory=list)
    
    
    issues: List[Dict] = field(default_factory=list)






class DeepCodeAnalyzer:

    
    def __init__(self, path: str, exclude_patterns: List[str] = None):
        self.root_path = Path(path).resolve()
        self.exclude_patterns = exclude_patterns or [
            'node_modules', 'vendor', '.git', '__pycache__',
            '.venv', 'venv', 'dist', 'build', 'target', '.DS_Store'
        ]
        self.files = []
        self.report = DeepAnalysisReport()
        
        
        self.functions: Dict[str, FunctionInfo] = {}
        self.data_models: Dict[str, DataModel] = {}
        self.business_rules: List[BusinessRule] = []
        self.external_deps: Set[str] = set()
        
    def should_include(self, file_path: Path) -> bool:

        
        try:
            rel_path = str(file_path.relative_to(self.root_path))
        except ValueError:
            
            rel_path = str(file_path)
        
        for pattern in self.exclude_patterns:
            if pattern in rel_path:
                return False
        return file_path.suffix in ['.py', '.js', '.ts', '.java', '.go', '.rs', '.sql']
    
    def discover_files(self) -> List[Path]:

        self.files = []
        if self.root_path.is_file():
            if self.should_include(self.root_path):
                self.files.append(self.root_path)
        else:
            for file_path in self.root_path.rglob('*'):
                if file_path.is_file() and self.should_include(file_path):
                    self.files.append(file_path)
        return self.files
    
    def analyze_python(self, file_path: Path, content: str):

        try:
            tree = ast.parse(content)
            rel_path = str(file_path.relative_to(self.root_path))
            
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    self._analyze_class(node, rel_path, content)
                
                elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                    self._analyze_function(node, rel_path, content)
                
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        self.external_deps.add(alias.name.split('.')[0])
                
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        self.external_deps.add(node.module.split('.')[0])
        
        except SyntaxError as e:
            print(f"  ⚠️  Syntax error in {rel_path}: {e}")
    
    def _analyze_class(self, node: ast.ClassDef, file_path: str, content: str):

        model = DataModel(
            name=node.name,
            type='class',
            file=file_path,
            fields=[],
            methods=[],
            relationships=[]
        )
        
        
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                for arg in item.args.args:
                    if arg.arg != 'self':
                        model.fields.append({'name': arg.arg, 'type': 'unknown'})
            
            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                model.methods.append(item.name)
        
        
        for base in node.bases:
            if isinstance(base, ast.Name):
                model.relationships.append(f'extends {base.id}')
        
        
        class_name_lower = node.name.lower()
        if any(kw in class_name_lower for kw in ['entity', 'model', 'schema', 'record']):
            model.is_entity = True
        elif any(kw in class_name_lower for kw in ['dto', 'request', 'response', 'data']):
            model.is_dto = True
        elif any(kw in class_name_lower for kw in ['value', 'vo']):
            model.is_value_object = True
        
        self.data_models[node.name] = model
    
    def _analyze_function(self, node: ast.FunctionDef, file_path: str, content: str):

        func = FunctionInfo(
            name=node.name,
            file=file_path,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno + 10,
            parameters=[arg.arg for arg in node.args.args if arg.arg != 'self'],
            return_type='unknown',
            calls=[],
            complexity=1
        )
        
        
        if node.name in ['main', 'run', 'execute', 'handle', 'process']:
            func.is_entry_point = True
        
        
        func_keywords = ['calculate', 'validate', 'create', 'update', 'delete', 
                        'process', 'generate', 'verify', 'approve', 'reject']
        if any(kw in node.name.lower() for kw in func_keywords):
            func.business_logic = True
        
        
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    func.calls.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    func.calls.append(child.func.attr)
        
        
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.ExceptHandler)):
                func.complexity += 1
        
        
        self._extract_business_rules(node, file_path, content)
        
        key = f"{file_path}:{node.name}"
        self.functions[key] = func
    
    def _extract_business_rules(self, node: ast.FunctionDef, file_path: str, content: str):

        lines = content.split('\n')
        
        
        for i, child in enumerate(ast.walk(node)):
            if isinstance(child, ast.If):
                
                if_content = '\n'.join(lines[child.lineno-1:child.lineno+5])
                
                if 'if not' in if_content or 'if !' in if_content:
                    rule = BusinessRule(
                        id=f"rule_{len(self.business_rules)+1}",
                        description=f"Validation in {node.name}",
                        location=f"{file_path}:{node.name}",
                        rule_type='validation',
                        conditions=[if_content.strip()[:200]],
                        priority='high' if 'raise' in if_content or 'return False' in if_content else 'medium'
                    )
                    self.business_rules.append(rule)
                
                
                if any(kw in if_content for kw in ['must', 'should', 'required', 'allowed']):
                    rule = BusinessRule(
                        id=f"rule_{len(self.business_rules)+1}",
                        description=f"Business constraint in {node.name}",
                        location=f"{file_path}:{node.name}",
                        rule_type='constraint',
                        conditions=[if_content.strip()[:200]],
                        priority='critical'
                    )
                    self.business_rules.append(rule)
    
    def analyze_javascript(self, file_path: Path, content: str):

        rel_path = str(file_path.relative_to(self.root_path))
        
        
        class_pattern = r'class\s+(\w+)(?:\s+extends\s+(\w+))?'
        for match in re.finditer(class_pattern, content):
            model = DataModel(
                name=match.group(1),
                type='class',
                file=rel_path,
                relationships=[f'extends {match.group(2)}'] if match.group(2) else []
            )
            self.data_models[match.group(1)] = model
        
        
        func_pattern = r'(?:function|const|let)\s+(\w+)\s*=\s*(?:async\s*)?\(([^)]*)\)'
        for match in re.finditer(func_pattern, content):
            func = FunctionInfo(
                name=match.group(1),
                file=rel_path,
                line_start=content[:match.start()].count('\n'),
                line_end=0,
                parameters=[p.strip() for p in match.group(2).split(',') if p.strip()],
                return_type='unknown'
            )
            if func.name in ['main', 'run', 'handle', 'process', 'controller']:
                func.is_entry_point = True
            self.functions[f"{rel_path}:{func.name}"] = func
        
        
        import_pattern = r"(?:import|require)\s*\(?['\"]([^'\"]+)['\"]"
        for match in re.finditer(import_pattern, content):
            dep = match.group(1)
            if not dep.startswith('.'):
                self.external_deps.add(dep.split('/')[0])
    
    def analyze_rust(self, file_path: Path, content: str):

        rel_path = str(file_path.relative_to(self.root_path))
        
        
        struct_pattern = r'(?:pub\s+)?struct\s+(\w+)'
        for match in re.finditer(struct_pattern, content):
            model = DataModel(
                name=match.group(1),
                type='struct',
                file=rel_path,
                is_entity=any(kw in match.group(1).lower() for kw in ['entity', 'model', 'data', 'record'])
            )
            self.data_models[match.group(1)] = model
        
        
        enum_pattern = r'(?:pub\s+)?enum\s+(\w+)'
        for match in re.finditer(enum_pattern, content):
            model = DataModel(
                name=match.group(1),
                type='enum',
                file=rel_path
            )
            self.data_models[match.group(1)] = model
        
        
        func_pattern = r'(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*\(([^)]*)\)'
        for match in re.finditer(func_pattern, content):
            func_name = match.group(1)
            params = match.group(2)
            
            func = FunctionInfo(
                name=func_name,
                file=rel_path,
                line_start=content[:match.start()].count('\n'),
                line_end=0,
                parameters=[p.split(':')[0].strip().replace('&', '').replace('mut ', '') 
                           for p in params.split(',') if p.strip() and p.strip() != 'self' and p.strip() != '&self'],
                return_type='unknown'
            )
            
            
            if func_name in ['main', 'run', 'execute', 'handle', 'process', 'new']:
                func.is_entry_point = True
            
            
            if any(kw in func_name for kw in ['calculate', 'validate', 'create', 'update', 'delete', 'process']):
                func.business_logic = True
            
            self.functions[f"{rel_path}:{func_name}"] = func
        
        
        use_pattern = r'use\s+([^;]+)'
        for match in re.finditer(use_pattern, content):
            deps = match.group(1).split(',')
            for dep in deps:
                dep = dep.strip().split('::')[0]
                if dep and dep not in ['std', 'crate', 'self', 'super']:
                    self.external_deps.add(dep)
        
        
        match_pattern = r'match\s+(\w+)\s*\{([^}]+)\}'
        for match in re.finditer(match_pattern, content):
            expr = match.group(1)
            arms = match.group(2)
            
            
            if any(kw in arms for kw in ['Err', 'None', 'Invalid', 'Error']):
                rule = BusinessRule(
                    id=f"rule_{len(self.business_rules)+1}",
                    description=f"Validation/matching on {expr}",
                    location=f"{rel_path}:match",
                    rule_type='validation',
                    conditions=[arms.strip()[:200]],
                    priority='high'
                )
                self.business_rules.append(rule)
    
    def detect_architecture(self) -> Tuple[str, List[str]]:

        dir_structure = defaultdict(list)
        
        for file_path in self.files:
            rel_path = str(file_path.relative_to(self.root_path))
            parts = rel_path.split(os.sep)
            if len(parts) > 1:
                dir_structure[parts[0]].append(rel_path)
        
        
        architecture_patterns = {
            'MVC': {
                'keywords': ['controller', 'model', 'view', 'controllers', 'models', 'views'],
                'confidence': 0
            },
            'Clean Architecture': {
                'keywords': ['domain', 'application', 'infrastructure', 'presentation', 'entities'],
                'confidence': 0
            },
            'Layered': {
                'keywords': ['api', 'service', 'repository', 'data', 'controller'],
                'confidence': 0
            },
            'Microservices': {
                'keywords': ['service', 'gateway', 'api', 'client', 'grpc', 'rpc'],
                'confidence': 0
            },
            'Hexagonal': {
                'keywords': ['adapter', 'port', 'domain', 'application', 'infrastructure'],
                'confidence': 0
            }
        }
        
        all_dirs = set(dir_structure.keys())
        
        for arch, data in architecture_patterns.items():
            matches = sum(1 for kw in data['keywords'] if kw in all_dirs or kw in str(dir_structure))
            data['confidence'] = matches
        
        
        best_arch = max(architecture_patterns.items(), key=lambda x: x[1]['confidence'])
        
        if best_arch[1]['confidence'] >= 2:
            return best_arch[0], list(dir_structure.keys())
        else:
            return 'Unknown/Mixed', list(dir_structure.keys())
    
    def build_call_graph(self) -> Dict[str, List[str]]:

        graph = defaultdict(list)
        
        for key, func in self.functions.items():
            for call in func.calls:
                graph[key].append(call)
        
        return dict(graph)
    
    def identify_execution_paths(self) -> List[ExecutionPath]:

        paths = []
        
        
        entry_points = [f for f in self.functions.values() if f.is_entry_point]
        
        for entry in entry_points[:5]:  
            path = ExecutionPath(
                name=entry.name,
                description=f"Entry point: {entry.file}",
                entry_point=f"{entry.file}:{entry.name}",
                critical=entry.business_logic,
                steps=[]
            )
            
            
            visited = set()
            to_visit = [entry.name]
            
            while to_visit and len(path.steps) < 10:
                current = to_visit.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                
                path.steps.append({
                    'function': current,
                    'type': 'function_call'
                })
                
                
                for key, func in self.functions.items():
                    if current in func.calls and func.name not in visited:
                        to_visit.append(func.name)
            
            paths.append(path)
        
        return paths
    
    def identify_data_flows(self) -> List[DataFlow]:

        flows = []
        
        
        for key, func in self.functions.items():
            if func.business_logic:
                
                if func.parameters:
                    flows.append(DataFlow(
                        source='external',
                        destination=f"{func.file}:{func.name}",
                        data_type=', '.join(func.parameters),
                        transformation='input_validation',
                        trigger='function_call'
                    ))
                
                
                if func.return_type != 'unknown':
                    flows.append(DataFlow(
                        source=f"{func.file}:{func.name}",
                        destination='external',
                        data_type=func.return_type,
                        transformation='output_formatting',
                        trigger='function_return'
                    ))
        
        return flows
    
    def run(self, output: Optional[str] = None) -> DeepAnalysisReport:

        print(f"🔍 Deep analyzing: {self.root_path}")
        
        
        self.discover_files()
        print(f"📁 Found {len(self.files)} files")
        
        
        for i, file_path in enumerate(self.files, 1):
            if i % 10 == 0:
                print(f"  Processing {i}/{len(self.files)}...")
            
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    
                    ext = file_path.suffix
                    if ext == '.py':
                        self.analyze_python(file_path, content)
                    elif ext in ['.js', '.ts']:
                        self.analyze_javascript(file_path, content)
                    elif ext == '.rs':
                        self.analyze_rust(file_path, content)
            except Exception as e:
                print(f"  ⚠️  Error reading {file_path}: {e}")
        
        
        self.report.timestamp = datetime.now().isoformat()
        self.report.path = str(self.root_path)
        self.report.total_files = len(self.files)
        self.report.total_lines = sum(
            len(open(f, 'r', encoding='utf-8', errors='ignore').read().split('\n'))
            for f in self.files
        )
        
        
        lang_count = defaultdict(int)
        for f in self.files:
            lang_count[f.suffix] += 1
        self.report.languages = dict(lang_count)
        
        
        arch, layers = self.detect_architecture()
        self.report.architecture_style = arch
        self.report.layers = layers
        
        
        self.report.functions = list(self.functions.values())[:50]  
        self.report.data_models = list(self.data_models.values())
        self.report.business_rules = self.business_rules
        self.report.entry_points = [f for f in self.report.functions if f.is_entry_point]
        
        
        for dep in self.external_deps:
            self.report.external_deps.append(ExternalDependency(
                name=dep,
                type='library',
                usage='imported',
                critical=dep in ['requests', 'axios', 'sqlalchemy', 'mongoose']
            ))
        
        
        self.report.execution_paths = self.identify_execution_paths()
        self.report.data_flows = self.identify_data_flows()
        
        print("✅ Deep analysis complete")
        
        
        if output:
            self.export_report(output)
            print(f"📝 Report saved to: {output}")
        
        return self.report
    
    def export_report(self, output_path: str):

        report = self.report
        
        md = []
        
        
        md.append(f"# 🔍 Deep Code Analysis Report\n")
        md.append(f"**Generated:** {report.timestamp}\n")
        md.append(f"**Path:** {report.path}\n")
        
        
        md.append("\n## 📋 Executive Summary\n")
        md.append(f"- **Total Files:** {report.total_files}")
        md.append(f"- **Total Lines:** {report.total_lines:,}")
        md.append(f"- **Architecture Style:** {report.architecture_style}")
        md.append(f"- **Entry Points:** {len(report.entry_points)}")
        md.append(f"- **Data Models:** {len(report.data_models)}")
        md.append(f"- **Business Rules:** {len(report.business_rules)}")
        md.append(f"- **External Dependencies:** {len(report.external_deps)}\n")
        
        
        md.append("\n## 🏗️ Architecture\n")
        md.append(f"**Style:** {report.architecture_style}\n")
        md.append("**Layers/Modules:**\n")
        for layer in report.layers:
            md.append(f"- `{layer}/`")
        
        
        md.append("\n## 🚀 Entry Points & Execution Flow\n")
        for entry in report.entry_points[:5]:
            md.append(f"\n### {entry.name}\n")
            md.append(f"- **Location:** `{entry.file}`")
            md.append(f"- **Parameters:** {', '.join(entry.parameters) if entry.parameters else 'None'}")
            md.append(f"- **Business Logic:** {'✅ Yes' if entry.business_logic else '❌ No'}")
            md.append(f"- **Calls:** {', '.join(entry.calls[:5]) if entry.calls else 'None'}")
        
        
        md.append("\n## 📊 Data Models\n")
        entities = [m for m in report.data_models if m.is_entity]
        dtos = [m for m in report.data_models if m.is_dto]
        
        if entities:
            md.append("\n### Core Entities\n")
            for entity in entities[:10]:
                md.append(f"\n**{entity.name}** (`{entity.file}`)\n")
                if entity.fields:
                    md.append("Fields:")
                    for f in entity.fields[:5]:
                        md.append(f"- `{f['name']}`")
                if entity.relationships:
                    md.append(f"Relationships: {', '.join(entity.relationships)}")
        
        if dtos:
            md.append("\n### DTOs/Value Objects\n")
            for dto in dtos[:5]:
                md.append(f"- **{dto.name}** - {dto.file}")
        
        
        md.append("\n## 📜 Business Rules\n")
        if report.business_rules:
            by_type = defaultdict(list)
            for rule in report.business_rules:
                by_type[rule.rule_type].append(rule)
            
            for rule_type, rules in by_type.items():
                md.append(f"\n### {rule_type.title()} Rules ({len(rules)})\n")
                for rule in rules[:5]:
                    md.append(f"**{rule.id}:** {rule.description}\n")
                    md.append(f"- Location: `{rule.location}`")
                    md.append(f"- Priority: {rule.priority}")
                    if rule.conditions:
                        md.append(f"- Condition: `{rule.conditions[0][:100]}...`")
                    md.append("")
        else:
            md.append("\n*No explicit business rules detected. May require manual review.*\n")
        
        
        md.append("\n## 🔗 External Dependencies\n")
        critical_deps = [d for d in report.external_deps if d.critical]
        other_deps = [d for d in report.external_deps if not d.critical]
        
        if critical_deps:
            md.append("\n### Critical Dependencies\n")
            for dep in critical_deps:
                md.append(f"- **{dep.name}** - {dep.usage}")
        
        if other_deps:
            md.append("\n### Other Dependencies\n")
            for dep in other_deps[:15]:
                md.append(f"- {dep.name}")
        
        
        md.append("\n## 💧 Data Flows\n")
        if report.data_flows:
            for flow in report.data_flows[:10]:
                md.append(f"- **{flow.source}** → **{flow.destination}**")
                md.append(f"  - Data: {flow.data_type}")
                md.append(f"  - Trigger: {flow.trigger}")
        else:
            md.append("\n*Data flows require deeper analysis.*\n")
        
        
        md.append("\n## 🛤️ Key Execution Paths\n")
        for path in report.execution_paths[:3]:
            md.append(f"\n### {path.name}\n")
            md.append(f"{path.description}\n")
            md.append("**Steps:**\n")
            for i, step in enumerate(path.steps[:8], 1):
                md.append(f"{i}. `{step['function']}`")
            if len(path.steps) > 8:
                md.append(f"... and {len(path.steps) - 8} more")
        
        
        md.append("\n## 💡 Recommendations\n")
        md.append("\n### For Understanding This Codebase\n")
        md.append("1. Start with entry points listed above")
        md.append("2. Review core entities and their relationships")
        md.append("3. Trace execution paths for key features")
        md.append("4. Review business rules for domain logic")
        md.append("5. Check external dependencies for integration points\n")
        
        md.append("\n### For Code Quality\n")
        md.append("1. Add documentation to entry points")
        md.append("2. Document business rules explicitly")
        md.append("3. Create architecture decision records (ADRs)")
        md.append("4. Add data flow diagrams\n")
        
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(md))






def main():
    parser = argparse.ArgumentParser(description='Deep Code Analyzer')
    parser.add_argument('--path', '-p', default='.', help='Path to codebase')
    parser.add_argument('--output', '-o', help='Output file (Markdown)')
    parser.add_argument('--exclude', '-e', help='Exclude patterns')
    
    args = parser.parse_args()
    
    exclude = args.exclude.split(',') if args.exclude else None
    analyzer = DeepCodeAnalyzer(args.path, exclude_patterns=exclude)
    analyzer.run(output=args.output)


if __name__ == '__main__':
    main()
